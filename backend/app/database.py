from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Optional
from app.config import Settings, settings
import logging
import threading

_engine_lock = threading.Lock()


def _ensure_database(cfg: Optional[Settings] = None):
    """若数据库不存在则自动创建（先连到 MySQL 不带库名，执行 CREATE DATABASE）"""
    cfg = cfg or settings
    url_no_db = (
        f"mysql+pymysql://{cfg.DB_USER}:{cfg.DB_PASSWORD}"
        f"@{cfg.DB_HOST}:{cfg.DB_PORT}"
    )
    eng = create_engine(url_no_db, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{cfg.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    eng.dispose()


def _create_engine(cfg: Settings):
    # 1026 全站僵死根因修复：连接池防吊死。
    # 当晚 DB 链路瞬间劣化后，正在用连接的请求/后台线程吊死在 pymysql 无超时的 recv() 上
    # 永不归还，5+10=15 条连接全被吊死会话占光 → 之后每个请求排队 30s QueuePool 超时，
    # 全站僵死 10 小时直到重启。两道保险：
    # ① read/write/connect_timeout：卡死的查询到点抛错、连接归还，不再永久占线
    #    （pool_pre_ping 只防「取用时」的死连接，防不了「使用中」吊死，必须配超时）；
    # ② 池扩到 10+20 且 pool_timeout=5：突发排队扛得住，真满了 5 秒快速失败不堆积线程。
    # 注：read/write/connect_timeout 是 pymysql 专有参数，PG 方言不能带；
    # Settings.database_url 只会是 mysql+pymysql 或 postgresql+psycopg2，按前缀分流保险。
    connect_args = {}
    if cfg.database_url.startswith("mysql"):
        connect_args = {
            "connect_timeout": 10,
            "read_timeout": 120,
            "write_timeout": 120,
        }
    return create_engine(
        cfg.database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
        pool_timeout=5,
        connect_args=connect_args,
        echo=False,
    )


# C5：默认禁止启动时自动建库/改表。仅在显式开启 AUTO_DDL=true（且 DB 账号具备 DDL 权限）时执行。
if getattr(settings, "AUTO_DDL", False):
    _ensure_database()

engine = _create_engine(settings)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def reload_database_engine(cfg: Optional[Settings] = None) -> None:
    """切换 .env 后重建 SQLAlchemy 连接池，并同步目标库表结构。"""
    global engine, SessionLocal
    with _engine_lock:
        cfg = cfg or Settings()
        # C5：切换数据库时同样受 AUTO_DDL 控制，避免意外对生产库执行 DDL
        if getattr(settings, "AUTO_DDL", False):
            _ensure_database(cfg)
        old_engine = engine
        engine = _create_engine(cfg)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        old_engine.dispose()
        if getattr(settings, "AUTO_DDL", False):
            sync_database_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """导入所有 model 后调用，若无表则自动建表"""
    sync_database_schema()
    _ensure_dingtalk_sync_columns()
    # users/students 补列**必须无条件执行**：这两个 ensure 原只挂在 sync_database_schema() 里，
    # 会被 `if not AUTO_DDL: return` 挡掉（生产默认 AUTO_DDL=false），导致 users.teaching_grade
    # 等列加了模型却没加到库，auth/register 直接 1054 → 500（D-1 事故同因）。
    _ensure_user_extra_columns()
    _ensure_student_extra_columns()
    _ensure_class_review_sessions_user_id()
    # R2 作业采集补列：无条件幂等执行（同 _ensure_dingtalk_sync_columns），
    # 保证 write_response_logs 插入 grade/homework_type 前列必已存在，避免静默写失败。
    _ensure_response_log_extra_columns()
    # ── 漂移收口：以下补列/建表**不依赖 AUTO_DDL**，必须与 _ensure_dingtalk_sync_columns 并列 ──
    # 理由：真库基线（2026-09-24 只读探针）为 3 表 / 10 列漂移 + 5 张缺表，8 个模型因此查不动
    # （1054 Unknown column / 1146 Table doesn't exist ⇒ 启动即 500）。D-1 事故同因：
    # 这些 ensure 若只写在 sync_database_schema() 里，会被它第 5 行 `if not AUTO_DDL: return`
    # 全部挡掉，生产默认配置（AUTO_DDL=false）下一次都不执行。⛔ 不许上移回该函数 return 之后。
    _ensure_lesson_plan_extra_columns()          # lesson_plans 5 列（textbook_id/unit_id/catalog_id/edition/chapter）
    _ensure_student_wrong_questions_extra_columns()  # student_wrong_questions 4 列
    _ensure_textbook_catalogs_table()            # 缺表 1/5
    _ensure_wrong_question_kp_bridge_table()     # 缺表 2/5
    _ensure_bandit_arm_stats_table()             # 缺表 3/5
    _ensure_response_logs_table()                # 缺表 4/5
    _ensure_ai_generation_history_table()        # 缺表 5/5
    _backfill_class_teacher_heads()
    # 流水阅卷：AUTO_DDL=false 时靠此幂等建表（同 _ensure_response_logs_table 模式）
    _ensure_flow_tables()
    # 批改额度：AUTO_DDL=false 时靠此幂等建表（同 _ensure_grading_daily_stats_table 模式）
    _ensure_grading_quota_tables()
    # 登录/注册合规：验证码表 + 手机号普通索引（幂等兜底，同 _ensure_flow_tables 模式）
    _ensure_verification_codes_table()
    _ensure_user_phone_index()
    # 分层推送（nav/ai-layered）：student_tasks / system_config 两表幂等兜底。
    # student_tasks 只挂在 sync_database_schema() 的 create_all 里、system_config 无任何迁移 SQL，
    # AUTO_DDL=false 的库（本地默认/生产）两张都可能缺 → 推送轮次/设置读写会 1146。
    # 挂**无条件段**，⛔ 不许上移回 sync_database_schema() 的 return 之后。
    _ensure_student_tasks_table()
    _ensure_system_config_table()
    # 修正/复核记账台账（B 项）：AUTO_DDL=false 时靠此幂等建表（同 _ensure_response_logs_table 模式）
    _ensure_correction_ledger_table()
    # 判分缓存（C 项）：同上幂等建表
    _ensure_verdict_cache_table()
    # 靶向提升任务清单（客户 #15）：AUTO_DDL=false 时靠此幂等建表（同 _ensure_response_logs_table 模式）
    _ensure_targeted_improvement_tasks_table()
    # 轻成绩表（对齐批改君 exam_scores）：同上幂等建表
    _ensure_grading_score_summaries_table()
    # 布置作业/打印记录落库（2026-10-23 前是内存队列重启即清）：同上幂等建表
    _ensure_print_jobs_tables()
    # 作文批改标准文本列加宽（2026-11-11）：题目图片 base64 原图直存超 TEXT 64KB → 1406 → 保存标准 500。
    # 同 _ensure_class_review_sessions_longtext 模式幂等 MODIFY，挂无条件段（⛔ 不许上移）。
    _ensure_essay_rubric_longtext()


def sync_database_schema():
    """对当前 engine 指向的库执行建表与增量补列（启动与切换数据库后均需调用）。

    C5：默认 AUTO_DDL=false，本函数直接返回，不自动执行任何 CREATE/ALTER；
    需显式迁移（如手工 SQL / Alembic）并开启 AUTO_DDL=true 后才生效。
    DB 账号建议收敛为 DML-only，DDL 走人工审批。
    """
    if not getattr(settings, "AUTO_DDL", False):
        return
    from app.models import (  # noqa: F401
        user,
        class_model,
        student,
        exam,
        ai_generation_history,
        exam_score,
        wrong_question,
        exam_question_template,
        subject_unit,
        knowledge_point,
        teaching_resource,
        system_config,
        system_settings,
        todo_item,
        feature_flag,
        user_role,
        profile,
        class_teacher,
        essay_rubric,
        lesson_plan,
        textbook_catalog,
        student_analysis,
        targeted_improvement,
        class_review,
        class_analysis,
        grading_daily_stat,
        # ── 种春风三域新表（integration 收口注册，AUTO_DDL=true 时 create_all 建全表）──
        student_portfolio,
        student_growth_record,
        indicator_definition,
        report_snapshot,
        assessment_comment,
        mentor,
        assessment_definition,
        assessment_session,
        assessment_result,
        assessment_answer,
        parent_student,
        badge_definition,
        badge_award,
        credit_account,
        credit_transaction,
        reward_product,
        redemption_record,
        practice_record,
        campus_club,
        club_enrollment,
        club_attendance,
        book_borrow,
        reading_record,
        health_check,
        student_task,
        student_memory,
        attendance_record,
        # ── DL1 学校/区域锚表（regions / schools，AUTO_DDL=true 时 create_all 建锚表）──
        school,
        # ── DL4a C2 校本题库表（school_question_banks，AUTO_DDL=true 时 create_all 建表）──
        school_question_bank,
        # G4-A AI 对话落库（agent_conversations / agent_conversation_messages / agent_audit_logs）
        ai_conversation,
        # R1 逐题响应日志（response_logs，学情预警/bandit 错题推荐数据底座）
        response_log,
        # R6a 错题→知识点桥（wrong_question_kp_bridge，历史错题跨库匹配 PG 知识点结果落表）
        wrong_question_kp_bridge,
        # R6b contextual bandit 状态表（bandit_arm_stats，LinUCB arm 状态与推荐统计）
        bandit_arm_stats,
        # P0-4 食堂电子台账（canteen_records，防篡改只增不改）
        canteen_record,
        # 流水阅卷 / 集体阅卷（flow_* 六表）
        flow_grading,
        # 批改额度账户
        grading_quota,
        # B 项修正/复核记账（correction_ledger；新表 ⇒ AUTO_DDL=false 时靠 _ensure_correction_ledger_table）
        correction_ledger,
        # C 项判分缓存（verdict_cache；新表 ⇒ AUTO_DDL=false 时靠 _ensure_verdict_cache_table）
        verdict_cache,
        # 轻成绩表（grading_score_summaries；新表 ⇒ AUTO_DDL=false 时靠 _ensure_grading_score_summaries_table）
        grading_score_summary,
    )
    Base.metadata.create_all(bind=engine)
    _ensure_grading_daily_stats_table()
    _ensure_response_logs_table()
    _ensure_response_log_extra_columns()
    _ensure_textbook_catalogs_table()
    _ensure_wrong_question_kp_bridge_table()
    _ensure_bandit_arm_stats_table()
    _ensure_user_extra_columns()
    _ensure_student_extra_columns()
    _ensure_lesson_plan_extra_columns()
    _ensure_class_teachers_table()
    _ensure_student_score_history_extra_columns()
    _ensure_system_settings_extra_columns()
    _ensure_essay_rubric_extra_columns()
    _ensure_student_wrong_questions_extra_columns()
    _ensure_smart_exam_paper_header_column()
    _ensure_class_review_sessions_longtext()
    _ensure_sanfeng_alter_columns()
    _ensure_flow_tables()


def _ensure_grading_daily_stats_table():
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS grading_daily_stats (
                        id VARCHAR(36) NOT NULL PRIMARY KEY,
                        user_id VARCHAR(36) NOT NULL,
                        folder_safe VARCHAR(255) NOT NULL DEFAULT '',
                        stat_date DATE NOT NULL,
                        upload_count INT NOT NULL DEFAULT 0,
                        grade_count INT NOT NULL DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY uq_grading_daily_stat (user_id, folder_safe, stat_date),
                        KEY ix_grading_daily_stats_user_id (user_id),
                        KEY ix_grading_daily_stats_folder_safe (folder_safe),
                        KEY ix_grading_daily_stats_stat_date (stat_date),
                        CONSTRAINT fk_grading_daily_stats_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
                    """
                )
            )
            conn.commit()
    except Exception:
        pass


def _ensure_grading_quota_tables():
    """批改额度账户表（幂等兜底，CREATE TABLE IF NOT EXISTS）。
    （充值流水表 grading_quota_recharge_logs 随充值功能 20261111 移除；存量库里的旧表不碰。）"""
    stmt = """
        CREATE TABLE IF NOT EXISTS grading_quota (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            total_pages INT NOT NULL DEFAULT 0,
            used_pages INT NOT NULL DEFAULT 0,
            used_today_pages INT NOT NULL DEFAULT 0,
            usage_date DATE NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_grading_quota_user_id (user_id),
            CONSTRAINT fk_grading_quota_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    try:
        with engine.connect() as conn:
            conn.execute(text(stmt))
            conn.commit()
    except Exception:
        pass


def _ensure_verification_codes_table():
    """验证码表（登录/注册合规，幂等兜底，CREATE TABLE IF NOT EXISTS）。"""
    stmt = """
        CREATE TABLE IF NOT EXISTS verification_codes (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            target VARCHAR(255) NOT NULL,
            channel VARCHAR(16) NOT NULL,
            purpose VARCHAR(32) NOT NULL,
            code_hash VARCHAR(64) NOT NULL,
            expires_at DATETIME NOT NULL,
            consumed TINYINT(1) NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            KEY ix_verification_codes_target (target),
            KEY ix_verification_codes_target_channel_purpose (target, channel, purpose)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    try:
        with engine.connect() as conn:
            conn.execute(text(stmt))
            conn.commit()
    except Exception:
        pass


def _ensure_user_phone_index():
    """给 users.phone 加普通索引（非唯一）——手机号登录按 phone 反查用户时提速。

    ⚠️ 用普通索引而非唯一索引：存量库 phone 可能存在非 NULL 重复，唯一索引会 ALTER 失败。
    唯一性由应用层在 bind/register 前查重强制。
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE INDEX ix_users_phone ON users (phone)"))
            conn.commit()
    except Exception:
        pass


def _ensure_response_logs_table():
    """R1 逐题响应日志表（幂等兜底，按模型 metadata 建表）。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    """
    try:
        from app.models.response_log import ResponseLog  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[ResponseLog.__table__])
    except Exception:
        pass


def _ensure_correction_ledger_table():
    """B 项修正/复核记账台账幂等建表（correction_ledger，按模型 metadata 建表）。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    """
    try:
        from app.models.correction_ledger import CorrectionLedger  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[CorrectionLedger.__table__])
    except Exception:
        pass


def _ensure_verdict_cache_table():
    """C 项判分缓存幂等建表（verdict_cache，按模型 metadata 建表）。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    """
    try:
        from app.models.verdict_cache import VerdictCache  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[VerdictCache.__table__])
    except Exception:
        pass


def _ensure_grading_score_summaries_table():
    """轻成绩表幂等建表（grading_score_summaries，对齐批改君 exam_scores）。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    模型 __table_args__ 带 mysql_collate=utf8mb4_0900_ai_ci（DDL 漂移口径）。
    """
    try:
        from app.models.grading_score_summary import GradingScoreSummary  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[GradingScoreSummary.__table__])
    except Exception:
        pass


def _ensure_print_jobs_tables():
    """布置作业/打印记录幂等建表（print_jobs / print_uploads）。

    2026-10-23 前 print_jobs 是纯内存队列（重启即清空、不留痕），网页端无法
    留痕/修改；落库后小程序与网页共享同一批作业记录。AUTO_DDL=true 时 create_all
    已建；此处显式 ensure，失败不阻断启动。模型 __table_args__ 带
    mysql_collate=utf8mb4_0900_ai_ci（DDL 漂移口径）。
    """
    try:
        from app.models.print_job import PrintJobRow, PrintUploadRow  # noqa: F401

        Base.metadata.create_all(
            bind=engine, tables=[PrintJobRow.__table__, PrintUploadRow.__table__]
        )
    except Exception:
        pass


def _ensure_targeted_improvement_tasks_table():
    """靶向提升任务清单幂等建表（targeted_improvement_tasks，客户功能 #15）。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    模型 __table_args__ 带 mysql_collate=utf8mb4_0900_ai_ci（DDL 漂移口径）。
    依赖父表 targeted_improvement_reports / classes / students，故一并 create_all 保序。
    """
    try:
        from app.models.targeted_improvement import (  # noqa: F401
            TargetedImprovementReport,
            TargetedImprovementTask,
        )

        Base.metadata.create_all(
            bind=engine,
            tables=[
                TargetedImprovementReport.__table__,
                TargetedImprovementTask.__table__,
            ],
        )
    except Exception:
        pass


def _ensure_student_tasks_table():
    """学生任务/分层推送轮次表幂等建表（student_tasks，按模型 metadata 建表）。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    """
    try:
        from app.models.student_task import StudentTask  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[StudentTask.__table__])
    except Exception:
        pass


def _ensure_system_config_table():
    """通用 KV 配置表幂等建表（system_config，分层推送设置存储）。

    该表无任何迁移 SQL，仅模型存在；此处显式 ensure，失败不阻断启动。
    """
    try:
        from app.models.system_config import SystemConfig  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[SystemConfig.__table__])
    except Exception:
        pass


def _ensure_flow_tables():
    """流水阅卷六表幂等建表（flow_batches/questions/items/assignments/reviews/arbitrations）。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    create_all(tables=[...]) 会按外键依赖自动排序建表。
    """
    try:
        from app.models.flow_grading import (  # noqa: F401
            FlowBatch,
            FlowQuestion,
            FlowItem,
            FlowAssignment,
            FlowReview,
            FlowArbitration,
        )

        Base.metadata.create_all(
            bind=engine,
            tables=[
                FlowBatch.__table__,
                FlowQuestion.__table__,
                FlowItem.__table__,
                FlowAssignment.__table__,
                FlowReview.__table__,
                FlowArbitration.__table__,
            ],
        )
    except Exception:
        pass


def _ensure_ai_generation_history_table():
    """G4 AI 生成历史表（ai_generation_history）幂等兜底，按模型 metadata 建表。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    缺表时 routers/ai_resources 的 list/get 直接 1146，故与其它 ensure 并列在无条件段。
    """
    try:
        from app.models.ai_generation_history import AiGenerationHistory  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[AiGenerationHistory.__table__])
    except Exception:
        pass


def _ensure_single_column_indexes(table, col_names):
    """为 ORM 声明了 index=True 的单列补索引。

    索引名与列名一律取自 ORM（`table.indexes`），⛔ 不自创；多列复合索引不在此处理。
    幂等：索引已存在时 MySQL 抛 1061 被 except 吞掉，失败不阻断启动。
    """
    for idx in table.indexes:
        cols = list(idx.columns)
        if len(cols) != 1 or cols[0].name not in col_names:
            continue
        try:
            with engine.connect() as conn:
                conn.execute(
                    text(f"CREATE INDEX {idx.name} ON {table.name} ({cols[0].name})")
                )
                conn.commit()
        except Exception:
            pass


def _ensure_response_log_extra_columns():
    """R2 作业采集：response_logs 补列（学科/年级/班级/作业类型）。

    create_all 不补既有表列，需 ALTER 幂等补列；列已存在时静默跳过，失败不阻断启动。
    subject/class_id 建表时已含，此处一并列出兜底旧库缺列场景。
    """
    cols = [
        ("subject", "VARCHAR(64) NULL"),
        ("class_id", "VARCHAR(36) NULL"),
        ("grade", "VARCHAR(32) NULL"),
        ("homework_type", "VARCHAR(64) NULL"),
    ]
    for name, ddl in cols:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE response_logs ADD COLUMN {name} {ddl}"))
                conn.commit()
        except Exception:
            pass


def _ensure_textbook_catalogs_table():
    """R4 教材目录表（textbook_catalogs）幂等兜底，按模型 metadata 建表。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    """
    try:
        from app.models.textbook_catalog import TextbookCatalog  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[TextbookCatalog.__table__])
    except Exception:
        pass


def _ensure_wrong_question_kp_bridge_table():
    """R6a 错题→知识点桥表（wrong_question_kp_bridge）幂等兜底，按模型 metadata 建表。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    """
    try:
        from app.models.wrong_question_kp_bridge import WrongQuestionKpBridge  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[WrongQuestionKpBridge.__table__])
    except Exception:
        pass


def _ensure_bandit_arm_stats_table():
    """R6b bandit 状态表（bandit_arm_stats）幂等兜底，按模型 metadata 建表。

    AUTO_DDL=true 时 create_all 已建；此处显式 ensure，失败不阻断启动。
    非关键路径：表不存在时 service 写库静默降级，推荐主流程不受影响。
    """
    try:
        from app.models.bandit_arm_stats import BanditArmStats  # noqa: F401

        Base.metadata.create_all(bind=engine, tables=[BanditArmStats.__table__])
    except Exception:
        pass


def _ensure_class_review_sessions_longtext():
    """将课堂讲评表中的 JSON 字段类型改为 LONGTEXT，防止试卷过多时超长报错"""
    cols = [
        "exam_names_json",
        "imported_folder_names_json",
        "source_summary_json",
        "pre_class_json",
        "tracking_json",
        "consolidation_json",
        "post_feedback_json",
        "ai_raw_json",
    ]
    try:
        with engine.connect() as conn:
            for col in cols:
                try:
                    conn.execute(text(f"ALTER TABLE class_review_sessions MODIFY COLUMN {col} LONGTEXT NULL"))
                    conn.commit()
                except Exception:
                    pass
            
            # 同样对靶向提升相关的表进行处理
            ti_cols = [
                "diagnosis_text",
                "plan_text",
                "diagnosis_json",
                "plan_json",
                "source_summary_json",
                "exam_names_json",
                "imported_folder_names_json",
                "ai_raw_json",
            ]
            for col in ti_cols:
                try:
                    conn.execute(text(f"ALTER TABLE targeted_improvement_reports MODIFY COLUMN {col} LONGTEXT NULL"))
                    conn.commit()
                except Exception:
                    pass
                    
            try:
                conn.execute(text(f"ALTER TABLE targeted_recommendations MODIFY COLUMN student_names_json LONGTEXT NULL"))
                conn.commit()
            except Exception:
                pass
    except Exception:
        pass

def _ensure_class_review_sessions_user_id():
    """课堂讲评按账号隔离：加 user_id 列，唯一约束由 (class_id, subject) 扩为 (class_id, subject, user_id)。

    幂等：ADD COLUMN / ADD INDEX / DROP INDEX / ADD UNIQUE INDEX 均 try/except 兜底，
    重复执行时「已存在 / 不存在」导致的报错被吞掉，不影响启动。
    注意：MySQL 的 UNIQUE 索引对 NULL 不判重，旧数据 user_id 全为 NULL 可共存，
    新数据按账号唯一；旧记录 user_id 为 NULL，不会被任何按 user_id 过滤的查询命中（自然隐藏）。
    """
    stmts = [
        "ALTER TABLE class_review_sessions ADD COLUMN user_id VARCHAR(36) NULL",
        "ALTER TABLE class_review_sessions ADD INDEX ix_class_review_sessions_user_id (user_id)",
        "ALTER TABLE class_review_sessions DROP INDEX uq_class_review_session_class_subject",
        "ALTER TABLE class_review_sessions ADD UNIQUE INDEX uq_class_review_session_class_subject (class_id, subject, user_id)",
    ]
    for stmt in stmts:
        try:
            with engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()
        except Exception:
            pass


def _ensure_essay_rubric_extra_columns():
    cols = [
        ("topic_text", "TEXT NULL"),
        ("topic_image_base64", "LONGTEXT NULL"),
        ("dimensions_json", "TEXT NULL"),
    ]
    for name, ddl in cols:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE essay_rubrics ADD COLUMN {name} {ddl}"))
                conn.commit()
        except Exception:
            pass


def _ensure_essay_rubric_longtext():
    """essay_rubrics 文本列加宽（幂等 MODIFY）。

    2026-11-11 实锤：作文标准的题目图片走 FileReader 原图 base64 直存，
    create_all 建出来的 TEXT 列只有 64KB，任何真实图片都撑爆 → 1406 Data too
    long → 保存/修改标准报 500 Internal Server Error。同
    _ensure_class_review_sessions_longtext 模式，启动即幂等加宽。
    """
    cols = [
        ("content", "MEDIUMTEXT"),
        ("summary_prompt", "MEDIUMTEXT"),
        ("comment_prompt", "MEDIUMTEXT"),
        ("rewrite_prompt", "MEDIUMTEXT"),
        ("guidance_prompt", "MEDIUMTEXT"),
        ("scoring_prompt", "MEDIUMTEXT"),
        ("topic_text", "MEDIUMTEXT"),
        ("topic_image_base64", "LONGTEXT"),
        ("dimensions_json", "MEDIUMTEXT"),
    ]
    for name, typ in cols:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE essay_rubrics MODIFY COLUMN {name} {typ} NULL"))
                conn.commit()
        except Exception:
            pass


def _ensure_student_wrong_questions_extra_columns():
    """已有库补列：student_wrong_questions 多校归属与订正状态列（P3-B3 错题实体统一）。

    学校错题唯一权威，幂等加列；重复执行 ADD COLUMN 已存在时 MySQL 抛错被 except 吞掉。
    """
    cols = [
        ("school_id", "VARCHAR(36) NULL"),
        ("corrected_at", "DATETIME NULL"),
        ("knowledge_point_id", "VARCHAR(36) NULL"),
        ("status", "VARCHAR(16) NOT NULL DEFAULT 'open'"),
    ]
    for name, ddl in cols:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE student_wrong_questions ADD COLUMN {name} {ddl}"))
                conn.commit()
        except Exception:
            pass
    # ORM 对 school_id / knowledge_point_id 声明了 index=True，补齐（否则补出来的库与 create_all 建的库不一致）
    try:
        from app.models.student_analysis import StudentWrongQuestion

        _ensure_single_column_indexes(StudentWrongQuestion.__table__, [n for n, _ in cols])
    except Exception:
        pass


def _ensure_smart_exam_paper_header_column():
    """已有库补列：smart_exam_papers.header_fields（11.9-2 智能组卷卷头可编辑字段）。

    幂等加列；重复执行 ADD COLUMN 已存在时 MySQL 抛错被 except 吞掉。
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE smart_exam_papers ADD COLUMN header_fields JSON NULL"))
            conn.commit()
    except Exception:
        pass


def _ensure_student_score_history_extra_columns():
    """已有库补列：student_score_history.class_avg"""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE student_score_history ADD COLUMN class_avg INT NULL"
                )
            )
            conn.commit()
    except Exception:
        pass


def _ensure_system_settings_extra_columns():
    """Add credentials and model settings to existing system_settings tables."""
    cols = [
        ("baidu_api_key", "TEXT NULL"),
        ("baidu_secret_key", "TEXT NULL"),
        ("dashscope_api_key", "TEXT NULL"),
        ("qwen_model", "VARCHAR(64) NULL"),
    ]
    for name, ddl in cols:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE system_settings ADD COLUMN {name} {ddl}"))
                conn.commit()
        except Exception:
            pass


def _backfill_class_teacher_heads():
    """旧数据：为每个班级补一条班主任任课记录"""
    from app.models.class_model import Class
    from app.models.class_teacher import ClassTeacher
    from app.models.user import User

    db = SessionLocal()
    try:
        for c in db.query(Class).all():
            exists = (
                db.query(ClassTeacher)
                .filter(ClassTeacher.class_id == c.id, ClassTeacher.user_id == c.user_id)
                .first()
            )
            if exists:
                continue
            u = db.query(User).filter(User.id == c.user_id).first()
            subj = getattr(u, "teaching_subject", None) if u else None
            db.add(ClassTeacher(class_id=c.id, user_id=c.user_id, role="head", subject=subj))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _ensure_dingtalk_sync_columns():
    """钉钉通讯录同步补列（幂等）：classes.dingtalk_dept_id / students.dingtalk_userid / users.dingtalk_userid。

    在 init_db 中无条件调用（不依赖 AUTO_DDL），保证重启后三列立即存在，
    避免新增 ORM 字段后 list_classes 等查询因缺列报错。
    """
    try:
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE classes ADD COLUMN dingtalk_dept_id VARCHAR(64) NULL")
            )
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE students ADD COLUMN dingtalk_userid VARCHAR(64) NULL")
            )
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN dingtalk_userid VARCHAR(64) NULL")
            )
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(
                text("CREATE INDEX ix_users_dingtalk_userid ON users (dingtalk_userid)")
            )
            conn.commit()
    except Exception:
        pass


def _ensure_user_extra_columns():
    """已有库补列：phone、teaching_subject、roles"""
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN phone VARCHAR(32) NULL"
                )
            )
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN teaching_subject VARCHAR(32) NULL"
                )
            )
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN teaching_grade VARCHAR(32) NULL"
                )
            )
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN roles VARCHAR(255) NULL"
                )
            )
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN job_title VARCHAR(255) NULL"
                )
            )
            conn.commit()
    except Exception:
        pass
    # C4：不再新增 plain_password 明文密码列（历史库中若存在该列，需要人工迁移清理）
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN personal_email VARCHAR(255) NULL"
                )
            )
            conn.commit()
    except Exception:
        pass
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN ui_locale VARCHAR(8) NULL DEFAULT 'zh'"
                )
            )
            conn.commit()
    except Exception:
        pass


def _ensure_student_extra_columns():
    """已有库补列：学生详细信息字段"""
    # 注意：全部 try/except 兜底，避免重复执行导致启动失败
    cols = [
        ("gender", "VARCHAR(8) NULL"),
        ("tier", "VARCHAR(2) NULL"),
        ("status", "VARCHAR(16) NULL"),
        ("birthday", "VARCHAR(32) NULL"),
        ("phone", "VARCHAR(32) NULL"),
        ("parent_name", "VARCHAR(255) NULL"),
        ("parent_phone", "VARCHAR(32) NULL"),
        ("address", "VARCHAR(255) NULL"),
        ("enroll_date", "VARCHAR(32) NULL"),
        ("seat_row", "INT NULL"),
        ("seat_col", "INT NULL"),
        ("cadre_role", "VARCHAR(64) NULL"),
        ("notes", "VARCHAR(1024) NULL"),
    ]
    for name, ddl in cols:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE students ADD COLUMN {name} {ddl}"))
                conn.commit()
        except Exception:
            pass


def _ensure_lesson_plan_extra_columns():
    """已有库补列：教案扩展字段"""
    cols = [
        ("deputy_author", "VARCHAR(255) NULL"),
        ("lesson_sequence", "VARCHAR(64) NULL"),
        ("school_year", "VARCHAR(32) NULL"),
        ("term", "VARCHAR(32) NULL"),
        ("collective_preparation_advice", "TEXT NULL"),
        # R4 备课 MVP：教材级联字段（全部可空，旧数据零影响）
        ("textbook_id", "VARCHAR(36) NULL"),
        ("unit_id", "VARCHAR(36) NULL"),
        ("catalog_id", "VARCHAR(36) NULL"),
        ("edition", "VARCHAR(64) NULL"),
        ("chapter", "VARCHAR(128) NULL"),
    ]
    for name, ddl in cols:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE lesson_plans ADD COLUMN {name} {ddl}"))
                conn.commit()
        except Exception:
            pass
    # ORM 对 textbook_id / unit_id / catalog_id 声明了 index=True，补齐（否则补出来的库与 create_all 建的库不一致）
    try:
        from app.models.lesson_plan import LessonPlan

        _ensure_single_column_indexes(LessonPlan.__table__, [n for n, _ in cols])
    except Exception:
        pass


def _ensure_class_teachers_table():
    """若 create_all 未执行到新表时的兜底（一般不需要）"""
    from app.models import class_teacher  # noqa: F401
    Base.metadata.create_all(bind=engine)


def _ensure_sanfeng_alter_columns():
    """种春风 A 域幂等补列/建表（99 §4.1 ALTER 段）。

    create_all 只建新表，不补既有表列；exam_scores/wrong_questions/students 的
    class_avg/class_rank/school_id/status/corrected_at/knowledge_point_id 等列
    由 A-agent 的 app/services/portfolio/alter_schema.apply_schema 幂等补齐
    （information_schema 检查，已存在跳过）。失败不阻断启动。
    """
    try:
        from app.services.portfolio.alter_schema import apply_schema
        apply_schema(engine)
    except Exception:
        pass
