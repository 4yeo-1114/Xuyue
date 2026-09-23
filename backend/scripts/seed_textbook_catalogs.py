# -*- coding: utf-8 -*-
"""R4 备课 MVP：教材目录 seed（textbook_catalogs 表）。

在本地主库（.env 配置：127.0.0.1:3306/grade）为「语文/数学/英语」各 seed 一版
人教版七年级上册教材目录（edition 顶层节点 + 若干 unit 子节点，数学 ≥5 个单元）。

幂等：按 (subject, edition, name) 自然键查重，已存在则跳过；可重复运行。
脚本同时幂等兜底建表（textbook_catalogs）与补列（lesson_plans 新教材字段），
与 app/database.py 的 _ensure 模式一致。

用法：python scripts/seed_textbook_catalogs.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text  # noqa: E402

from app.database import engine, _ensure_lesson_plan_extra_columns, _ensure_textbook_catalogs_table  # noqa: E402
from app.models.user import gen_uuid  # noqa: E402

# 各学科 seed 的教材目录（edition 顶层 + units 子节点，unit 为 (名称, 序号)）
CATALOGS = {
    "数学": {
        "edition": "人教版",
        "grade": "七年级",
        "name": "人教版数学七年级上册",
        "units": [
            ("第一章 有理数", 1),
            ("第二章 整式的加减", 2),
            ("第三章 一元一次方程", 3),
            ("第四章 几何图形初步", 4),
            ("第五章 相交线与平行线", 5),
            ("第六章 实数", 6),
        ],
    },
    "语文": {
        "edition": "人教版",
        "grade": "七年级",
        "name": "人教版语文七年级上册",
        "units": [
            ("第一单元 四季美景", 1),
            ("第二单元 至爱亲情", 2),
            ("第三单元 学习生活", 3),
            ("第四单元 人生之舟", 4),
            ("第五单元 动物与人", 5),
            ("第六单元 想象之翼", 6),
        ],
    },
    "英语": {
        "edition": "人教版",
        "grade": "七年级",
        "name": "人教版英语七年级上册",
        "units": [
            ("Starter Unit 1 Good morning!", 1),
            ("Starter Unit 2 What's this in English?", 2),
            ("Starter Unit 3 What color is it?", 3),
            ("Unit 1 My name's Gina.", 4),
            ("Unit 2 This is my sister.", 5),
            ("Unit 3 Is this your pencil?", 6),
        ],
    },
}


def seed():
    # 幂等建表 / 补列（对应 app/database.py 的 _ensure 模式）
    _ensure_textbook_catalogs_table()
    _ensure_lesson_plan_extra_columns()

    total = 0
    with engine.begin() as conn:
        for subject, spec in CATALOGS.items():
            edition = spec["edition"]
            grade = spec["grade"]
            top_name = spec["name"]

            # 顶层 edition 节点（parent_id NULL）
            existing = conn.execute(
                text(
                    "SELECT id FROM textbook_catalogs "
                    "WHERE subject = :s AND edition = :e AND level = 'edition' AND name = :n"
                ),
                {"s": subject, "e": edition, "n": top_name},
            ).first()
            if existing:
                top_id = existing[0]
            else:
                top_id = gen_uuid()
                conn.execute(
                    text(
                        "INSERT INTO textbook_catalogs "
                        "(id, name, subject, edition, grade, level, unit_index, parent_id) "
                        "VALUES (:id, :n, :s, :e, :g, 'edition', NULL, NULL)"
                    ),
                    {"id": top_id, "n": top_name, "s": subject, "e": edition, "g": grade},
                )
                total += 1

            # unit 子节点（parent_id 指向 edition 节点）
            for name, idx in spec["units"]:
                ex = conn.execute(
                    text(
                        "SELECT id FROM textbook_catalogs "
                        "WHERE subject = :s AND edition = :e AND parent_id = :p AND name = :n"
                    ),
                    {"s": subject, "e": edition, "p": top_id, "n": name},
                ).first()
                if ex:
                    continue
                conn.execute(
                    text(
                        "INSERT INTO textbook_catalogs "
                        "(id, name, subject, edition, grade, level, unit_index, parent_id) "
                        "VALUES (:id, :n, :s, :e, :g, 'unit', :idx, :p)"
                    ),
                    {"id": gen_uuid(), "n": name, "s": subject, "e": edition, "g": grade,
                     "idx": idx, "p": top_id},
                )
                total += 1

    print(f"seed 完成：本次新增 {total} 行")
    with engine.connect() as conn:
        for subject in CATALOGS:
            n = conn.execute(
                text("SELECT COUNT(*) FROM textbook_catalogs WHERE subject = :s"), {"s": subject}
            ).scalar()
            print(f"  {subject}: {n} 行")


if __name__ == "__main__":
    seed()
