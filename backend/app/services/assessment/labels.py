"""标签白名单闸门 —— 机器贴标签防护（学术安全线）。

只允许「行为观察 / 学习方式 / 兴趣倾向」描述词，禁止人格归因词（粗心 / 懒惰 /
性格缺陷 / 贴标签式）。对齐 B0 契约 §4.2-4.3。

硬约束（fail-closed）：
  - LABEL_MAP 只收录白名单文案，generate_labels 不外造词；
  - filter_labels 对任何输入逐词过闸门：不在白名单 → 直接丢弃，含禁止词 → 直接丢弃；
  - 标签只写 assessment_result.tag_schema（锚点层），绝不写 student_portfolio.dimensions；
  - 无信效度宣称：文案只做行为倾向描述，不做人格归因。
"""

from __future__ import annotations

from typing import Optional

# ── 白名单标签库：{子维度键: 白名单标签文案}（B0 §4.2，共 22 个）──
LABEL_MAP: dict[str, str] = {
    # 学习方式偏好 (learning_style)
    "ls_watch_example": "偏好先看例题再动笔",
    "ls_try_self": "偏好先动手尝试再对答案",
    "ls_handson": "偏好动手实践",
    "ls_listen": "适合听觉输入",
    "ls_read": "适合文字阅读输入",
    "ls_discuss": "适合讨论互动式学习",
    "ls_mixed": "学习方式较灵活",
    # 兴趣领域 (interest)
    "int_making": "对动手创作类活动兴趣高",
    "int_reading": "对阅读思考类活动兴趣高",
    "int_sports": "对运动户外类活动兴趣高",
    "int_social": "对与人交流类活动兴趣高",
    "int_balanced": "兴趣领域较均衡",
    # 交往风格 (social_style)
    "ss_organize": "班级活动中偏向主动组织",
    "ss_participate": "班级活动中偏向配合参与",
    "ss_mixed": "组织与参与较均衡",
    # 情绪调节方式 (emotion_regulation)
    "er_alone": "情绪波动时偏向独处调节",
    "er_talk": "情绪波动时偏向找人倾诉",
    "er_mixed": "情绪调节方式较灵活",
    # 挑战应对倾向 (challenge_coping)
    "cc_persist": "面对难题倾向坚持解决",
    "cc_skip_then_back": "面对难题倾向先跳过再回看",
    "cc_ask_help": "遇到难题倾向主动求助",
    "cc_mixed": "面对难题策略较灵活",
}

# 禁止词：标签文案一旦包含任一禁止词即丢弃（fail-closed 双保险）。
# B0 §4.3 共 33 个（含叙阅扩展禁止词）。
FORBIDDEN_WORDS: list[str] = [
    "粗心", "懒惰", "态度差", "性格缺陷", "内向", "外向", "多动",
    "自闭", "智力低下", "笨", "迟钝", "自卑", "自大", "叛逆", "爱捣乱",
    "自私", "孤僻", "不合群", "心理", "性格", "人格", "品行",
    # 叙阅扩展禁止词（对齐教育场景）
    "没救了", "差生", "坏学生", "问题学生", "不正常", "有病",
    "天生", "智商", "情商", "缺陷", "障碍",
]

_ALLOWED_LABELS: frozenset[str] = frozenset(LABEL_MAP.values())

# 公开白名单全集（供验证/审计直接引用）
ALLOWED_LABELS: frozenset[str] = _ALLOWED_LABELS


def is_allowed_label(label: str) -> bool:
    """白名单闸门：不在白名单直接丢弃（fail-closed），含禁止词也丢弃。"""
    if not label or not isinstance(label, str):
        return False
    if label not in _ALLOWED_LABELS:
        return False
    if any(w in label for w in FORBIDDEN_WORDS):
        return False
    return True


def filter_labels(labels) -> list[str]:
    """强制过白名单：逐个闸门校验，丢弃不合法标签，去重（fail-closed）。"""
    out: list[str] = []
    for label in (labels or []):
        if is_allowed_label(label) and label not in out:
            out.append(label)
    return out


def label_for_option_dim(option_dim: str) -> Optional[str]:
    """按选项子维度键取白名单标签；未收录返回 None（不外造词）。"""
    if not option_dim:
        return None
    label = LABEL_MAP.get(option_dim)
    if not label:
        return None
    return label if is_allowed_label(label) else None
