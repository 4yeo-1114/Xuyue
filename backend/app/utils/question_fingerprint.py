# -*- coding: utf-8 -*-
"""题目稳定 ID 指纹纯函数（DL3 · C2 校本题库前置）。

P0 语义
-------
题目指纹 = sha256(规范化(subject) + "|" + 规范化(question_type) + "|"
                 + 规范化(question_text) + "|" + 规范化(correct_answer))，
输出带 ``fp_`` 命名空间前缀的 64 位 hex（小写，总长 67）。

- 实质内容变化（改科目 / 改题型 / 改题干 / 改答案）⇒ 指纹变化 ⇒ 视为新题；
- 仅排版级差异（空白、全半角、冗余首尾标点）⇒ 指纹不变 ⇒ 同一题。

用途
----
C2 校本题库的稳定唯一键 ``UNIQUE(school_id, fingerprint)``：同一道题跨多张卷子
收敛到题库同一条记录，从而叠加正答率等统计。指纹只依赖题干内容，与卷内位置
序号（如 ``q-1`` / ``q-2``，见 reference_vlm_grading.py / manual_grading.py）
无关，故跨卷稳定、可复现。

归一化规则（_normalize，确定性、幂等）
--------------------------------------
1. None → ""（缺席字段在 question_fingerprint 层用哨兵区分，见"字段边界"）；
2. ``str().strip()`` 去首尾空白；
3. 全半角统一：U+FF01..U+FF5E 映射回半角 ASCII（Ａ→A、１→1、＋→+）；
   U+3000 全角空格 → 普通空格；
4. 连续空白完全移除（含 \\t\\n\\r、全角空格）。注意：这里比"折叠为单个半角
   空格"吸收更强——验收要求 ``"分数 加减"`` 与 ``"分数加减"`` 指纹一致，只有
   整体移除才能满足；代价是拉丁词边界空格也会被吸收（P0 以题干去重为目标，
   接受该碰撞风险，P1 近似去重再细化）；
5. 标点归一：，→,   。→.   ！→!   ？→?   ；→;   ：→:   “”→"   ‘’→'
   （）→()   …→...；随后剥离首尾冗余标点（str.strip）；若整个字符串全为标点，
   保留归一后的标点串（不剥到空），使"全标点"输入与"空串"指纹可区分；
6. 不做大小写折叠、繁简转换、去语气词 / 同义替换 —— 那是 P1 近似去重
   （simhash）的范畴，不进本 DL。

字段边界与缺席语义
------------------
四个字段先各自规范化，再以 ``|`` join。为满足验收"空输入指纹各不相同"：
- None（缺席）字段在 join 中用保留哨兵 ``\\x00`` 表示，与"显式空串"（归一为
  空）区分；
- 因此 ``(None,None,None,None)``、``("","","","")``、全标点三类空输入的指纹
  两两不同。

已知边界
--------
字段内容若含字面 ``|``（半角或全角转半角后）可能引入分隔歧义（如
subject="a|b" 与 text="c" 撞 subject="a" 与 text="b|c" 的编码）。本 DL 按
"normalize 后以 | join"的口径实现，仅保证验收中的边界样例可区分，不做转义 /
长度前缀。全角竖线 ｜→| 同理。
"""

from __future__ import annotations

import hashlib
import re

_FINGERPRINT_PREFIX = "fp_"
_SEPARATOR = "|"
# None（缺席）字段哨兵：与"显式空串"区分，保证空输入指纹两两不同
_ABSENT_FIELD_MARKER = "\x00"

# U+FF01..U+FF5E（全角 ASCII 区）→ 减去 0xFEE0 映射回半角 ASCII（U+0021..U+005E）
_FULLWIDTH_ASCII = {cp: cp - 0xFEE0 for cp in range(0xFF01, 0xFF5F)}

# 不在 U+FF01..U+FF5E 区间的常见标点 → 语义等价 ASCII
_CJK_PUNCT_MAP = str.maketrans({
    "，": ",",
    "。": ".",
    "！": "!",
    "？": "?",
    "；": ";",
    "：": ":",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "（": "(",
    "）": ")",
    "…": "...",
})

# 首尾剥离的"不影响语义"标点（映射后均为 ASCII）
_EDGE_PUNCT = ".,!?;:()[]{}'\""


def _normalize(text: str | None) -> str:
    """确定性、幂等的字段规范化（None → 空串；全标点串保留归一结果）。"""
    if text is None:
        return ""
    s = str(text).strip()
    # 全半角统一（全角 ASCII 区 → 半角；全角空格 → 普通空格）
    s = s.translate(_FULLWIDTH_ASCII).replace("　", " ")
    # 连续空白完全移除（更强吸收：折叠为 1 个空格仍会在"分数 加减"vs"分数加减"上分歧）
    s = re.sub(r"\s+", "", s)
    # 标点归一
    s = s.translate(_CJK_PUNCT_MAP)
    # 剥离首尾冗余标点；全标点串保留归一结果（不剥到空），保证与空串指纹可区分
    stripped = s.strip(_EDGE_PUNCT)
    if stripped:
        s = stripped
    return s


def question_fingerprint(
    subject: str | None,
    question_type: str | None,
    question_text: str | None,
    correct_answer: str | None,
) -> str:
    """生成题目稳定 ID 指纹（P0：实质内容变化 = 新题）。

    四字段：subject / question_type / question_text / correct_answer。
    任一字段可为 None（按缺席处理）；输出 ``fp_`` + 64 位 hex。
    """
    parts = [
        _ABSENT_FIELD_MARKER if subject is None else _normalize(subject),
        _ABSENT_FIELD_MARKER if question_type is None else _normalize(question_type),
        _ABSENT_FIELD_MARKER if question_text is None else _normalize(question_text),
        _ABSENT_FIELD_MARKER if correct_answer is None else _normalize(correct_answer),
    ]
    joined = _SEPARATOR.join(parts)
    return f"{_FINGERPRINT_PREFIX}{hashlib.sha256(joined.encode('utf-8')).hexdigest()}"


def text_fingerprint(text: str | None) -> str:
    """任意文本指纹（判分缓存的作答身份哈希）：与题目指纹同套归一化。

    输出 64 位 hex（无 ``fp_`` 前缀，对齐 verdict_cache.student_answer_hash 定长）。
    ⚠️ None 与空串归一后同值——空作答不得进缓存，由 cache_key 先行拦截，
    不依赖本函数区分。
    """
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()
