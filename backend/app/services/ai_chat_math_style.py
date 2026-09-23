# -*- coding: utf-8 -*-
"""AI 助教：数学/理化符号输出规范（供 Prompt 注入）。"""

from __future__ import annotations

import re

from app.utils.exam_math_format import normalize_exam_math_notation

MATH_FORMAT_RULES = """
## 数学与理化符号书写（必须遵守）
- **禁止**使用 LaTeX 语法：不要用 `$...$`、`$$...$$`、\\frac、\\sqrt、\\times 等。
- **禁止**用 ASCII 上标写法 `cm^3`、`x^2`（前端无法正确显示）。
- 请使用 Unicode 与教师常用写法：
  - **幂次/体积单位**：cm³、dm³、m³、mm³、km²、x²、10⁹
  - **运算符号**：×、÷、±、≤、≥、≠、≈、√、π
  - **分数**：写为 (a)/(b) 或「三分之二」，不要用 \\frac{a}{b}
  - **容量/速度单位**：L、mL、km/h、°C
  - **多个单位并列**：cm³、dm³、m³、L、mL（用中文逗号或顿号分隔）
- 示例（正确）：「强化单位量感：对比 cm³、dm³、m³、L、mL 的实际大小」
- 示例（错误）：「$cm^3, dm^3, m^3$」或「cm^3」
"""

_SUPERSCRIPT_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_UNIT_POWER = re.compile(r"\b([a-zA-Z]{1,4})\^(\d+)\b")


def _to_superscript(text: str) -> str:
    return text.translate(_SUPERSCRIPT_DIGITS)


def normalize_chat_math_text(text: str) -> str:
    """将 AI 输出中的 LaTeX / ^ 写法转为 Unicode 可读文本（与前端 chatMathFormat 对齐）。"""
    if not text:
        return text or ""
    out = normalize_exam_math_notation(text)
    return _UNIT_POWER.sub(lambda m: m.group(1) + _to_superscript(m.group(2)), out)
