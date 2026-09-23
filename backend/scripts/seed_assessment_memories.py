# -*- coding: utf-8 -*-
"""多元评价 + 成长印记 + 学期评语 + 报告快照 造数（Task #17）。

目标：演示-小学三年级 1~4 班（204 名学生），让 五育画像/多元评价/成长印记/学期报告 对演示账号有数据。
前端五育画像三块面板（AiCommentPanel / SemesterReportPanel / SelectionPanel）硬编码默认学期
"2025-2026-1"，故本脚本统一把演示数据对齐到该学期窗口 2025-09-01 ~ 2026-01-31。

步骤：
  0. 日期回拨：把 Task #15/#16 造在 2026-07/08 的成长记录/颁章/实践日期幂等回拨到 2025-2026-1 窗口，
     使 compute_report_for_student 能聚合出有数据的学期报告。
  1. 测评题组：复用 seed_assessment_definition 服务（幂等）。
  2. 测评会话 + 锚点结果 + 逐题明细：每生一次施测，用真实计分服务 score_answers 生成 tag_schema/raw_score。
  3. AI 学期评语：每生一条 assessment_comments（term=2025-2026-1，已确认）。
  4. 成长印记：每生 2~3 条 student_memories，并生成占位图片落盘 assets/memories/。
  5. 报告快照：每生 freeze 一次（compute_report_for_student 真实聚合 + create_report_snapshot）。

幂等：
  - 日期回拨用 WHERE 日期 >= '2026-07-01' 兜底，回拨后不再命中；
  - 会话/结果/明细/印记用确定性 uuid5 主键 + 存在性检查；
  - 评语按 (student_id, term) 唯一，快照按 (student_id, term) 存在性检查。
凭据复用后端根目录 .env，需在 backend 根目录运行。
用法：cd grade-buddy-scan-back_end && python scripts/seed_assessment_memories.py
"""
import hashlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.assessment_session import AssessmentSession  # noqa: E402
from app.models.assessment_result import AssessmentResult  # noqa: E402
from app.models.assessment_answer import AssessmentAnswer  # noqa: E402
from app.models.assessment_comment import AssessmentComment  # noqa: E402
from app.models.student_memory import StudentMemory  # noqa: E402
from app.services.assessment.seed import seed_assessment_definition, SEED_QUESTIONS  # noqa: E402
from app.services.assessment.scoring import (  # noqa: E402
    score_answers, build_tag_schema, build_raw_score, default_guardian_consent,
)
from app.services.portfolio.repository import PortfolioRepository  # noqa: E402

TARGET_GRADE = "小学三年级"
TERM = "2025-2026-1"           # 前端五育画像三面板默认学期
TERM_FROM = "2025-09-01"
TERM_DAYS = 152                # 2025-09-01 ~ 2026-01-31

MEMORY_ROOT = ROOT / "assets" / "memories"
MEMORY_MONTH = "2025-09"       # 与学期窗口一致

# 占位图调色板（12 色），成长印记复用
PALETTE = [
    (244, 162, 97), (231, 111, 81), (244, 140, 6), (233, 196, 106),
    (42, 157, 143), (38, 70, 83), (58, 134, 255), (67, 97, 238),
    (231, 111, 150), (147, 129, 255), (128, 185, 120), (150, 170, 190),
]

MEMORY_CAPTIONS = [
    "课堂上专注完成练习", "参加校园劳动实践", "运动会上的精彩瞬间",
    "美术课创作作品", "课外阅读时光", "班级合唱排练",
    "科技节动手实验", "志愿服务中的身影", "研学活动留影", "体育课锻炼瞬间",
]


def _seed_int(sid: str) -> int:
    return int(hashlib.md5(sid.encode()).hexdigest(), 16)


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def rebase_dates_to_term(db) -> dict:
    """把 2026-07 之后的演示日期幂等回拨到 2025-2026-1 窗口。"""
    n = {}
    n["growth"] = db.execute(
        text(
            "UPDATE student_growth_records SET occurred_at = "
            "DATE_ADD(:frm, INTERVAL (CRC32(id) % :days) DAY) "
            "WHERE occurred_at >= '2026-07-01'"
        ), {"frm": f"{TERM_FROM} 08:00:00", "days": TERM_DAYS},
    ).rowcount
    n["badge"] = db.execute(
        text(
            "UPDATE badge_awards SET award_date = "
            "DATE_ADD(:frm, INTERVAL (CRC32(id) % :days) DAY) "
            "WHERE award_date >= '2026-07-01'"
        ), {"frm": TERM_FROM, "days": TERM_DAYS},
    ).rowcount
    n["practice"] = db.execute(
        text(
            "UPDATE practice_records SET practice_date = "
            "DATE_ADD(:frm, INTERVAL (CRC32(id) % :days) DAY) "
            "WHERE practice_date >= '2026-07-01'"
        ), {"frm": TERM_FROM, "days": TERM_DAYS},
    ).rowcount
    n["credit"] = db.execute(
        text(
            "UPDATE credit_transactions SET created_at = "
            "DATE_ADD(:frm, INTERVAL (CRC32(id) % :days) DAY) "
            "WHERE created_at >= '2026-07-01'"
        ), {"frm": f"{TERM_FROM} 08:00:00", "days": TERM_DAYS},
    ).rowcount
    return n


def _gen_answers(questions: list, sid: str) -> dict:
    rng = _seed_int(sid)
    answers = {}
    for i, q in enumerate(questions):
        opts = q["options"]
        k = (rng >> (i * 2)) % len(opts)
        answers[q["id"]] = opts[k]["key"]
    return answers


def seed_assessment(db, students: list, creator: str) -> dict:
    """每生一次施测：session + result + 逐题明细（真实计分）。"""
    definition = seed_assessment_definition(db)  # 幂等，返回 definition_id
    def_id = definition["definition_id"]
    n_sess = n_res = n_ans = 0
    for (sid, sname, cid, school_id, grade) in students:
        sess_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"assessment_session:{sid}"))
        exists = db.execute(
            text("SELECT id FROM assessment_sessions WHERE id = :id"), {"id": sess_id}
        ).first()
        if exists:
            continue
        # 会话时间落在学期窗口内（确定性）：2025-09-01 起偏移 day 天
        rng = _seed_int(sid)
        day = rng % TERM_DAYS
        base = datetime(2025, 9, 1, 9, 0, 0, tzinfo=timezone.utc)
        taken_at = base + timedelta(days=day, hours=(rng >> 8) % 6)
        submitted_at = taken_at + timedelta(minutes=15 + (rng >> 4) % 40)

        db.add(AssessmentSession(
            id=sess_id, student_id=sid, definition_id=def_id,
            test_mode="class_batch", batch_id=f"batch_{cid[:8]}",
            status="submitted", proctored_by=creator, created_by=creator,
            taken_at=taken_at, submitted_at=submitted_at,
        ))
        n_sess += 1
        # 先落 session，result.session_id 外键才能引用
        db.flush()

        answers = _gen_answers(SEED_QUESTIONS, sid)
        score = score_answers(SEED_QUESTIONS, answers)
        tag_schema = build_tag_schema(score, generated_at=_iso(submitted_at))
        raw_score = build_raw_score(SEED_QUESTIONS, answers, score)
        consent = default_guardian_consent()

        res_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"assessment_result:{sid}"))
        db.add(AssessmentResult(
            id=res_id, student_id=sid, definition_id=def_id, session_id=sess_id,
            domain="self_built_survey", purpose="anchor",
            tag_schema=tag_schema, raw_score=raw_score, guardian_consent=consent,
            created_by=creator,
        ))
        n_res += 1
        # 先落库 session+result，answers.result_id 外键才能引用
        db.flush()

        for q in SEED_QUESTIONS:
            qid = q["id"]
            opt_key = answers.get(qid)
            if not opt_key:
                continue
            selected = next((o for o in q["options"] if o["key"] == opt_key), None)
            if not selected:
                continue
            db.add(AssessmentAnswer(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"assessment_answer:{res_id}:{qid}")),
                result_id=res_id, question_id=qid, option_key=opt_key,
                dim=q["dim"], option_dim=selected.get("dim"),
            ))
            n_ans += 1
    return {"definition_id": def_id, "sessions": n_sess, "results": n_res, "answers": n_ans}


def _build_comment(name: str, sid: str) -> str:
    rng = _seed_int(sid)
    openers = [
        f"{name}同学在本学期表现出良好的成长势头，",
        f"{name}同学本学期整体状态积极向上，",
        f"{name}同学在各方面都有可喜的进步，",
    ]
    moral = ["遵守纪律、乐于助人，与同学相处融洽", "责任心强，主动承担班级事务",
            "文明有礼，积极参与品德实践活动"]
    intel = ["学习态度端正，课堂参与积极，作业完成认真", "善于思考，能主动提出问题并寻求解答",
            "学习习惯良好，成绩稳步提升"]
    phys = ["积极参加体育锻炼，体质健康状态良好", "运动习惯逐渐养成，精神面貌饱满",
            "作息规律，能坚持日常锻炼"]
    aest = ["审美感受力强，在艺术活动中表现投入", "兴趣爱好广泛，乐于参与美育活动",
            "有较好的艺术表现力，创作积极"]
    labor = ["热爱劳动，能独立完成力所能及的家务", "劳动实践主动，动手能力较强",
            "珍惜劳动成果，责任意识逐步增强"]
    closers = ["希望继续保持，在新学期取得更大进步。", "期待你在新的学期继续努力、全面发展。",
              "相信只要坚持，你一定会收获更多成长。"]
    o = rng % len(openers)
    return (
        openers[o]
        + f"德育方面，{moral[(rng >> 2) % 3]}；"
        + f"智育方面，{intel[(rng >> 4) % 3]}；"
        + f"体育方面，{phys[(rng >> 6) % 3]}；"
        + f"美育方面，{aest[(rng >> 8) % 3]}；"
        + f"劳动方面，{labor[(rng >> 10) % 3]}。"
        + closers[(rng >> 12) % 3]
    )


def seed_comments(db, students: list, creator: str) -> int:
    n = 0
    for (sid, sname, cid, school_id, grade) in students:
        exists = db.execute(
            text("SELECT id FROM assessment_comments WHERE student_id=:s AND term=:t"),
            {"s": sid, "t": TERM},
        ).first()
        if exists:
            continue
        content = _build_comment(sname, sid)
        db.add(AssessmentComment(
            student_id=sid, class_id=cid, school_id=school_id or None, term=TERM,
            status="confirmed", ai_content=content, confirmed_content=content,
            ai_model="demo-seed", tokens_used=0, cost_cent=0, gate_flagged=False,
            created_by=creator, confirmed_by=creator,
            confirmed_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        ))
        n += 1
    return n


def _ensure_palette_images() -> dict:
    """生成 12 张占位图（原图 + 缩略图），返回 {index: rel_path}。"""
    from PIL import Image, ImageDraw

    month_dir = MEMORY_ROOT / MEMORY_MONTH
    thumb_dir = month_dir / "thumb"
    month_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for i, color in enumerate(PALETTE):
        fname = f"demo_{i:02d}.png"
        fpath = month_dir / fname
        tpath = thumb_dir / fname
        if not fpath.exists():
            img = Image.new("RGB", (320, 240), color)
            d = ImageDraw.Draw(img)
            d.rectangle([18, 16, 302, 224], outline=(255, 255, 255), width=5)
            d.rectangle([26, 24, 294, 216], outline=(255, 255, 255), width=1)
            img.save(fpath)
        if not tpath.exists():
            thumb = Image.open(fpath)
            thumb.thumbnail((160, 120))
            thumb.save(tpath)
        paths[i] = f"{MEMORY_MONTH}/{fname}"
    return paths


def seed_memories(db, students: list, creator: str) -> int:
    paths = _ensure_palette_images()
    n = 0
    for (sid, sname, cid, school_id, grade) in students:
        rng = _seed_int(sid)
        count = 2 + (rng % 2)  # 2~3 条
        for j in range(count):
            mid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"memory:{sid}:{j}"))
            exists = db.execute(
                text("SELECT id FROM student_memories WHERE id=:id"), {"id": mid}
            ).first()
            if exists:
                continue
            ci = (rng >> (j * 4)) % len(PALETTE)
            cap = MEMORY_CAPTIONS[(rng >> (j * 4 + 2)) % len(MEMORY_CAPTIONS)]
            day = (rng >> (j * 3)) % TERM_DAYS
            created = datetime(2025, 9, 1, 10, 0, 0, tzinfo=timezone.utc) + \
                timedelta(days=day, hours=(rng >> (j * 3 + 5)) % 8)
            db.add(StudentMemory(
                id=mid, student_id=sid, class_id=cid, school_id=school_id or None,
                image_path=paths[ci], caption=cap, source_type="memory",
                created_by=creator, created_at=created,
            ))
            n += 1
    return n


def seed_report_snapshots(db, repo: PortfolioRepository, students: list, creator: str) -> int:
    n = 0
    for (sid, sname, cid, school_id, grade) in students:
        exists = db.execute(
            text("SELECT id FROM report_snapshots WHERE student_id=:s AND term=:t LIMIT 1"),
            {"s": sid, "t": TERM},
        ).first()
        if exists:
            continue
        student = {"id": sid, "name": sname, "class_id": cid}
        term_from = datetime(2025, 9, 1, tzinfo=timezone.utc)
        term_to = datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc)
        report = repo.compute_report_for_student(student, TERM, term_from, term_to, grade=grade)
        snap = repo.create_report_snapshot(
            student_id=sid, term=TERM, class_id=cid, school_id=school_id or None,
            payload=report, generated_by=creator,
        )
        if snap:
            n += 1
    return n


def main():
    out_lines = ["=== seed_assessment_memories ==="]
    db = SessionLocal()
    try:
        creator = db.execute(
            text("SELECT id FROM users WHERE email='headteacher@grade.local'")
        ).first()
        creator = creator[0]
        out_lines.append(f"creator(headteacher)={creator}")

        students = db.execute(
            text(
                "SELECT s.id, s.name, s.class_id, s.school_id, c.grade FROM students s "
                "JOIN classes c ON c.id=s.class_id WHERE c.grade=:g ORDER BY c.name, s.id"
            ),
            {"g": TARGET_GRADE},
        ).all()
        out_lines.append(f"students={len(students)}")

        # 0. 日期回拨（幂等）
        rebased = rebase_dates_to_term(db)
        out_lines.append(f"rebase_dates: growth={rebased['growth']} badge={rebased['badge']} practice={rebased['practice']} credit={rebased['credit']}")

        # 1~2. 测评题组 + 会话/结果/明细
        a = seed_assessment(db, students, creator)
        out_lines.append(f"assessment: def={a['definition_id']} sessions={a['sessions']} results={a['results']} answers={a['answers']}")

        # 3. 评语
        n_cmt = seed_comments(db, students, creator)
        out_lines.append(f"comments={n_cmt}")

        # 4. 成长印记
        n_mem = seed_memories(db, students, creator)
        out_lines.append(f"memories={n_mem}")

        db.commit()

        # 5. 报告快照（内部 commit）
        repo = PortfolioRepository(db)
        n_snap = seed_report_snapshots(db, repo, students, creator)
        out_lines.append(f"report_snapshots={n_snap}")

        for tbl in ["assessment_definitions", "assessment_sessions", "assessment_results",
                    "assessment_answers", "assessment_comments", "student_memories", "report_snapshots"]:
            cnt = db.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            out_lines.append(f"  {tbl}={cnt}")

        # 抽查一个学生的报告 total_growth_point
        if students:
            sid0 = students[0][0]
            gpt = db.execute(
                text("SELECT payload->>'$.total_growth_point' FROM report_snapshots WHERE student_id=:s AND term=:t"),
                {"s": sid0, "t": TERM},
            ).scalar()
            out_lines.append(f"sample report total_growth_point={gpt}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    out_path = ROOT / "scripts" / "seed_assessment_memories_out.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"done -> {out_path}")


if __name__ == "__main__":
    main()
