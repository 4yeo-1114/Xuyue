# -*- coding: utf-8 -*-
"""红线词表守卫测试 — 锚定 B 端 redline_filter.py 词表现状。

背景：B 端（叙阅）复制 C 端（灵犀家长端）redline_filter.py 纯函数词表，
挂到 4 个 LLM 输出出口做输出侧过滤。本文件只锚定词表现状，
不擅自增删词（语义待产品确认）。词表变更须经产品评审，先改这里再改实现。
"""

from app.services.redline_filter import REDLINE_PHRASES

# 8 个删除词：伪科学名目，绝不出现
_DELETE_PHRASES = [
    "松果体激活",
    "照相记忆",
    "左右脑开发",
    "全脑开发",
    "感统失调",
    "开天眼",
    "蒙眼识字",
    "右脑开发",
]

# 抽查替换词：话术换语言，保留行为内核
_REPLACEMENT_SPOT_CHECKS = {
    "多巴胺戒断": "减少即时刺激",
    "21天养成习惯": "习惯养成需要时间",
    "窗口期": "关键阶段",
    "专注力训练": "专注习惯培养",
    "低级快乐": "即时快乐",
    "意志力是肌肉": "循序渐进培养自控",
}


def test_redline_phrases_nonempty_and_sized():
    """词表非空，且条数 ≥ 26（锚定现状，防误删）。"""
    assert REDLINE_PHRASES, "红线词表不应为空"
    assert len(REDLINE_PHRASES) >= 26


def test_delete_phrases_present_and_marked_none():
    """8 个删除词必须在词表内，且值为 None（删除，绝不出现）。"""
    for phrase in _DELETE_PHRASES:
        assert phrase in REDLINE_PHRASES, f"删除词缺失: {phrase}"
        assert REDLINE_PHRASES[phrase] is None, f"{phrase} 应为删除类(None)，当前={REDLINE_PHRASES[phrase]!r}"


def test_replacement_spot_checks():
    """抽查替换词映射正确（话术换语言，保留行为内核）。"""
    for phrase, expected in _REPLACEMENT_SPOT_CHECKS.items():
        assert phrase in REDLINE_PHRASES, f"替换词缺失: {phrase}"
        assert REDLINE_PHRASES[phrase] == expected, (
            f"{phrase} 应替换为 {expected!r}，当前={REDLINE_PHRASES[phrase]!r}"
        )
