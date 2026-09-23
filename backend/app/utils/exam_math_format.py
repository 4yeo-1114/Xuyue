# -*- coding: utf-8 -*-
"""智能组卷：数学/理科题目符号规范化（禁止 LaTeX，转为纸笔试卷常用写法）"""

from __future__ import annotations

import re
from typing import Any, Dict, List

MATH_RELATED_SUBJECT_KEYWORDS = ("数学", "物理", "化学")

MATH_EXAM_FORMAT_PROMPT = """
【数学/理科符号格式——必须严格遵守】
你生成的是中国大陆中小学「纸笔印刷试卷」，学生直接在纸上阅读，不是网页、不是 Markdown、不是 LaTeX。
因此题干、选项、子问题中：
1. 绝对禁止使用：$...$、$$...$$、\\frac{}{}、\\sqrt{}、\\times、\\div 等 LaTeX 或 TeX 命令。
2. 分数一律写成 (分子)/(分母) 或 a/b，例如 (c+d)/m，不要写 \\frac{c+d}{m}。
3. 乘号用 × 或 ·；除号用 ÷ 或 /；绝对值用 |m|；不等号用 ≤、≥、≠。
4. 指数优先用上标字符：m²、m³；若无上标则写 m^2，但不要加 $ 包裹。
5. 字母、数字、符号混排时用半角，例如：若 a、b 互为倒数，c、d 互为相反数，且 |m|=2，则代数式 2ab-(c+d)/m+m² 的值为（ ）。
6. 选择题括号只保留一处：（ ）或 ( )，不要重复 (    )(5分) 这类叠写；分值已在 score 字段，题干里不要再写“(5分)”。
7. 变量名用单个字母或常见代数写法（ab 表示 a×b 时可写 2ab），不要用 LaTeX 间距命令。
"""


def is_math_related_subject(subject: str) -> bool:
    s = (subject or "").strip()
    return any(k in s for k in MATH_RELATED_SUBJECT_KEYWORDS)


_FRAC_PATTERN = re.compile(
    r"\\frac\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}"
)


def _format_frac(num: str, den: str) -> str:
    num = num.strip()
    den = den.strip()
    num_part = f"({num})" if any(ch in num for ch in "+- ") else num
    den_part = f"({den})" if any(ch in den for ch in "+- ") else den
    return f"{num_part}/{den_part}"


def normalize_exam_math_notation(text: str) -> str:
    """将常见 LaTeX 写法转为中小学试卷可读的纯文本。"""
    if not text or not isinstance(text, str):
        return (text or "").strip()

    s = text.strip()
    if not s:
        return s

    s = re.sub(r"\$\$([^$]+)\$\$", r"\1", s)
    s = re.sub(r"\$([^$]+)\$", r"\1", s)

    while _FRAC_PATTERN.search(s):
        s = _FRAC_PATTERN.sub(lambda m: _format_frac(m.group(1), m.group(2)), s)

    replacements = [
        (r"\\times", "×"),
        (r"\\div", "÷"),
        (r"\\cdot", "·"),
        (r"\\leq", "≤"),
        (r"\\geq", "≥"),
        (r"\\neq", "≠"),
        (r"\\approx", "≈"),
        (r"\\pi", "π"),
        (r"\\infty", "∞"),
        (r"\\pm", "±"),
        (r"\\left\s*", ""),
        (r"\\right\s*", ""),
        (r"\\sqrt\{([^{}]+)\}", r"√(\1)"),
        (r"\\text\{([^{}]+)\}", r"\1"),
        (r"\\,", ""),
        (r"\\;", " "),
        (r"\\!", ""),
    ]
    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s)

    s = re.sub(r"([a-zA-Z0-9])\^2\b", r"\1²", s)
    s = re.sub(r"([a-zA-Z0-9])\^3\b", r"\1³", s)
    s = re.sub(r"\\([a-zA-Z]+)", r"\1", s)
    s = re.sub(r"\(\s*\)\s*\(\s*\)", "（ ）", s)
    s = re.sub(r"\(\s{2,}\)", "（ ）", s)
    s = re.sub(r"[（(]\s*\d+\s*分\s*[）)]\s*$", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def normalize_question_math_fields(question: Dict[str, Any]) -> Dict[str, Any]:
    q = dict(question or {})
    for key in ("stem", "content"):
        if q.get(key):
            q[key] = normalize_exam_math_notation(str(q[key]))
    opts = q.get("options")
    if isinstance(opts, list):
        q["options"] = [normalize_exam_math_notation(str(o)) for o in opts]
    subs = q.get("subQuestions")
    if isinstance(subs, list):
        q["subQuestions"] = [normalize_exam_math_notation(str(s)) for s in subs]
    return q


def normalize_questions_math_notation(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [normalize_question_math_fields(q) for q in (questions or [])]
