# -*- coding: utf-8 -*-
"""家长端演示数据造数（parent@grade.local + 家长-学生绑定 + 五育成长记录）。

生成一个「家长」角色演示账号，绑定到若干演示学生，并为这些学生写入五育成长记录，
使「家长端 → 孩子五育画像」有数据可看（radar / 最近成长记录 / 学期报告摘要）。

数据库连接凭据不写入本文件：复用后端根目录 `.env`（app.config.Settings 自动加载），
因此需在 backend 根目录下运行（否则 `_get_env_file()` 找不到 `.env`）。

幂等：
  - 用户按 email 幂等；parent_students 有 UNIQUE(parent_id, student_id)；
  - 成长记录按 (source_type, source_id) 幂等（重复运行不翻倍）。
用法：cd grade-buddy-scan-back_end && python scripts/seed_parent_demo.py
"""
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
from app.utils.security import hash_password  # noqa: E402

PARENT_EMAIL = "parent@grade.local"
PARENT_PASSWORD = "demo123"
PARENT_DISPLAY_NAME = "演示家长"
PARENT_ROLE = "家长"
BOUND_STUDENT_COUNT = 3

# 五育成长记录样例：(维度, 内容说明, 成长点)。source_id 幂等。
GROWTH_SAMPLES = [
    ("moral", "主动帮助同学整理图书角", 3),
    ("moral", "参与班级志愿服务并获得表扬", 4),
    ("intellectual", "数学单元测验进步明显", 5),
    ("intellectual", "完成一次高质量的项目式作业", 4),
    ("physical", "校运动会 50 米跑进入决赛", 4),
    ("physical", "坚持晨跑打卡满两周", 3),
    ("aesthetic", "美术作品入选班级展板", 3),
    ("aesthetic", "参与校园合唱节排练", 4),
    ("labor", "独立完成家务劳动打卡", 3),
    ("labor", "参与校园种植园劳动实践", 4),
]


def _iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def main():
    out_lines = ["=== seed_parent_demo ==="]

    with engine.begin() as conn:
        # 1. 家长账号（email 幂等）
        row = conn.execute(
            text("SELECT id FROM users WHERE email = :e"), {"e": PARENT_EMAIL}
        ).first()
        if row:
            parent_id = row[0]
            out_lines.append(f"parent exists: {parent_id}")
        else:
            parent_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, display_name, roles) "
                    "VALUES (:id, :email, :ph, :name, :roles)"
                ),
                {
                    "id": parent_id,
                    "email": PARENT_EMAIL,
                    "ph": hash_password(PARENT_PASSWORD),
                    "name": PARENT_DISPLAY_NAME,
                    "roles": PARENT_ROLE,
                },
            )
            out_lines.append(f"parent created: {parent_id}")

        # 2. 选取绑定学生（演示班，确定性排序）
        students = conn.execute(
            text(
                "SELECT s.id, s.name, s.class_id, s.school_id AS s_school, "
                "       c.name AS class_name, c.school_id AS c_school "
                "FROM students s JOIN classes c ON c.id = s.class_id "
                "WHERE c.name LIKE '演示-%' "
                "ORDER BY s.class_id, s.id LIMIT :n"
            ),
            {"n": BOUND_STUDENT_COUNT},
        ).all()
        out_lines.append(f"bound students: {len(students)}")

        # 3. 家长-学生绑定 + 成长记录
        created_bindings = 0
        created_records = 0
        base = datetime.now(timezone.utc) - timedelta(days=12)
        for (sid, sname, class_id, s_school, class_name, c_school) in students:
            school_id = s_school or c_school
            exists = conn.execute(
                text("SELECT id FROM parent_students WHERE parent_id = :p AND student_id = :s"),
                {"p": parent_id, "s": sid},
            ).first()
            if not exists:
                conn.execute(
                    text(
                        "INSERT INTO parent_students "
                        "(id, parent_id, student_id, relation, status, created_by) "
                        "VALUES (:id, :p, :s, 'guardian', 'active', :cb)"
                    ),
                    {"id": str(uuid.uuid4()), "p": parent_id, "s": sid, "cb": parent_id},
                )
                created_bindings += 1

            for i, (dim, note, pts) in enumerate(GROWTH_SAMPLES):
                source_id = f"demo_parent_{sid[:8]}_{dim}_{i}"
                exists = conn.execute(
                    text(
                        "SELECT id FROM student_growth_records "
                        "WHERE source_type = 'manual' AND source_id = :sid"
                    ),
                    {"sid": source_id},
                ).first()
                if exists:
                    continue
                occurred = base + timedelta(days=i, hours=(i * 3) % 24)
                conn.execute(
                    text(
                        "INSERT INTO student_growth_records "
                        "(id, student_id, class_id, school_id, dimension, source_type, "
                        " source_id, growth_points, note, created_by, occurred_at) "
                        "VALUES (:id, :sid, :cid, :sch, :dim, 'manual', :src, :pts, :note, :cb, :occ)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "sid": sid,
                        "cid": class_id,
                        "sch": school_id,
                        "dim": dim,
                        "src": source_id,
                        "pts": pts,
                        "note": note,
                        "cb": parent_id,
                        "occ": _iso(occurred),
                    },
                )
                created_records += 1

            out_lines.append(f"  student {sname} ({class_name}) ok")

        out_lines.append(f"created_bindings={created_bindings}")
        out_lines.append(f"created_records={created_records}")

        # 4. 汇总
        total_bindings = conn.execute(
            text("SELECT COUNT(*) FROM parent_students WHERE parent_id = :p"),
            {"p": parent_id},
        ).scalar()
        total_records = conn.execute(
            text(
                "SELECT COUNT(*) FROM student_growth_records "
                "WHERE student_id IN (SELECT student_id FROM parent_students WHERE parent_id = :p)"
            ),
            {"p": parent_id},
        ).scalar()
        out_lines.append(f"total_bindings={total_bindings}")
        out_lines.append(f"total_records={total_records}")

    out_path = ROOT / "scripts" / "seed_parent_out.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"done -> {out_path}")


if __name__ == "__main__":
    main()
