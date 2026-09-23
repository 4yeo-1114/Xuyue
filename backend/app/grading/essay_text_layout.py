# -*- coding: utf-8 -*-
"""中文排版辅助：折行后修正行首标点（避头标点）。"""

from __future__ import annotations

# 不应出现在行首的标点（含中英文常见闭引号、括号等）
LEADING_PUNCTUATION = frozenset(
    "，。！？；：、）】》」』\"\"''…—·,.!?;:)]}\"'%"
)


def fix_punctuation_line_starts(lines: list[str]) -> list[str]:
    """若某行以标点开头，将上一行末字移到本行开头。"""
    if not lines:
        return lines
    result = [lines[0]]
    for line in lines[1:]:
        prev = result[-1]
        while line and line[0] in LEADING_PUNCTUATION and prev:
            ch = prev[-1]
            prev = prev[:-1]
            line = ch + line
        result[-1] = prev
        result.append(line)
    return result
