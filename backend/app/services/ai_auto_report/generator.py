# -*- coding: utf-8 -*-
"""千问流式生成批改自动分析报告。"""

from __future__ import annotations

import json
from typing import Any, Iterator

import requests
from sqlalchemy.orm import Session

from app.services.ai_chat_math_style import MATH_FORMAT_RULES
from app.services.redline_filter import RedlineFilter
from app.utils.anonymize import Anonymizer
from app.utils.qwen_settings import DEFAULT_QWEN_MODEL, QWEN_CHAT_EXTRA_BODY, get_llm_config

REPORT_TEMPERATURE = 0.35

_SMART_SYSTEM = """你是学校 AI 助教，根据教师「智能模型批改」已统分试卷数据，生成**简要**班级考试分析报告（Markdown）。

输入数据说明（参考靶向提升）：
- class：班级信息
- scope_note：分析范围说明（已纳入分析的统分学生人数）
- student_count：已纳入分析的统分学生数（与 score_ranking 条数一致）
- score_ranking / students：各试卷框（student_box）分数、错题、AI 批改摘要 grading_result_excerpt
- scored_file_count：仅作参考，为文件夹内已统分试卷文件数，**不等于**学生人数
- paper_records / wrong_records：来自 records 错题 JSON 的题目判定
- wrong_analysis：来自 analysis 错题 JSON 的 AI 解析
- wrong_question_images：错题裁剪图 URL（question_image / answer_image）
- top_wrong_questions：班级高频错题统计

报告结构（简洁，勿冗长）：
1. **分析范围**：说明本次纳入多少名已统分学生（必须引用 scope_note / student_count，按试卷框计人，禁止用 scored_file_count 或文件夹试卷总数）
2. **分数排名**：按 score_ranking 列出试卷框名称与分数（表格或有序列表）
3. **成绩概况**：平均分、最高/最低、分数分布一句话
4. **错题与知识点**：结合 top_wrong_questions、wrong_records、wrong_analysis、grading_result_excerpt 归纳 3～6 个知识点/题型问题，须有据
5. **需重点关注学生**：错题多或低分的试卷框（student_box），各 1～2 句，可引用具体错题
6. **教学建议**：2～3 条可操作建议

约束：
- 只分析数据中已出现的试卷框，禁止编造学生姓名、题号或分数
- 未纳入分析的试卷不要提及
- 语气专业、客观；数据不足时如实说明
- **禁止**使用 `#`、`##`、`###` 标题语法；小节标题用 **加粗** 即可
""" + MATH_FORMAT_RULES


_ESSAY_SYSTEM = """你是学校 AI 助教，根据教师「作文批改」数据生成简洁的班级作文分析报告（Markdown）。
分节：分数概况、写作共性问题、需关注学生、教学建议。禁止编造数据中不存在的内容。
**禁止**使用 `#`、`##`、`###` 标题语法；小节标题用 **加粗** 即可。
""" + MATH_FORMAT_RULES


def _sse_content_chunk(content: str) -> str:
    payload = json.dumps({"choices": [{"delta": {"content": content}}]}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


def _build_user_prompt(payload: dict[str, Any]) -> str:
    kind = payload.get("report_kind") or ""
    exam_name = payload.get("exam_name") or "本次考试"
    class_info = payload.get("class") or {}
    class_name = class_info.get("class_name") or ""
    header = f"考试：{exam_name}"
    if class_name:
        header += f"，班级：{class_name}"
    scope = payload.get("scope_note") or ""
    if scope:
        header += f"。{scope}"

    data_text = json.dumps(payload, ensure_ascii=False)
    if kind == "essay":
        return f"请根据以下作文批改数据生成简要报告。\n{header}\n\n数据（JSON）：\n{data_text}"
    return (
        f"请根据以下已统分试卷数据生成简要考试分析报告。\n{header}\n\n"
        f"数据（JSON，含批改摘要、错题 JSON、错题图片 URL）：\n{data_text}"
    )


def _system_prompt(payload: dict[str, Any]) -> str:
    if payload.get("report_kind") == "essay":
        return _ESSAY_SYSTEM
    return _SMART_SYSTEM


def _register_payload_names(anon: Anonymizer, db: Session, payload: dict[str, Any]) -> None:
    """从 payload 结构化字段 + 班级学生表登记全部学生真名，供 anon_text 全文本匿名。"""
    for item in payload.get("score_ranking") or []:
        if isinstance(item, dict) and item.get("student_box"):
            anon.anon(str(item["student_box"]))
    for item in payload.get("students") or []:
        if isinstance(item, dict) and item.get("student_box"):
            anon.anon(str(item["student_box"]))
    for question in payload.get("top_wrong_questions") or []:
        if isinstance(question, dict):
            for name in question.get("wrong_students") or []:
                anon.anon(str(name))
    for image in payload.get("wrong_question_images") or []:
        if isinstance(image, dict) and image.get("student_name"):
            anon.anon(str(image["student_name"]))
    class_meta = payload.get("class")
    if isinstance(class_meta, dict) and class_meta.get("class_id"):
        from app.models.student import Student

        rows = db.query(Student.name).filter(Student.class_id == class_meta["class_id"]).all()
        for (name,) in rows:
            anon.anon(name or "")


def stream_auto_report(db: Session, payload: dict[str, Any]) -> Iterator[str]:
    base_url, api_key, model = get_llm_config(db)
    if not api_key:
        yield _sse_content_chunk("系统未配置文本大模型 API Key，无法生成自动分析报告。请在系统设置中配置后重试。")
        yield _sse_done()
        return

    # PII 匿名化：payload 中可能嵌入学生姓名（student_box/文件名/批改摘要/错题图 URL 等），
    # 发千问前全文本匿名，流式返回文本里若出现匿名标识再 restore 回真名给前端展示。
    anon = Anonymizer()
    _register_payload_names(anon, db, payload)
    prompt_payload = anon.anon_text_deep(payload)

    messages = [
        {"role": "system", "content": _system_prompt(prompt_payload)},
        {"role": "user", "content": _build_user_prompt(prompt_payload)},
    ]
    body: dict[str, Any] = {
        "model": model or DEFAULT_QWEN_MODEL,
        "messages": messages,
        "temperature": REPORT_TEMPERATURE,
        "stream": True,
        **QWEN_CHAT_EXTRA_BODY,
    }
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=120,
            stream=True,
        )
    except Exception as e:
        yield _sse_content_chunk(f"调用千问模型失败：{e}")
        yield _sse_done()
        return

    if response.status_code != 200:
        try:
            err_body = response.json()
            msg = (err_body.get("error") or {}).get("message") if isinstance(err_body.get("error"), dict) else response.text[:200]
        except Exception:
            msg = response.text[:200]
        yield _sse_content_chunk(f"千问模型返回错误：{msg}")
        yield _sse_done()
        return

    # AI 输出红线词过滤：restore_text 之后、SSE yield 之前（best-effort，异常不阻断报告主流程）
    redline = RedlineFilter()
    done = False
    for raw in response.iter_lines(decode_unicode=True):
        if not raw:
            continue
        line = raw.strip()
        if line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            done = True
            break
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        content = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
        if content:
            try:
                text = redline.feed(anon.restore_text(content))
            except Exception:  # noqa: BLE001 - best-effort，过滤器异常不阻断流式
                text = anon.restore_text(content)
            if text:
                yield _sse_content_chunk(text)
    # 流结束：释放缓冲残留（在 [DONE] 之前发出，保持 SSE 事件顺序正确）
    try:
        tail = redline.flush()
    except Exception:  # noqa: BLE001 - best-effort
        tail = ""
    if tail:
        yield _sse_content_chunk(tail)
    if done:
        yield _sse_done()
