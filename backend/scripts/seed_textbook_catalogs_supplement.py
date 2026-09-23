# -*- coding: utf-8 -*-
"""四维定位矩阵 · 全量补全 seed（textbook_catalogs 表）。

在 seed_textbook_catalogs.py（七年级，3 科）与 seed_textbook_catalogs_primary.py
（小学段 4 科）基础上，完成两件事，使四维定位矩阵所有单元格点亮且可点：
  1. 修正初中段年级命名：`七年级` → `初一`（前端目录页只传「初一/初二/初三」，
     后端按 grade 精确匹配，原「七年级」会导致点击后目录为空）。
  2. 补全缺失组合（人教版）：
       - 小学段 补 道德与法治 × 6 年级；
       - 初中段 补 语文/数学/英语 × 初二/初三，以及 道德与法治/历史/地理/生物/物理/化学 × 初一/初二/初三。

幂等：先做年级归一化，再按 (subject, edition, grade, name) 自然键查重；可重复运行。
用法：python scripts/seed_textbook_catalogs_supplement.py
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

EDITION = "人教版"

PRIMARY_GRADES = [
    "小学一年级",
    "小学二年级",
    "小学三年级",
    "小学四年级",
    "小学五年级",
    "小学六年级",
]
JUNIOR_GRADES = ["初一", "初二", "初三"]

# 各科占位单元名（通用；真实目录后续替换）
UNITS = {
    "语文": ["第一单元 识字与拼音", "第二单元 课文学习", "第三单元 阅读理解",
             "第四单元 古诗文", "第五单元 口语交际", "第六单元 习作表达"],
    "数学": ["第一单元 数与代数", "第二单元 图形与几何", "第三单元 统计与概率",
             "第四单元 量与计量", "第五单元 综合应用", "第六单元 复习与拓展"],
    "英语": ["Unit 1 Greetings", "Unit 2 Colours", "Unit 3 Numbers",
             "Unit 4 Animals", "Unit 5 Food", "Unit 6 My Family"],
    "科学": ["第一单元 植物", "第二单元 动物", "第三单元 物质与材料",
             "第四单元 地球与宇宙", "第五单元 技术与工程", "第六单元 科学探究"],
    "道德与法治": ["第一单元 成长中的我", "第二单元 友谊的天空", "第三单元 师长情谊",
                   "第四单元 生命的思考", "第五单元 青春时光", "第六单元 做情绪的主人"],
    "历史": ["第一单元 史前时期", "第二单元 夏商周时期", "第三单元 秦汉时期",
             "第四单元 三国两晋南北朝", "第五单元 隋唐时期", "第六单元 明清时期"],
    "地理": ["第一单元 地球与地图", "第二单元 陆地和海洋", "第三单元 天气与气候",
             "第四单元 居民与聚落", "第五单元 发展与合作", "第六单元 中国地理"],
    "生物": ["第一单元 生物和生物圈", "第二单元 生物体的结构层次", "第三单元 生物圈中的绿色植物",
             "第四单元 生物圈中的人", "第五单元 生物的多样性", "第六单元 生物技术"],
    "物理": ["第一单元 声现象", "第二单元 光现象", "第三单元 物态变化",
             "第四单元 运动和力", "第五单元 压强与浮力", "第六单元 功和机械能"],
    "化学": ["第一单元 走进化学世界", "第二单元 我们周围的空气", "第三单元 物质构成的奥秘",
             "第四单元 自然界的水", "第五单元 化学方程式", "第六单元 碳和碳的氧化物"],
}

# 需要补全的「(年级组, 学科组)」；语文/数学/英语/科学 × 小学、语文/数学/英语 × 初一 已存在，
# 靠下方查重跳过，这里统一遍历不会重复插入。
PLAN = [
    (PRIMARY_GRADES, ["道德与法治"]),
    (JUNIOR_GRADES, ["语文", "数学", "英语", "道德与法治", "历史", "地理", "生物", "物理", "化学"]),
]


def _normalize_junior_grades(conn):
    """初中段年级归一化：七年级 -> 初一（同时修正 edition 节点名里的「七年级」字样）。"""
    n = conn.execute(
        text("SELECT COUNT(*) FROM textbook_catalogs WHERE grade = '七年级'")
    ).scalar()
    if n:
        conn.execute(
            text(
                "UPDATE textbook_catalogs "
                "SET grade = '初一', name = REPLACE(name, '七年级', '初一') "
                "WHERE grade = '七年级'"
            )
        )
    return int(n or 0)


def seed():
    _ensure_textbook_catalogs_table()
    total = 0
    with engine.begin() as conn:
        renamed = _normalize_junior_grades(conn)

        for grades, subjects in PLAN:
            for grade in grades:
                for subject in subjects:
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
                        # edition 节点已存在（如归一化后的 语文/数学/英语×初一），
                        # 其下单元已由原 seed 建好且名称可能不同，跳过避免产生重复单元。
                        continue
                    else:
                        top_id = gen_uuid()
                        conn.execute(
                            text(
                                "INSERT INTO textbook_catalogs "
                                "(id, name, subject, edition, grade, level, unit_index, parent_id) "
                                "VALUES (:id, :n, :s, :e, :g, 'edition', NULL, NULL)"
                            ),
                            {"id": top_id, "n": top_name, "s": subject,
                             "e": EDITION, "g": grade},
                        )
                        total += 1

                    for idx, name in enumerate(UNITS.get(subject) or [], 1):
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

    print(f"seed 完成：归一化 {renamed} 行（七年级→初一），本次新增 {total} 行")
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM textbook_catalogs")).scalar()
        print(f"  textbook_catalogs 总计: {n} 行")


if __name__ == "__main__":
    seed()
