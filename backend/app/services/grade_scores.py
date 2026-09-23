"""成绩等级制（E04《未成年人学校保护规定》）。

对齐《未成年人学校保护规定》相关条款：成绩以等级呈现（4 级制）、一对一可见、不公开不排名。

本模块提供：
- ``grade_for_score``：分数 → 等级纯函数（契约锁定，前后端勿改等级代码）
- ``ensure_ranking_grade``：给 rankings 每项补 grade（旧报告按 score 派生，不落库）
- ``filter_rankings_for_parent``：家长视图裁剪（只留绑定学生记录 + 去掉 rank），
  供未来家长端复用（当前 class_access 体系无 parent 入口，做成函数级契约预埋）。

等级映射契约：
    score >= 85 → excellent
    score >= 70 → good
    score >= 60 → pass
    score <  60 → needs_work
    score 为空  → None
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

# E04 契约等级代码（前后端锁定，勿改字段名/取值）
GRADE_EXCELLENT = "excellent"
GRADE_GOOD = "good"
GRADE_PASS = "pass"
GRADE_NEEDS_WORK = "needs_work"

GRADE_VALUES = (GRADE_EXCELLENT, GRADE_GOOD, GRADE_PASS, GRADE_NEEDS_WORK)


def grade_for_score(score: Any) -> Optional[str]:
    """分数 → 等级纯函数。

    边界：>=85 excellent；>=70 good；>=60 pass；<60 needs_work。
    score 为 None / 非数值 → None（保留空等级，表示未评分）。
    """
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if value >= 85:
        return GRADE_EXCELLENT
    if value >= 70:
        return GRADE_GOOD
    if value >= 60:
        return GRADE_PASS
    return GRADE_NEEDS_WORK


def ensure_ranking_grade(rankings: Sequence[Any]) -> None:
    """就地给 rankings 每项补 grade；已有合法 grade 保留，缺失时按 score 派生。

    用于兼容历史报告（新增 grade 字段前落库的 JSON 无此键）。
    """
    for row in rankings:
        if not isinstance(row, dict):
            continue
        if row.get("grade") not in GRADE_VALUES:
            row["grade"] = grade_for_score(row.get("score"))


def filter_rankings_for_parent(
    rankings: Sequence[Any],
    bound_student_ids: Sequence[str],
) -> list[dict]:
    """家长视图：只保留该家长绑定学生自己的排名记录，并去掉 rank（不公开不排名）。

    grade/score 保留（是绑定学生本人的成绩，一对一可见）；percentile/tier 等若有同样保留。
    bound_student_ids 为该家长绑定的学生 ID 列表。
    """
    bound = set(bound_student_ids or [])
    out: list[dict] = []
    for row in rankings:
        if not isinstance(row, dict):
            continue
        if row.get("student_id") not in bound:
            continue
        item = {key: value for key, value in row.items() if key != "rank"}
        out.append(item)
    return out
