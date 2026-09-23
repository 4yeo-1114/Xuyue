# -*- coding: utf-8 -*-
"""E09 统一字段掩码工具（纯函数）。

分级依据 JY/T 0661-2025《教育行业数据分类分级指南》（近似落地）：
- L4 学籍号 / 手机 / 家长电话 → 掩码（保留首尾，隐藏中间）
- L4-L5 家庭住址 → 仅保留省 + 市 + 区县，其余掩码
- L3 姓名 → 保留首字 + 「**」（AI 出站匿名化另走 Anonymizer，映射为「学生01」）

约定：
- 全部为纯函数，不抛异常；空值/短值做健壮退化。
- 空串原样返回，None 返回空串——调用方如需保留 None 语义请自行先判空。
- 规则与 docs/contracts/13-data-classification.md 第 3 节保持一致，改规则需同步文档。
"""

from __future__ import annotations

import re

_MASK = "*"

# 行政区划前缀：省(自治区/特别行政区) + 市(自治州/地区/盟) + 区/县/旗/新区
# 每段限定 1-12 字，避免贪心吞掉后续街道门牌。
_ADDRESS_PROVINCE_RE = re.compile(r"^(.{1,12}?(?:省|自治区|特别行政区))")
_ADDRESS_CITY_RE = re.compile(r"^(.{1,12}?(?:市|自治州|地区|盟))")
_ADDRESS_DISTRICT_RE = re.compile(r"^(.{1,12}?(?:区|县|旗|新区))")

# 「区」结尾的常见非行政区复合词：如「幸福小区」「科技园区」，不是行政区划，识别时须拒绝。
_DISTRICT_FALSE_POSITIVE_SUFFIXES = (
    "小区",
    "园区",
    "校区",
    "社区",
    "景区",
    "矿区",
    "厂区",
    "学区",
    "街区",
    "郊区",
    "库区",
    "港区",
    "林区",
    "管区",
    "辖区",
)


def _to_str(value) -> str:
    return str(value or "").strip()


def _region_prefix(s: str) -> str:
    """提取地址中可公开的省 + 市 + 区县前缀；识别不到返回空串。"""
    kept = ""
    rest = s
    m = _ADDRESS_PROVINCE_RE.match(rest)
    if m:
        kept += m.group(1)
        rest = rest[len(m.group(1)):]
    m = _ADDRESS_CITY_RE.match(rest)
    if m:
        kept += m.group(1)
        rest = rest[len(m.group(1)):]
    m = _ADDRESS_DISTRICT_RE.match(rest)
    if m:
        token = m.group(1)
        # 拒绝「幸福小区」这类以非行政区「区」结尾的复合词
        if not token.endswith(_DISTRICT_FALSE_POSITIVE_SUFFIXES):
            kept += token
    return kept


def mask_phone(value) -> str:
    """手机/电话掩码：标准位 → 138****1234（前3后4）；过短退化为保留首尾。

    - 空值 → ""
    - len <= 4 → 整体掩码
    - len <= 7 → 保留前2后2，中间掩码
    - 其余 → 保留前3后4
    """
    s = _to_str(value)
    if not s:
        return ""
    n = len(s)
    if n <= 4:
        return _MASK * n
    if n <= 7:
        return s[:2] + _MASK * (n - 4) + s[-2:]
    return s[:3] + _MASK * 4 + s[-4:]


def mask_student_number(value, keep: int = 2) -> str:
    """学籍号掩码：保留前 keep 位 + 后 keep 位，中间掩码（23****89）。

    - keep 默认 2（与文档统一）；过短仅保留一端。
    - 空值 → ""
    - len <= keep → 整体掩码
    - len <= 2*keep → 保留后 keep 位
    - 其余 → 前 keep + 掩码 + 后 keep
    """
    s = _to_str(value)
    if not s:
        return ""
    n = len(s)
    if n <= keep:
        return _MASK * n
    if n <= keep * 2:
        return _MASK * (n - keep) + s[-keep:]
    return s[:keep] + _MASK * (n - keep * 2) + s[-keep:]


def mask_address(value) -> str:
    """家庭住址掩码：仅保留省 + 市 + 区县前缀，其余以「**」替代。

    - 空值 → ""
    - 无法识别行政区划（无省/市/区县标记）→ 整体掩码（保守策略，最长 8 位）。
    - 识别到前缀且仍有剩余 → 前缀 + 「**」。
    """
    s = _to_str(value)
    if not s:
        return ""
    kept = _region_prefix(s)
    if not kept:
        return _MASK * min(len(s), 8)
    if len(s) > len(kept):
        kept += "**"
    return kept


def mask_name(name) -> str:
    """姓名掩码：保留首字 + 「**」（张小明 → 张**）。

    - 空值 → ""
    - 单字 → 「*」（无法既保留首字又隐藏，整体掩码）
    - 备注：AI 出站的学生姓名匿名化另走 app/utils/anonymize.py 的 Anonymizer（学生01）。
    """
    s = _to_str(name)
    if not s:
        return ""
    if len(s) == 1:
        return _MASK
    return s[0] + _MASK * (len(s) - 1)
