# -*- coding: utf-8 -*-
"""AI 出题共用逻辑（不接题库时的 AI 题源）。

供分层组卷 AI 题源（compose_tiered_papers_ai）与错题变式 AI 出题复用：
- 提示词口径对齐 routers/exams.py 的 AI 组卷（题型/数量/分数 + 严格 JSON 数组输出），
  但额外要求 answer/analysis 字段（分层卷预览/打印/配套练习要显示答案与解析）。
- get_llm_config 必须传 db（key 在 SystemSettings 表）。
- 输出统一 ExamQuestion 形状（id/type/stem/content/options/score/answer/analysis/
  knowledge_point/difficulty/is_ai），type 取英文枚举，便于直接进试卷库。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from app.services.redline_filter import filter_dict, filter_text
from app.utils.exam_math_format import (
    MATH_EXAM_FORMAT_PROMPT,
    is_math_related_subject,
    normalize_questions_math_notation,
)
from app.utils.qwen_settings import get_llm_config, get_llm_thinking_extra

logger = logging.getLogger(__name__)

# 英文题型枚举 → 提示词里的中文名（输出 type 仍为英文，直接是 ExamQuestion.type）
TYPE_ZH: Dict[str, str] = {
    "choice": "选择题",
    "fill": "填空题",
    "judge": "判断题",
    "short_answer": "简答题",
    "essay": "作文",
    "matching": "连线匹配题",
    "ordering": "排序题",
    "reading": "阅读理解题",
    "cloze": "完形填空题",
    "calculation": "计算题",
    "application": "应用题",
}
VALID_TYPES = tuple(TYPE_ZH.keys())

# 层难度偏好 → 提示词难度描述（与 tier_strategy 的 difficulty_pref 同口径）
_TIER_DIFFICULTY_ZH: Dict[str, str] = {
    "hard": "偏难（综合与压轴题为主）",
    "medium": "中等（标准难度）",
    "easy": "偏易（基础巩固为主）",
}


class AIGenerationError(RuntimeError):
    """AI 出题失败（调用方转 500/降级）；message 面向用户。"""


def tier_difficulty_text(difficulty_pref: Optional[str]) -> str:
    return _TIER_DIFFICULTY_ZH.get((difficulty_pref or "").strip().lower(), "中等（标准难度）")


def default_requirements(count: int) -> List[Dict[str, Any]]:
    """未指定题型模板时的缺省配比：选择 40% / 填空 30% / 判断 10% / 简答 20%。"""
    n = max(1, int(count or 10))
    c = max(1, round(n * 0.4)) if n >= 4 else n
    f = max(1, round(n * 0.3)) if n >= 4 else 0
    j = 1 if n >= 6 else 0
    s = max(0, n - c - f - j)
    if s == 0 and n >= 4:
        # 挤一点给简答，避免全是客观题
        s = 1
        if c > 1:
            c -= 1
    reqs = [
        {"type": "choice", "count": c, "score": 3},
        {"type": "fill", "count": f, "score": 2},
        {"type": "judge", "count": j, "score": 1},
        {"type": "short_answer", "count": s, "score": 5},
    ]
    return [r for r in reqs if r["count"] > 0]


def _filter_redline_question(q: Dict[str, Any]) -> Dict[str, Any]:
    """红线词过滤单题（同 exams._filter_redline_exam_question，含 options 子串列表）。"""
    if not isinstance(q, dict):
        return q
    q = filter_dict(q, ["stem", "content", "analysis", "explanation", "answer"])
    for key in ("options", "subQuestions"):
        items = q.get(key)
        if isinstance(items, list):
            q[key] = [filter_text(item) if isinstance(item, str) else item for item in items]
    return q


def _build_prompt(
    *,
    subject: str,
    grade: Optional[str],
    term: Optional[str],
    difficulty: Optional[str],
    topics: Sequence[str],
    requirements: Sequence[Dict[str, Any]],
    extra_note: str = "",
) -> str:
    req_lines = []
    for r in requirements:
        rtype = str(r.get("type") or "short_answer")
        zh = TYPE_ZH.get(rtype, rtype)
        req_lines.append(
            f"- 题型：{zh}（type 填 \"{rtype}\"），数量：{int(r.get('count') or 1)}题，"
            f"单题分数：{float(r.get('score') or 5)}分"
        )
    req_str = "\n".join(req_lines) if req_lines else "- 题型：简答题，数量：5题，单题分数：5分"
    subj = (subject or "").strip()
    math_format_block = MATH_EXAM_FORMAT_PROMPT if is_math_related_subject(subj) else ""
    kp_text = "、".join([str(t).strip() for t in topics if str(t).strip()]) or "未指定（请按该学科该年级常考知识点出题）"
    coverage_note = ""
    if len([t for t in topics if str(t).strip()]) > 1:
        coverage_note = (
            f"【知识点覆盖】：本次需覆盖以下 {len(topics)} 个知识点，题目请大致均匀地分布到这些知识点上，"
            f"不要全部集中在一个知识点：{kp_text}\n"
        )
    extra_block = f"【出题备注】：{extra_note}\n" if (extra_note or "").strip() else ""

    return f"""你是一个专业的中国中小学教师。请根据以下要求生成题目：

【学科】：{subj or "未指定（请根据知识点推断，数学/物理/化学题必须遵守下方符号规范）"}
【知识点】：{kp_text}
【年级】：{grade or "未指定"}
【学期】：{term or "未指定"}
【难度】：{difficulty or "中等"}
{extra_block}{coverage_note}
【题目要求】：
{req_str}
{math_format_block}

请务必直接输出一个标准的 JSON 数组，包含所有生成的题目（不要输出 markdown 的 ```json 块，也不要输出任何前缀或后缀说明，只输出纯 JSON 数组）。
每个题目对象的字段必须包含：
- id: 随机的唯一字符串（例如 "q_12345"）
- type: 题型的英文字符串（必须是 "choice", "fill", "judge", "short_answer", "essay", "matching", "ordering", "reading", "cloze", "calculation", "application" 中的一个）
- stem: 题干或背景材料（reading 必须填阅读材料全文；其余如果没有可为空字符串）
- content: 题目具体内容或问题（cloze 填含空白的篇章，空白处用「＿＿＿」表示；calculation/application 填计算题/应用题题干）
- score: 数字（使用上方提供的分数）
- options: 字符串数组（choice 提供4个选项；matching 提供左列4项；ordering 提供需按正确顺序排列的乱序项；cloze 可选提供候选词。注意：只输出内容本身，绝对不要在内容前面加上 "A."、"B."、"C."、"D." 这样的前缀！因为前端试卷上已经自带序号标签了）
- subQuestions: 字符串数组（short_answer/reading 提供1到3个子问题；matching 提供右列与左列一一对应的4项；其余为空数组）
- answer: 参考答案（客观题给选项内容或字母，主观题给标准答案要点）
- analysis: 简要解析（一两句话说清考点与解题关键）
- knowledge_point: 本题对应的考点名称

示例格式：
[
  {{
    "id": "q_abc1",
    "type": "choice",
    "stem": "",
    "content": "若 a、b 互为倒数，c、d 互为相反数，且 |m|=2，则代数式 2ab-(c+d)/m+m² 的值为（ ）",
    "score": 5,
    "options": ["-3", "-1", "1", "3"],
    "answer": "-1",
    "analysis": "由倒数与相反数性质化简后代入 |m|=2 计算。",
    "knowledge_point": "有理数运算"
  }},
  {{
    "id": "q_abc2",
    "type": "short_answer",
    "stem": "阅读以下短文...",
    "content": "根据短文回答：",
    "score": 10,
    "subQuestions": ["第一段的主要内容是什么？", "作者表达了什么情感？"],
    "answer": "第一段主要写……；作者表达了……之情。",
    "analysis": "抓住关键句概括段意，再结合描写手法体会情感。",
    "knowledge_point": "现代文阅读"
  }}
]
请确保生成的题目符合指定的知识点和难度，并且数量与要求完全一致。所有文字必须是学生可直接阅读的普通中文试卷用语，不要出现 LaTeX 或 Markdown 标记。
"""


def _parse_questions(raw_text: str) -> List[dict]:
    text = (raw_text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    data = json.loads(text)
    if not isinstance(data, list):
        raise AIGenerationError("AI 返回的不是 JSON 数组")
    return [q for q in data if isinstance(q, dict)]


def _normalize_question(q: dict, index: int) -> dict:
    """统一成 ExamQuestion 形状（缺项给安全缺省）。"""
    qtype = str(q.get("type") or "short_answer").strip()
    if qtype not in VALID_TYPES:
        qtype = "short_answer"
    options = q.get("options")
    if not isinstance(options, list):
        options = []
    sub_qs = q.get("subQuestions")
    if isinstance(sub_qs, list):
        subs = [str(s) for s in sub_qs]
    else:
        subs = []
    try:
        score = float(q.get("score") or (30 if qtype == "essay" else 5))
    except (TypeError, ValueError):
        score = 30 if qtype == "essay" else 5
    content = str(q.get("content") or "").strip()
    stem = str(q.get("stem") or "").strip()
    if subs and not content:
        content = " ".join(f"{i + 1}. {s}" for i, s in enumerate(subs))
    out = {
        "id": str(q.get("id") or f"q_ai_{index}"),
        "type": qtype,
        "stem": stem,
        "content": content,
        "options": [str(o) for o in options],
        "score": score,
        "answer": str(q.get("answer") or "").strip(),
        "analysis": str(q.get("analysis") or "").strip(),
        "knowledge_point": str(q.get("knowledge_point") or "").strip(),
        "is_ai": True,
    }
    return out


def llm_generate_questions(
    db,
    *,
    subject: str,
    grade: Optional[str] = None,
    term: Optional[str] = None,
    difficulty: Optional[str] = None,
    topics: Optional[Sequence[str]] = None,
    requirements: Optional[Sequence[Dict[str, Any]]] = None,
    extra_note: str = "",
    llm_cfg: Optional[Tuple[str, str, str]] = None,
) -> List[dict]:
    """LLM 出一套题（ExamQuestion 形状列表）。失败抛 AIGenerationError。

    llm_cfg=(base_url, api_key, model) 可预取后传入（多线程并发出卷时只读一次配置）。
    """
    reqs = [dict(r) for r in (requirements or []) if isinstance(r, dict)]
    reqs = [r for r in reqs if int(r.get("count") or 0) > 0]
    if not reqs:
        reqs = default_requirements(10)

    prompt = _build_prompt(
        subject=subject,
        grade=grade,
        term=term,
        difficulty=difficulty,
        topics=list(topics or []),
        requirements=reqs,
        extra_note=extra_note,
    )

    if llm_cfg is None:
        base_url, api_key, model = get_llm_config(db)
    else:
        base_url, api_key, model = llm_cfg
    if not api_key:
        raise AIGenerationError("系统设置中未配置文本大模型 API Key，无法生成试卷")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    payload.update(get_llm_thinking_extra(base_url))

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=180,
        )
        res_json = response.json()
        if response.status_code != 200 or "error" in res_json:
            err = (res_json.get("error") or {}).get("message") if isinstance(res_json, dict) else None
            raise AIGenerationError(f"AI生成错误: {err or res_json}")
        result_str = (
            (res_json.get("choices") or [{}])[0].get("message") or {}
        ).get("content", "").strip()
        questions = _parse_questions(result_str)
    except AIGenerationError:
        raise
    except Exception as e:
        logger.warning("ai_question_gen: llm call/parse failed", exc_info=True)
        raise AIGenerationError("AI 解析失败，请重试或修改提示词") from e

    subject_str = (subject or "").strip()
    if is_math_related_subject(subject_str):
        try:
            questions = normalize_questions_math_notation(questions)
        except Exception:
            logger.warning("ai_question_gen: math normalize failed", exc_info=True)

    out: List[dict] = []
    for i, q in enumerate(questions):
        try:
            q = _filter_redline_question(q)
        except Exception:
            pass  # best-effort：过滤器异常不阻断出题主流程
        out.append(_normalize_question(q, i))
    return out
