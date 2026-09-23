# -*- coding: utf-8 -*-
"""四维定位矩阵 · 小学段教材目录补充 seed（textbook_catalogs 表）。

演示库主体是小学一到六年级（demo_seed.py 造数），但原 seed_textbook_catalogs.py
只 seed 了七年级（初中）。本脚本补齐小学段：6 个年级 × 4 科（语文/数学/英语/科学），
使四维定位矩阵的小学段单元格全部点亮可点（对齐 demo_seed.py 的 SUBJECTS）。

幂等：按 (subject, edition, grade, name) 自然键查重，已存在则跳过；可重复运行。
用法：python scripts/seed_textbook_catalogs_primary.py
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

from app.database import engine, _ensure_textbook_catalogs_table  # noqa: E402
from app.models.user import gen_uuid  # noqa: E402

PRIMARY_GRADES = [
    "小学一年级",
    "小学二年级",
    "小学三年级",
    "小学四年级",
    "小学五年级",
    "小学六年级",
]
EDITION = "人教版"

# 各科单元名（小学段通用，保证目录页有真实单元可展开）
UNITS = {
    "语文": ["第一单元 识字与拼音", "第二单元 课文学习", "第三单元 阅读理解",
             "第四单元 古诗文", "第五单元 口语交际", "第六单元 习作表达"],
    "数学": ["第一单元 数与代数", "第二单元 图形与几何", "第三单元 统计与概率",
             "第四单元 量与计量", "第五单元 综合应用", "第六单元 复习与拓展"],
    "英语": ["Unit 1 Greetings", "Unit 2 Colours", "Unit 3 Numbers",
             "Unit 4 Animals", "Unit 5 Food", "Unit 6 My Family"],
    "科学": ["第一单元 植物", "第二单元 动物", "第三单元 物质与材料",
             "第四单元 地球与宇宙", "第五单元 技术与工程", "第六单元 科学探究"],
}


def seed():
    _ensure_textbook_catalogs_table()
    total = 0
    with engine.begin() as conn:
        for grade in PRIMARY_GRADES:
            for subject, units in UNITS.items():
                top_name = f"{EDITION}{subject}{grade}上册"
                existing = conn.execute(
                    text(
                        "SELECT id FROM textbook_catalogs "
                        "WHERE subject=:s AND edition=:e AND grade=:g "
                        "AND level='edition' AND name=:n"
                    ),
                    {"s": subject, "e": EDITION, "g": grade, "n": top_name},
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
                        {"id": top_id, "n": top_name, "s": subject, "e": EDITION, "g": grade},
                    )
                    total += 1

                for idx, name in enumerate(units, 1):
                    ex = conn.execute(
                        text(
                            "SELECT id FROM textbook_catalogs "
                            "WHERE subject=:s AND edition=:e AND parent_id=:p AND name=:n"
                        ),
                        {"s": subject, "e": EDITION, "p": top_id, "n": name},
                    ).first()
                    if ex:
                        continue
                    conn.execute(
                        text(
                            "INSERT INTO textbook_catalogs "
                            "(id, name, subject, edition, grade, level, unit_index, parent_id) "
                            "VALUES (:id, :n, :s, :e, :g, 'unit', :idx, :p)"
                        ),
                        {"id": gen_uuid(), "n": name, "s": subject, "e": EDITION,
                         "g": grade, "idx": idx, "p": top_id},
                    )
                    total += 1

    print(f"seed 完成：本次新增 {total} 行")
    with engine.connect() as conn:
        for grade in PRIMARY_GRADES:
            n = conn.execute(
                text("SELECT COUNT(*) FROM textbook_catalogs WHERE grade = :g"), {"g": grade}
            ).scalar()
            print(f"  {grade}: {n} 行")


if __name__ == "__main__":
    seed()
