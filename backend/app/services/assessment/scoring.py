"""测评计分服务 —— B0 契约 §4.4 标签生成规则 + §4.5 冲突裁决。

v1 简化规则（等权累加 + 归一化）：
  1. 遍历 questions 数组，逐个匹配 answers 中对应题号的选项
  2. 按题目 dim（顶层维度）累加作答次数 → dimension_points
  3. 归一化到百分比：各维 points / total_answered × 100 → dimension_percents
  4. 逐个选项取 option.dim（子维度键）→ LABEL_MAP 白名单文案 → 过闸门筛选
  5. 输出：labels（去重白名单标签） + dimension_percents（归一化占比）

冲突裁决（§4.5）：同维度多标签并列保留（不做强制排他）；v1 无次数阈值；
  dimension_percents 按维度归一化展示；全 mixed 兜底为均衡描述，不计"数据无效"。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from app.services.assessment.labels import LABEL_MAP, filter_labels, label_for_option_dim

# 顶层 5 维（v1 维度键）
DIMENSION_KEYS: tuple[str, ...] = (
    "learning_style",
    "interest",
    "social_style",
    "emotion_regulation",
    "challenge_coping",
)


def validate_answers(questions: list[dict], answers: dict[str, str]) -> int:
    """校验 answers 命中题面题号/选项的数量；全部无效返回 0（no_match）。"""
    valid_qids = {q.get("id") for q in questions}
    matched = 0
    for qid, opt_key in (answers or {}).items():
        if qid not in valid_qids:
            continue
        q = next((x for x in questions if x.get("id") == qid), None)
        if not q:
            continue
        if any(o.get("key") == opt_key for o in q.get("options", [])):
            matched += 1
    return matched


def score_answers(questions: list[dict], answers: dict[str, str]) -> dict:
    """
    answers: {question_id: option_key}
    返回: {dimension_points, dimension_percents, labels, total_answered}
    """
    dim_points: dict[str, int] = defaultdict(int)
    selected_labels: list[str] = []
    dim_label_map: dict[str, list[str]] = defaultdict(list)  # 维度 -> 标签列表（冲突裁决展示用）

    for q in questions or []:
        qid = q.get("id")
        if qid not in answers:
            continue
        dim = q.get("dim") or ""
        opt_key = answers[qid]
        selected = next((o for o in q.get("options", []) if o.get("key") == opt_key), None)
        if not selected:
            continue

        dim_points[dim] += 1
        label = label_for_option_dim(selected.get("dim"))
        if label:
            if label not in selected_labels:
                selected_labels.append(label)
            if label not in dim_label_map[dim]:
                dim_label_map[dim].append(label)

    total = sum(dim_points.values())
    percents: dict[str, float] = {}
    if total:
        percents = {d: round(pts / total * 100, 2) for d, pts in dim_points.items()}

    # fail-closed 白名单闸门：双重校验（label_for_option_dim 已过闸门，此处再兜底）
    labels = filter_labels(selected_labels)

    return {
        "dimension_points": dict(dim_points),
        "dimension_percents": percents,
        "labels": labels,
        "labels_by_dimension": {d: dim_label_map[d] for d in dim_label_map},
        "total_answered": total,
    }


def build_tag_schema(score: dict, generated_at: Optional[str] = None) -> dict:
    """组装 assessment_results.tag_schema JSON（B0 §2.3 结构）。"""
    from datetime import datetime, timezone

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "labels": score.get("labels", []),
        "dimension_percents": score.get("dimension_percents", {}),
        "dimension_points": score.get("dimension_points", {}),
        "generated_at": generated_at,
    }


def build_raw_score(questions: list[dict], answers: dict[str, str], score: dict) -> dict:
    """组装 assessment_results.raw_score JSON（B0 §2.3 结构）。"""
    # answers 只保留命中有效题号+选项的条目，便于审计
    valid_qids = {q.get("id") for q in (questions or [])}
    clean_answers = {}
    for qid, opt_key in (answers or {}).items():
        if qid in valid_qids:
            clean_answers[qid] = opt_key
    return {
        "answers": clean_answers,
        "dimension_points": score.get("dimension_points", {}),
        "total_answered": score.get("total_answered", 0),
    }


def default_guardian_consent() -> dict:
    """首测默认 consent 状态：not_required（至少不默认 granted），version=1。"""
    return {
        "status": "not_required",
        "version": 1,
        "granted_at": None,
        "withdrawn_at": None,
    }


# ── 供单元验收直接引用的纯函数 ──
def is_label_whitelisted(label: str) -> bool:
    from app.services.assessment.labels import is_allowed_label
    return is_allowed_label(label)
