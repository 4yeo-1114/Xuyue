# 对账裁决 — 四契约统一（00/A0/B0/C0）

> 版本: 1.0 | 日期: 2026-08-11 | 状态: **契约级**
> 本文件是 Wave 1 后端建表的**唯一权威依据**。00/10/11/12 四份契约中与本文件冲突之处，一律以本文件为准。
> 裁决原则：**命名铁律（蛇形复数）优先；领域契约（A0/B0/C0 的详细设计）优先于基线简化版；概念重叠时保留完整产品闭环，删除基线占位。**

---

## 1. 结论速览

| # | 冲突点 | 参与契约 | 裁决 | 权威 DDL 位置 |
|---|--------|---------|------|--------------|
| 1 | 画像主表命名+结构 | 00 `student_portfolios`（五列展开）vs A0 `student_portfolio`（dimensions JSON） | 表名 `student_portfolios`，**结构采纳 A0 JSON 方案** | 本文件 §4.1 |
| 2 | 成长流水命名+字段 | 00 `student_growth_records` vs A0 `student_growth_record` vs C0 反推版（缺 updated_at） | 表名 `student_growth_records`，字段融合 A0 主 + C0 消费 | 本文件 §4.1 |
| 3 | 报告快照 | 00 `report_snapshots` vs A0 `report_snapshot` | 表名 `report_snapshots`，字段采纳 A0 | 本文件 §4.1 |
| 4 | AI 评语 | 00 `assessment_comments` vs A0 `assessment_comment` | 表名 `assessment_comments`，字段采纳 A0 | 本文件 §4.1 |
| 5 | 测评三表 | 00 简化版 vs B0 领域版（含 answers） | 表名全复数（一致），**字段全部采纳 B0** | 本文件 §4.2 |
| 6 | 徽章 | 00 `student_badges`（单表） vs C0 `badge_definitions`+`badge_awards`（双表） | **C0 双表胜出**，00 单表删除 | C0 §1.1 |
| 7 | 积分 | 00 `student_point_accounts/transactions` vs C0 `credit_accounts/transactions`+兑换 | **C0 学分银行胜出**，00 积分账户删除 | C0 §1.2-1.4 |
| 8 | 任务/导师 | 00 `student_tasks`、`mentors`（无冲突） | 保留 | 00 §5.8 / §5.12 |
| 9 | 智能体预留 6 表 | 00 §3（agent_*） | 保留 schema，Wave 1 不实现 | 00 §3 |

**删除清单（不得建表）**：`student_point_accounts`、`student_point_transactions`、`student_badges`、`student_portfolio`（单数）、`student_growth_record`（单数）、`report_snapshot`（单数）、`assessment_comment`（单数）。

---

## 2. 命名统一（铁律，适用全部表）

- 表名一律**蛇形复数**：`student_portfolios`、`student_growth_records`、`report_snapshots`、`assessment_comments`。
- Model 文件名蛇形单数：`app/models/student_portfolio.py`（类 `StudentPortfolio`）。
- 每表必须含 `created_at` + `updated_at`（只读快照如 `assessment_answers`、`agent_audit_logs` 可省略 `updated_at`，但**成长流水/画像主表必须含**）。
- 外键只指向三锚表：`users.id` / `classes.id` / `students.id`，外键字段必建索引。
- `id VARCHAR(36) PRIMARY KEY`，`default=gen_uuid`。

---

## 3. 概念冲突详裁

### 3.1 徽章：C0 双表胜出，00 `student_badges` 删除
`badge_definitions`（章定义，可配置类别/五育维度/积分/适用年级）+ `badge_awards`（颁章记录，`uk_student_badge_date` 去重 + `credit_transaction_id` 关联入账）支撑「定义管理 → 单人/批量颁发 → 自动入账 → 撤销回滚」完整闭环，是学生端运营核心功能。00 的单表 `student_badges`（badge_code 硬编码）无法支撑运营配置，废弃。

### 3.2 积分：C0 学分银行胜出，00 积分账户删除
C0 的 `credit_accounts` + `credit_transactions` + `reward_products` + `redemption_records` 覆盖「颁章入账 → 手动加减 → 兑换扣减 → 审核/发放 → 过期清零」全链路。00 的 `student_point_accounts/transactions` 是泛化占位，与学分银行同概念。
**融合点**：C0 `credit_transactions.transaction_type` 为枚举，如后续需要任务完成/考试成绩类自动入账，扩展枚举值（如 `task_complete`、`exam_top3`）即可，**不需要**重建 00 的积分表。

### 3.3 测评：B0 领域版为准
`assessment_definitions` 采纳 B0 版（比 00 多 `description` 字段、`questions` JSON 结构定义）。
`assessment_sessions` 采纳 B0 版（`batch_id`/`proctored_by`/`created_by`，状态机含 `canceled`）。
`assessment_results` 采纳 B0 版（`guardian_consent` 为 JSON 含 version 状态机，`CHECK (purpose='anchor')` 学术红线，`raw_score` JSON）。
`assessment_answers` 为 B0 新增表，保留（v1 可选启用）。

### 3.4 画像主表：A0 JSON 方案 vs 00 展开列
00 用 5 个独立 FLOAT 列（dimension_moral...）+ detail_json LONGTEXT；A0 用 `dimensions` JSON 缓存五育 + `detail`/`auto_detail` JSON + `total_growth_point DECIMAL(10,2)`。
**采纳 A0**，理由：智育事件经时间衰减产生小数（DECIMAL 精确）；JSON 可动态扩展五维明细；与 AI 评语、报告 payload 直接交换 JSON 无需序列化 LONGTEXT。

---

## 4. 权威 DDL（Wave 1 建表唯一依据）

### 4.1 画像域（4 表 + 现有表 ALTER）

```sql
-- ============ 4.1.1 student_portfolios 学生五育画像主表 ============
CREATE TABLE IF NOT EXISTS `student_portfolios` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `student_id` VARCHAR(36) NOT NULL,
    `class_id` VARCHAR(36) NOT NULL,
    `school_id` VARCHAR(36) NULL,
    `base_points` INT NOT NULL DEFAULT 100,
    `dimensions` JSON NOT NULL COMMENT '{"moral":0,"intellectual":15.5,"physical":0,"aesthetic":0,"labor":0,"total":15.5}',
    `detail` JSON NULL COMMENT '智育明细',
    `auto_detail` JSON NULL COMMENT '智育自动事件明细(cap后)',
    `total_growth_point` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '综合成就分(Σ五维,不含base)',
    `last_calculated_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_sp_student_id` (`student_id`),
    KEY `idx_sp_class_id` (`class_id`),
    CONSTRAINT `fk_sp_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sp_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生五育成长画像主表';
-- school_id 可空：叙阅单校定制，冗余列保留，不填不阻塞

-- ============ 4.1.2 student_growth_records 成长流水（融合 A0 主 + C0 消费） ============
-- 所有者: A 画像 agent。C 学生运营是写入方，写入字段按 source_type/source_id 映射，不重复定义。
CREATE TABLE IF NOT EXISTS `student_growth_records` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `student_id` VARCHAR(36) NOT NULL,
    `class_id` VARCHAR(36) NOT NULL,
    `school_id` VARCHAR(36) NULL,
    `dimension` VARCHAR(32) NOT NULL COMMENT 'moral|intellectual|physical|aesthetic|labor',
    `source_type` VARCHAR(32) NOT NULL DEFAULT 'manual' COMMENT 'manual|badge_award|practice_record|club_activity|reading_record|health_check|exam|wrong_question|targeted_report|auto_event',
    `source_id` VARCHAR(36) NULL COMMENT '来源记录ID，幂等去重键之一',
    `growth_points` INT NOT NULL DEFAULT 0 COMMENT '本次贡献分值(+/-)',
    `evidence` JSON NULL,
    `note` VARCHAR(512) NULL COMMENT '事件标题/教师备注',
    `created_by` VARCHAR(36) NULL COMMENT '录入人 users.id；系统自动事件为 NULL',
    `occurred_at` DATETIME NULL COMMENT '业务发生时间(时间衰减用)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY `idx_sgr_student_id` (`student_id`),
    KEY `idx_sgr_student_dim` (`student_id`, `dimension`),
    KEY `idx_sgr_student_time` (`student_id`, `occurred_at`),
    KEY `idx_sgr_source` (`source_type`, `source_id`),
    CONSTRAINT `fk_sgr_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sgr_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sgr_creator` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生成长记录流水表';
-- 幂等: 应用层保证 (student_id, source_type, source_id) 不重复录入

-- ============ 4.1.3 report_snapshots 学期报告快照 ============
CREATE TABLE IF NOT EXISTS `report_snapshots` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `student_id` VARCHAR(36) NOT NULL,
    `class_id` VARCHAR(36) NOT NULL,
    `school_id` VARCHAR(36) NULL,
    `term` VARCHAR(32) NOT NULL COMMENT '2025-2026-1',
    `version` INT NOT NULL DEFAULT 1,
    `parent_id` VARCHAR(36) NULL COMMENT '版本链',
    `payload` JSON NOT NULL,
    `generated_by` VARCHAR(36) NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_rs_student_term_version` (`student_id`, `term`, `version`),
    KEY `idx_rs_class_term` (`class_id`, `term`),
    CONSTRAINT `fk_rs_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_rs_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_rs_parent` FOREIGN KEY (`parent_id`) REFERENCES `report_snapshots` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_rs_genby` FOREIGN KEY (`generated_by`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学期报告快照(冻结不可变)';

-- ============ 4.1.4 assessment_comments AI 学期评语 ============
CREATE TABLE IF NOT EXISTS `assessment_comments` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `student_id` VARCHAR(36) NOT NULL,
    `class_id` VARCHAR(36) NOT NULL,
    `school_id` VARCHAR(36) NULL,
    `term` VARCHAR(32) NOT NULL,
    `status` VARCHAR(16) NOT NULL DEFAULT 'ai_generated' COMMENT 'ai_generated|confirmed|ai_failed',
    `ai_content` TEXT NULL,
    `confirmed_content` TEXT NULL,
    `ai_model` VARCHAR(64) NULL,
    `tokens_used` INT NULL,
    `cost_cent` INT NULL,
    `gate_flagged` TINYINT(1) NOT NULL DEFAULT 0,
    `created_by` VARCHAR(36) NOT NULL,
    `confirmed_by` VARCHAR(36) NULL,
    `confirmed_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_ac_student_term` (`student_id`, `term`),
    KEY `idx_ac_class_term` (`class_id`, `term`),
    CONSTRAINT `fk_ac_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ac_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ac_creator` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ac_confirmer` FOREIGN KEY (`confirmed_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI学期评语表';
```

**现有表 ALTER（A0 §1 前置，执行前必须 information_schema 幂等检查）**：

```sql
-- exam_scores: 智育事件必需（class_avg/class_rank/class_id/school_id）
ALTER TABLE exam_scores
    ADD COLUMN class_avg  DECIMAL(10,2) NULL,
    ADD COLUMN class_rank INT           NULL,
    ADD COLUMN class_id   VARCHAR(36)   NULL,
    ADD COLUMN school_id  VARCHAR(36)   NULL;

-- wrong_questions: 订正状态 + 知识点关联
ALTER TABLE wrong_questions
    ADD COLUMN status             VARCHAR(16)  NOT NULL DEFAULT 'open',
    ADD COLUMN corrected_at       DATETIME     NULL,
    ADD COLUMN knowledge_point_id VARCHAR(36)  NULL,
    ADD COLUMN school_id          VARCHAR(36)  NULL;
CREATE INDEX idx_wq_status    ON wrong_questions (student_id, status);
CREATE INDEX idx_wq_kp        ON wrong_questions (student_id, knowledge_point_id, status);
CREATE INDEX idx_wq_corrected ON wrong_questions (student_id, corrected_at);

-- students: school_id 冗余
ALTER TABLE students ADD COLUMN school_id VARCHAR(36) NULL;
```

> ⚠️ 执行前置：`information_schema.COLUMNS` 逐个查列是否已存在，已存在则跳过（幂等）。`exam_scores` 若已存在 `class_avg/class_rank`（C0 摘要显示 exam_scores 曾有相关字段规划），以实际 schema 为准，重复列跳过。

### 4.2 测评域（4 表，全部以 B0 §2 为准，此处仅列表名）

- `assessment_definitions` — B0 §2.1（含 `description`，`questions` JSON）
- `assessment_sessions` — B0 §2.2（含 `batch_id`/`proctored_by`/`created_by`，状态机含 `canceled`）
- `assessment_results` — B0 §2.3（`guardian_consent` JSON + `CHECK (purpose='anchor')`）
- `assessment_answers` — B0 §2.4（可选用；v1 建议先写 `raw_score` JSON）

### 4.3 学生运营域（13 表，以 C0 §1 为准，无修订）

`badge_definitions` / `badge_awards` / `credit_accounts` / `credit_transactions` / `reward_products` / `redemption_records` / `practice_records` / `campus_clubs` / `club_enrollments` / `club_attendance` / `book_borrows` / `reading_records` / `health_checks`

> C0 §1 已全部复数命名 + 含 `created_at`/`updated_at` + 外键三锚表，直接引用，本文件不重复。

### 4.4 保留表

- `student_tasks`（00 §5.8）— 学生任务/打卡，**归 C 运营 agent**。
- `mentors`（00 §5.12）— 导师指派，归 A 画像 agent（与画像强相关）。
- 智能体预留 6 表（00 §3）— `agent_llm_configs`/`agent_tools`/`agent_tool_instances`/`agent_conversations`/`agent_conversation_messages`/`agent_audit_logs`。Wave 1 **只建 schema**，不实现逻辑。

---

## 5. 各契约需修订点

| 契约 | 修订 |
|------|------|
| 00 | §5.1-5.4 被本文件 §4.1 覆盖（画像主表改 JSON 方案、删除积分两表）；§5.5-5.7 被本文件 §4.2 覆盖（对齐 B0）；§5.9 `student_badges` 删除。§5 标题下加"以 99-reconciliation 为准"覆盖声明 |
| 10 (A0) | §2.1-2.4 全部单数名 → 复数名（`student_portfolios`/`student_growth_records`/`report_snapshots`/`assessment_comments`）；字段按 §4.1 微调（补 `updated_at`/`class_id`、`created_by` 可空） |
| 11 (B0) | 表结构与 00 对齐已完成（00 改从 B0），B0 本身无需改 DDL；补充声明"assessment 三表 00 §5.5-5.7 已废弃，以 B0 为准" |
| 12 (C0) | §6.1 `student_growth_records` 反推定义**删除**，改为引用本文件 §4.1.2（A0 版），写入字段映射：`event_type→source_type`、`event_title→note`、`score_change→growth_points`、`event_date→occurred_at`；`recorded_by→created_by`（可空）。§6.3 事务边界不变 |

**C0 画像联动写入映射（正式版）**：

```
badge_award        → source_type='badge_award', source_id=badge_awards.id,  dimension=badge.category,  growth_points=badge.points_awarded
practice_record    → source_type='practice_record', source_id=practice_records.id,  dimension=映射表,  growth_points=+50(可配置)
club_activity      → source_type='club_activity',  source_id=club_attendance.id,  dimension=映射,  growth_points=+30(可配置)
reading_record     → source_type='reading_record', source_id=reading_records.id,   dimension='intellectual', growth_points=+20(可配置)
health_check       → source_type='health_check',  source_id=health_checks.id,     dimension='physical', growth_points=0(仅留痕)
credit_transaction → 不写 growth_record（积分流水非成长事件）
redemption_record  → 不写 growth_record
```

---

## 6. 表所有权划分（Wave 1 分工）

| 域 | Agent | 建表 | 实现内容 |
|----|-------|------|---------|
| A 画像 | A-agent（worktree-A） | 4.1 四表 + ALTER 现有 3 表 + `mentors` | 7 智育事件引擎、双轨制评分、班级百分位/五档/z-score、画像 GET/重算、学期报告快照版本链、AI 评语（禁词闸门）、reportlab PDF |
| B 测评 | B-agent（worktree-B） | 4.2 四表 | 题组 CRUD、施测会话状态机、作答计分、白名单标签、监护人同意、家长-学生绑定、种子题组 |
| C 运营 | C-agent（worktree-C） | 4.3 十三表 + `student_tasks` | 争章颁章/撤销/批量、学分银行/流水/对账、兑换库存(SELECT FOR UPDATE)+审核发放、校外实践审核、校园生活（社团/图书/健康）、图片上传、画像联动写入（消费方） |

**集成收口（integration-agent）**：统一挂载三个 router 到 `app/main.py` + 注册 models 到 `app/models/__init__.py` + 生产 DDL 脚本 `docs/migrations/` 汇总 + 全量验收。

---

## 7. 实施前置检查点（Wave 1 各 agent 开工前必查）

1. **ALTER 幂等**：`exam_scores`/`wrong_questions`/`students` 现有列清单，用 `information_schema` 核对，避免重复加列。
2. **智育事件 SQL 依赖列**：A 的 7 事件 SQL 用到的 `exam_scores.subject`、`exam_scores.class_avg/class_rank`、`exams.exam_date`、`wrong_questions.status/corrected_at/knowledge_point_id` 必须与实际 schema 对齐；`subject` 若在 `exams` 表而非 `exam_scores`，JOIN 时调整。
3. **C 的 `credit_transactions.transaction_type` 枚举**：默认含 `badge_award/manual_add/redemption/manual_deduct/adjustment/expire`；自动入账场景后续扩展枚举，不改表结构。
4. **`targeted_improvement_reports` 表**：确认叙阅现有表名与 `generated_at` 列（A 的智育事件 3 依赖）。
5. **models 注册顺序**：A/B/C 三个 agent 各自 `app/models/<domain>/*.py`，**只新建文件，不改** `app/models/__init__.py` 与 `app/main.py`；由 integration-agent 统一收口注册，避免并行冲突。
