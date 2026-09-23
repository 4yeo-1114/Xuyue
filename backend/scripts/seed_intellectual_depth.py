# -*- coding: utf-8 -*-
"""智育深度造数 + 报告快照重生成（Task #18）。

前端五育画像三面板硬编码默认学期 "2025-2026-1"。智育深度数据（成绩/错题/靶向报告）此前
落在 2026-03~08（下学期/暑假），导致学期报告的 milestones / 智育 detail / auto_points 对演示账号为空。
本脚本补全并回拨到 2025-2026-1 窗口（2025-09-01 ~ 2026-01-31）。

步骤：
  1. 幂等回拨日期：exams.exam_date、targeted_improvement_reports.generated_at → 学期窗口。
     成绩已具备 score/class_avg/class_rank，回拨后 report 的 exam_rank_up / above_class_avg 事件即触发。
  2. 造 wrong_questions（沿用 raw_intellectual_events 实际读取的 wrong_questions 表）：
     每生 5 题（4 订正 + 1 未订正，订正率 80% 触发 correction_rate_high），
     订正题带 knowledge_point_id（触发 weak_point_conquered）。
  3. 造 targeted_improvement_reports（三年级此前为 0）：每生 语/数 各 1 份（触发 targeted_report）。
  4. 删除并重生成 report_snapshots（旧快照 milestones 为空），使智育 detail/milestones 有数据。

幂等：
  - 日期回拨用 WHERE 日期 >= '2026-03-01' 兜底；
  - 错题/靶向报告用确定性 uuid5 主键 + 存在性检查；
  - 快照重生成 = 先删 term=2025-2026-1 全部快照再重建（派生数据，可安全重建）。
凭据复用后端 .env；需在 backend 根目录运行。
用法：cd grade-buddy-scan-back_end && python scripts/seed_intellectual_depth.py
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
from app.services.portfolio.repository import PortfolioRepository  # noqa: E402

TARGET_GRADE = "小学三年级"
TERM = "2025-2026-1"
TERM_FROM = "2025-09-01"
TERM_DAYS = 152  # 2025-09-01 ~ 2026-01-31

SUBJECTS = ["语文", "数学", "英语"]

# 每科错题模板：题目 / 正确答案 / 错误答案 / 错误类型 / 解析
WQ_POOL = {
    "语文": [
        ("选出下列词语中书写有误的一项", "B", "A", "形近字混淆", "形近字需结合偏旁辨析字义。"),
        ("给加点字选择正确的读音", "C", "B", "字音误读", "注意多音字在词语中的读音规律。"),
        ("把句子补充完整", "示例答案", "答案不完整", "审题不清", "作答前先圈出题目要求的关键词。"),
    ],
    "数学": [
        ("计算：1/4 + 1/2 = ?", "3/4", "1/3", "分数加减法未通分", "异分母分数相加需先通分再相加。"),
        ("解方程：3x + 5 = 20", "x = 5", "x = 15", "方程求解", "等式两边先同时减去常数项，再除以系数。"),
        ("求边长为 6cm 的正方形面积", "36cm²", "24cm²", "面积计算", "正方形面积 = 边长 × 边长。"),
    ],
    "英语": [
        ("He ___ to school every day.", "goes", "go", "三单形式错误", "主语为第三人称单数时，动词需加 -s/-es。"),
        ("She is ___ now.", "reading", "read", "现在进行时", "be + 动词-ing 构成现在进行时。"),
        ("There ___ a book on the desk.", "is", "are", "主谓一致", "there be 句型中 be 与最近的名词单复数一致。"),
    ],
}

# 靶向报告模板（诊断 / 提升计划）
TARGETED_SUBJECTS = ["语文", "数学"]
DIAGNOSIS = "本学科在{weak}等知识点上存在薄弱环节，建议针对性巩固。"
PLAN = "1) 每日完成{weak}专项练习 10 分钟；2) 每周复习错题本；3) 结合靶向报告查漏补缺。"


def _seed_int(sid: str) -> int:
    return int(hashlib.md5(sid.encode()).hexdigest(), 16)


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def rebase_dates(db) -> dict:
    n = {}
    n["exams"] = db.execute(
        text(
            "UPDATE exams SET exam_date = DATE_ADD(:frm, INTERVAL (CRC32(id) % :days) DAY) "
            "WHERE exam_date >= '2026-03-01'"
        ), {"frm": TERM_FROM, "days": TERM_DAYS},
    ).rowcount
    n["targeted"] = db.execute(
        text(
            "UPDATE targeted_improvement_reports SET generated_at = "
            "DATE_ADD(:frm, INTERVAL (CRC32(id) % :days) DAY) "
            "WHERE generated_at >= '2026-03-01'"
        ), {"frm": f"{TERM_FROM} 08:00:00", "days": TERM_DAYS},
    ).rowcount
    return n


def _kp_lists(db) -> dict:
    """按科目归类知识点 id。"""
    kps = db.execute(text("SELECT id, code, name FROM knowledge_points")).all()
    out = {"语文": [], "数学": [], "英语": [], "_all": []}
    for kp_id, code, name in kps:
        out["_all"].append(kp_id)
        c = (code or "") + (name or "")
        if "语文" in c:
            out["语文"].append(kp_id)
        elif (code or "").startswith("SX") or "数学" in c:
            out["数学"].append(kp_id)
        elif (code or "").startswith("YY") or "英语" in c:
            out["英语"].append(kp_id)
    return out


def seed_wrong_questions(db, students: list, creator: str, kp_lists: dict) -> int:
    n = 0
    for (sid, sname, snum, cid, school_id, grade) in students:
        rng = _seed_int(sid)
        for j in range(5):
            wq_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"wrong_q:{sid}:{j}"))
            exists = db.execute(
                text("SELECT id FROM wrong_questions WHERE id=:id"), {"id": wq_id}
            ).first()
            if exists:
                continue
            subject = SUBJECTS[(rng >> (j * 2)) % len(SUBJECTS)]
            pool = WQ_POOL[subject]
            q_content, correct, wrong, err_type, analysis = pool[(rng >> (j * 3)) % len(pool)]
            is_corrected = j < 4  # 前 4 题已订正，第 5 题未订正
            day = (rng >> (j * 4 + 1)) % TERM_DAYS
            created = datetime(2025, 9, 1, 10, 0, 0, tzinfo=timezone.utc) + \
                timedelta(days=day, hours=(rng >> (j + 2)) % 8)
            corrected_at = created + timedelta(days=1, hours=(rng >> (j + 5)) % 10) \
                if is_corrected else None
            kp_list = kp_lists.get(subject) or kp_lists["_all"]
            kp_id = kp_list[(rng >> (j * 5 + 3)) % len(kp_list)] if kp_list else None
            db.execute(
                text(
                    "INSERT INTO wrong_questions "
                    "(id, user_id, student_id, class_id, school_id, subject, "
                    " question_content, correct_answer, student_answer, error_type, analysis, "
                    " knowledge_point_id, status, corrected_at, created_at) "
                    "VALUES (:id, :uid, :sid, :cid, :sch, :subj, :q, :ca, :sa, :et, :an, "
                    " :kp, :st, :co, :cr)"
                ),
                {
                    "id": wq_id, "uid": creator, "sid": sid, "cid": cid, "sch": school_id or None,
                    "subj": subject, "q": q_content, "ca": correct, "sa": wrong,
                    "et": err_type, "an": analysis, "kp": kp_id,
                    "st": "corrected" if is_corrected else "open",
                    "co": corrected_at, "cr": created,
                },
            )
            n += 1
    return n


def seed_targeted_reports(db, students: list, creator: str) -> int:
    n = 0
    for (sid, sname, snum, cid, school_id, grade) in students:
        rng = _seed_int(sid)
        for ti, subj in enumerate(TARGETED_SUBJECTS):
            tr_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"targeted:{sid}:{subj}"))
            exists = db.execute(
                text("SELECT id FROM targeted_improvement_reports WHERE id=:id"),
                {"id": tr_id},
            ).first()
            if exists:
                continue
            weak = {"语文": "阅读理解", "数学": "分数运算"}[subj]
            day = (rng >> (ti * 4 + 7)) % TERM_DAYS
            generated = datetime(2025, 9, 1, 9, 0, 0, tzinfo=timezone.utc) + \
                timedelta(days=day, hours=(rng >> (ti + 9)) % 8)
            db.execute(
                text(
                    "INSERT INTO targeted_improvement_reports "
                    "(id, class_id, student_id, student_name, student_number, subject, "
                    " diagnosis_text, plan_text, generated_at) "
                    "VALUES (:id, :cid, :sid, :sn, :snum, :subj, :diag, :plan, :gen)"
                ),
                {
                    "id": tr_id, "cid": cid, "sid": sid, "sn": sname, "snum": snum,
                    "subj": subj, "diag": DIAGNOSIS.format(weak=weak),
                    "plan": PLAN.format(weak=weak), "gen": generated,
                },
            )
            n += 1
    return n


def regenerate_snapshots(db, repo: PortfolioRepository, students: list, creator: str) -> tuple:
    deleted = db.execute(
        text("DELETE FROM report_snapshots WHERE term=:t"), {"t": TERM}
    ).rowcount
    db.commit()
    n = 0
    for (sid, sname, snum, cid, school_id, grade) in students:
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
    return deleted, n


def main():
    out_lines = ["=== seed_intellectual_depth ==="]
    db = SessionLocal()
    try:
        creator = db.execute(
            text("SELECT id FROM users WHERE email='headteacher@grade.local'")
        ).first()
        creator = creator[0]
        out_lines.append(f"creator={creator}")

        students = db.execute(
            text(
                "SELECT s.id, s.name, s.student_number, s.class_id, s.school_id, c.grade "
                "FROM students s JOIN classes c ON c.id=s.class_id "
                "WHERE c.grade=:g ORDER BY c.name, s.id"
            ),
            {"g": TARGET_GRADE},
        ).all()
        out_lines.append(f"students={len(students)}")

        rebased = rebase_dates(db)
        out_lines.append(f"rebase_dates: exams={rebased['exams']} targeted={rebased['targeted']}")

        kp_lists = _kp_lists(db)
        n_wq = seed_wrong_questions(db, students, creator, kp_lists)
        out_lines.append(f"wrong_questions={n_wq}")

        n_tr = seed_targeted_reports(db, students, creator)
        out_lines.append(f"targeted_reports={n_tr}")

        db.commit()

        repo = PortfolioRepository(db)
        deleted, n_snap = regenerate_snapshots(db, repo, students, creator)
        out_lines.append(f"report_snapshots: deleted={deleted} regenerated={n_snap}")

        for tbl in ["wrong_questions", "targeted_improvement_reports", "report_snapshots"]:
            cnt = db.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            out_lines.append(f"  {tbl}={cnt}")

        # 抽查首个学生报告：milestones / intellectual detail
        if students:
            sid0 = students[0][0]
            p = db.execute(
                text("SELECT payload FROM report_snapshots WHERE student_id=:s AND term=:t ORDER BY version DESC LIMIT 1"),
                {"s": sid0, "t": TERM},
            ).scalar()
            import json
            d = json.loads(p) if isinstance(p, str) else p
            out_lines.append(f"sample milestones={len(d.get('milestones') or [])}")
            intel = (d.get('dimensions') or {}).get('intellectual') or {}
            out_lines.append(f"sample intellectual={json.dumps(intel, ensure_ascii=False)}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    out_path = ROOT / "scripts" / "seed_intellectual_depth_out.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"done -> {out_path}")


if __name__ == "__main__":
    main()
