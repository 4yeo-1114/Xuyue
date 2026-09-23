# -*- coding: utf-8 -*-
"""五育成长记录造数：为演示班学生批量写入德/智/体/美/劳/AI素养 六维成长记录。

目标：演示-小学三年级 1~4 班（班主任 headteacher@ 与任课教师 teacher@ 共同带 三年级1班），
让五育画像 / 班级总览 / 年级分析对演示账号有数据。
compute_portfolio 实时从 student_growth_records 聚合并幂等写回 student_portfolios 缓存，
因此只造成长记录即可，无需手写 student_portfolios。

幂等：source_id = demo_class_{student前8}_{dim}_{di}_{j}，重复运行不翻倍。
凭据复用后端 .env；需在 backend 根目录运行。
用法：cd grade-buddy-scan-back_end && python scripts/seed_growth_records.py
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
from app.database import engine  # noqa: E402

TARGET_GRADE = "小学三年级"  # 造 三年级 1~4 班

# 维度 → [(indicator_id, 说明, 基础成长点)]，indicator_id 对应 seed_indicators.py 的二级指标
DIM_POOLS = [
    ("moral", [
        ("ind-moral-behavior", "主动帮助同学整理图书角", 3),
        ("ind-moral-activity", "参与班级志愿服务并获得表扬", 4),
        ("ind-moral-responsibility", "认真完成值日任务", 3),
        ("ind-moral-conduct", "诚实守信受到表扬", 4),
    ]),
    ("intellectual", [
        ("ind-intellectual-grade", "数学单元测验进步明显", 5),
        ("ind-intellectual-class", "课堂积极发言", 3),
        ("ind-intellectual-homework", "作业质量优秀", 4),
        ("ind-intellectual-ability", "自主完成拓展阅读", 3),
    ]),
    ("physical", [
        ("ind-physical-fitness", "校运动会50米跑进入决赛", 4),
        ("ind-physical-habit", "坚持晨跑打卡满两周", 3),
        ("ind-physical-metrics", "视力检测达标", 2),
    ]),
    ("aesthetic", [
        ("ind-aesthetic-music", "参与校园合唱节排练", 4),
        ("ind-aesthetic-art", "美术作品入选班级展板", 3),
        ("ind-aesthetic-activity", "参加艺术展演", 4),
    ]),
    ("labor", [
        ("ind-labor-practice", "独立完成家务劳动打卡", 3),
        ("ind-labor-outdoor", "参与校园种植园劳动实践", 4),
        ("ind-labor-innovation", "完成一件手工制作", 3),
    ]),
    ("ai_literacy", [
        ("ind-ai-course", "完成AI基础课程学习", 3),
        ("ind-ai-course-task", "AI课程任务完成质量优秀", 4),
        ("ind-ai-project-idea", "AI项目创意构思清晰", 4),
    ]),
]

BASE_DAY = datetime.now(timezone.utc) - timedelta(days=40)


def _seed_int(sid: str) -> int:
    return int(hashlib.md5(sid.encode()).hexdigest(), 16)


def _iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def build_records(sid: str) -> list[dict]:
    rng = _seed_int(sid)
    recs = []
    for di, (dim, pool) in enumerate(DIM_POOLS):
        n = 1 + ((rng >> di) % 2)  # 1~2 条/维度
        for j in range(n):
            k = (rng >> (di * 3 + j)) % len(pool)
            ind_id, note, base_pts = pool[k]
            pts = max(1, min(5, base_pts + ((rng >> (di * 3 + j + 2)) % 3) - 1))
            day_off = (rng >> (di * 4 + j * 2)) % 40
            occurred = BASE_DAY + timedelta(days=day_off, hours=(rng >> (di + j)) % 9 + 8)
            source_id = f"demo_class_{sid[:8]}_{dim}_{di}_{j}"
            recs.append({
                "dim": dim, "indicator_id": ind_id, "note": note,
                "pts": pts, "source_id": source_id, "occurred": _iso(occurred),
            })
    return recs


INSERT_SQL = (
    "INSERT INTO student_growth_records "
    "(id, student_id, class_id, school_id, dimension, source_type, source_id, "
    " indicator_id, growth_points, note, created_by, occurred_at) "
    "VALUES (:id, :sid, :cid, :sch, :dim, 'manual', :src, :ind, :pts, :note, :cb, :occ)"
)


def main():
    out_lines = ["=== seed_growth_records ==="]
    with engine.begin() as conn:
        head = conn.execute(
            text("SELECT id FROM users WHERE email = 'headteacher@grade.local'")
        ).first()
        creator = head[0] if head else None

        students = conn.execute(
            text(
                "SELECT s.id, s.name, s.class_id, s.school_id AS s_school, "
                "       c.school_id AS c_school, c.name AS class_name "
                "FROM students s JOIN classes c ON c.id = s.class_id "
                "WHERE c.grade = :g ORDER BY c.name, s.id"
            ),
            {"g": TARGET_GRADE},
        ).all()

        inserted = 0
        for (sid, sname, class_id, s_school, c_school, class_name) in students:
            school_id = s_school or c_school
            for r in build_records(sid):
                exists = conn.execute(
                    text(
                        "SELECT id FROM student_growth_records "
                        "WHERE source_type = 'manual' AND source_id = :src"
                    ),
                    {"src": r["source_id"]},
                ).first()
                if exists:
                    continue
                conn.execute(
                    text(INSERT_SQL),
                    {
                        "id": str(uuid.uuid4()), "sid": sid, "cid": class_id,
                        "sch": school_id, "dim": r["dim"], "src": r["source_id"],
                        "ind": r["indicator_id"], "pts": r["pts"], "note": r["note"],
                        "cb": creator, "occ": r["occurred"],
                    },
                )
                inserted += 1
        out_lines.append(f"students={len(students)}")
        out_lines.append(f"inserted={inserted}")

        # 汇总
        per_class = conn.execute(
            text(
                "SELECT c.name, COUNT(*) FROM student_growth_records g "
                "JOIN classes c ON c.id = g.class_id WHERE c.grade = :g "
                "GROUP BY c.name ORDER BY c.name"
            ),
            {"g": TARGET_GRADE},
        ).all()
        for cn, n in per_class:
            out_lines.append(f"  {cn}: {n}")

    out_path = ROOT / "scripts" / "seed_growth_records_out.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"done -> {out_path}")


if __name__ == "__main__":
    main()
