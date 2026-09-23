# -*- coding: utf-8 -*-
"""五育指标库 indicator_definitions 幂等造数。

对齐 docs/migrations：
  - 2026-08-12-chunfeng-indicators-v2.sql（19 条二级指标，level=2）
  - 2026-08-15-ai-literacy-hierarchy.sql（6 维度节点 level=1 + AI 素养方面/观测点）

三层级：维度(level=1) → 方面(level=2) → 观测点(level=3)，parent_id 自引用。
幂等：固定主键 id + INSERT IGNORE（主键冲突跳过）；重复运行不翻倍。
凭据复用后端根目录 .env（app.config.Settings 自动加载），需在 backend 根目录运行。
用法：cd grade-buddy-scan-back_end && python scripts/seed_indicators.py
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
from app.database import engine  # noqa: E402

# (id, dimension, code, name, description, level, parent_id, sort_order)
ROWS = [
    # ── 维度节点 level=1 ──
    ("ind-dim-moral",        "moral",        "dim_moral",        "品德发展",       "品德发展与行为规范（教基〔2021〕3号）", 1, None, 1),
    ("ind-dim-intellectual", "intellectual", "dim_intellectual", "学业发展",       "学业水平与学习过程", 1, None, 2),
    ("ind-dim-physical",     "physical",     "dim_physical",     "身心发展",       "体质健康与心理健康", 1, None, 3),
    ("ind-dim-aesthetic",    "aesthetic",    "dim_aesthetic",    "审美素养",       "审美感知与艺术表现", 1, None, 4),
    ("ind-dim-labor",        "labor",        "dim_labor",        "劳动与社会实践", "劳动习惯与社会实践", 1, None, 5),
    ("ind-dim-ai",           "ai_literacy",  "dim_ai_literacy",  "AI 素养",        "AI 课程学习过程性成果与素养表现（2024 教基厅函 32 号）", 1, None, 6),
    # ── 方面 level=2（德/智/体/美/劳 19 条）──
    ("ind-moral-behavior",      "moral",        "moral_behavior",      "日常行为表现", "日常言谈举止、校规遵守等", 2, "ind-dim-moral", 1),
    ("ind-moral-activity",      "moral",        "moral_activity",      "品德活动参与", "主题活动、班会、志愿服务等", 2, "ind-dim-moral", 2),
    ("ind-moral-responsibility","moral",        "moral_responsibility","责任担当",     "值日尽责、班级事务担当等", 2, "ind-dim-moral", 3),
    ("ind-moral-conduct",       "moral",        "moral_conduct",       "品行记录",     "奖惩记录、诚信表现等", 2, "ind-dim-moral", 4),
    ("ind-intellectual-grade",    "intellectual", "intellectual_grade",    "学科成绩", "学科测验、期中期末成绩表现", 2, "ind-dim-intellectual", 1),
    ("ind-intellectual-class",    "intellectual", "intellectual_class",    "课堂表现", "课堂参与、回答问题、专注度", 2, "ind-dim-intellectual", 2),
    ("ind-intellectual-homework", "intellectual", "intellectual_homework", "作业情况", "作业完成度与质量", 2, "ind-dim-intellectual", 3),
    ("ind-intellectual-ability",  "intellectual", "intellectual_ability",  "学习能力", "自主学习、学习方法、思维拓展", 2, "ind-dim-intellectual", 4),
    ("ind-intellectual-analysis", "intellectual", "intellectual_analysis", "学情分析", "学情诊断、错题订正、靶向提升", 2, "ind-dim-intellectual", 5),
    ("ind-physical-fitness", "physical", "physical_fitness", "身体素质", "体能锻炼、运动表现、社团活动等", 2, "ind-dim-physical", 1),
    ("ind-physical-metrics", "physical", "physical_metrics", "体质指标", "身高体重、视力、晨午检留痕等", 2, "ind-dim-physical", 2),
    ("ind-physical-mental",  "physical", "physical_mental",  "心理健康", "心理状态、情绪调节、适应性", 2, "ind-dim-physical", 3),
    ("ind-physical-habit",   "physical", "physical_habit",   "生活习惯", "作息规律、用眼卫生、锻炼习惯", 2, "ind-dim-physical", 4),
    ("ind-aesthetic-music",    "aesthetic", "aesthetic_music",    "音乐",     "音乐课表现、合唱器乐活动", 2, "ind-dim-aesthetic", 1),
    ("ind-aesthetic-art",      "aesthetic", "aesthetic_art",      "美术",     "美术课表现、书画创作", 2, "ind-dim-aesthetic", 2),
    ("ind-aesthetic-activity", "aesthetic", "aesthetic_activity", "美育活动", "艺术展演、社团美育活动", 2, "ind-dim-aesthetic", 3),
    ("ind-labor-practice",   "labor", "labor_practice",   "劳动实践", "家务劳动、校园劳动、志愿服务劳动", 2, "ind-dim-labor", 1),
    ("ind-labor-outdoor",    "labor", "labor_outdoor",    "校外实践", "社会实践、研学劳动体验", 2, "ind-dim-labor", 2),
    ("ind-labor-innovation", "labor", "labor_innovation", "创新实践", "手工制作、科技创新、劳创结合", 2, "ind-dim-labor", 3),
    # ── AI 素养方面 level=2 + 观测点 level=3 ──
    ("ind-ai-course",  "ai_literacy", "ai_literacy_course",  "AI 课程学习", "AI 课程过程性学习成果（课时/任务/测验）", 2, "ind-dim-ai", 1),
    ("ind-ai-project", "ai_literacy", "ai_literacy_project", "AI 作品创作", "AI 项目式学习作品/创新成果", 2, "ind-dim-ai", 2),
    ("ind-ai-quality", "ai_literacy", "ai_literacy_quality", "素养表现",    "AI 伦理意识/协作/表达等素养表现", 2, "ind-dim-ai", 3),
    ("ind-ai-course-basic", "ai_literacy", "ai_literacy_course_basic", "AI 基础认知", "AI 基本概念/原理理解", 3, "ind-ai-course", 1),
    ("ind-ai-course-task",  "ai_literacy", "ai_literacy_course_task",  "AI 任务完成", "AI 课程任务/练习完成质量", 3, "ind-ai-course", 2),
    ("ind-ai-project-idea", "ai_literacy", "ai_literacy_project_idea", "创意构思",   "AI 项目创意与方案设计", 3, "ind-ai-project", 1),
]

INSERT_SQL = (
    "INSERT IGNORE INTO indicator_definitions "
    "(id, dimension, code, name, description, level, parent_id, sort_order, is_active, school_id) "
    "VALUES (:id, :dim, :code, :name, :desc, :level, :parent, :sort, 1, NULL)"
)

# 兜底：为任何 level=2 且 parent_id 为空的系统指标回填父维度（幂等）
BACKFILL_SQL = (
    "UPDATE indicator_definitions t "
    "JOIN indicator_definitions d "
    "  ON d.dimension = t.dimension AND d.level = 1 AND d.school_id IS NULL "
    " AND d.code = CONCAT('dim_', t.dimension) "
    "SET t.parent_id = d.id "
    "WHERE t.level = 2 AND t.parent_id IS NULL AND t.school_id IS NULL"
)


def main():
    out_lines = ["=== seed_indicators ==="]
    with engine.begin() as conn:
        inserted = 0
        for (rid, dim, code, name, desc, level, parent, sort) in ROWS:
            res = conn.execute(
                text(INSERT_SQL),
                {"id": rid, "dim": dim, "code": code, "name": name,
                 "desc": desc, "level": level, "parent": parent, "sort": sort},
            )
            inserted += res.rowcount if res.rowcount else 0
        conn.execute(text(BACKFILL_SQL))
        total = conn.execute(text("SELECT COUNT(*) FROM indicator_definitions")).scalar()
        by_dim = conn.execute(
            text("SELECT dimension, COUNT(*) FROM indicator_definitions GROUP BY dimension ORDER BY dimension")
        ).all()
        out_lines.append(f"inserted={inserted}")
        out_lines.append(f"total={total}")
        for dim, n in by_dim:
            out_lines.append(f"  {dim}: {n}")

    out_path = ROOT / "scripts" / "seed_indicators_out.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"done -> {out_path}")


if __name__ == "__main__":
    main()
