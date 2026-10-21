# -*- coding: utf-8 -*-
"""
作文批改（独立逻辑）：
1) 百度手写作文 OCR：create_task / get_result
2) 将 OCR 文本 + 用户自定义批改标准 + 固定提示词 发送给项目现有通义千问（DashScope compatible OpenAI API）

注意：本模块只做“识别 + 文本批改”，不生成留痕图，不写入原 grading_history，避免与试卷批改互通。
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests


from app.grading.baidu_grading import (
    _create_rate_limiter,
    _get_access_token,
    _get_rate_limiter,
)
from app.grading.baidu_grading import _post_json as _baidu_post_json
from app.grading.doc_convert import enhance_for_ocr

BAIDU_CREATE_TASK_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/handwriting_composition/create_task"
BAIDU_GET_RESULT_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/handwriting_composition/get_result"

_baidu_token_cache = {"token": "", "expires_at": 0}

def _baidu_access_token() -> str:
    global _baidu_token_cache
    if _baidu_token_cache["token"] and time.time() < _baidu_token_cache["expires_at"]:
        return _baidu_token_cache["token"]
        
    token = _get_access_token()
    if token:
        _baidu_token_cache["token"] = token
        _baidu_token_cache["expires_at"] = time.time() + 86400
        return token
    raise RuntimeError("获取百度OCR Token失败：请检查数据库中的 baidu_access_token 配置")

def _post_json(url: str, body: dict) -> dict:
    """走 baidu_grading 统一 _post_json：滑动窗口限流 + QPS(18) 指数退避 + token 失效刷新。

    handwriting_composition 此前是全链路唯一裸调百度的口子，批量作文会突发打爆 QPS。
    create_task/get_result 各用自己的限流器（对齐批改君作文链路）。
    """
    limiter = _create_rate_limiter if "create_task" in url else _get_rate_limiter
    return _baidu_post_json(url, body, timeout=30, limiter=limiter)


def _prepare_submit_image_bytes(image_path: str) -> bytes:
    """读图并返回待提交字节：GRADING_OCR_ENHANCE=off 时保持原始字节（行为不变）；
    否则对同尺寸增强副本转 JPEG（enhance_for_ocr 内部按 env 自动/激进，任何异常回退原始字节）。

    与 baidu_grading._prepare_submit_image_bytes 思路一致；本模块自包含实现，避免跨模块私有耦合。
    """
    mode = os.environ.get("GRADING_OCR_ENHANCE", "auto").strip().lower()
    if mode == "off":
        with open(image_path, "rb") as f:
            return f.read()
    try:
        from io import BytesIO as _BytesIO
        from PIL import Image as _Image

        with _Image.open(image_path) as im:
            enhanced = enhance_for_ocr(im)  # mode 缺省，内部按 env 决定档位
        buf = _BytesIO()
        enhanced.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    except Exception:
        with open(image_path, "rb") as f:
            return f.read()  # 增强失败回退原始字节


def baidu_essay_create_task(image_path: str) -> str:
    """上传作文图片到百度OCR，返回 task_id。"""
    img = base64.b64encode(_prepare_submit_image_bytes(image_path)).decode("utf-8")
    url = f"{BAIDU_CREATE_TASK_URL}?access_token={_baidu_access_token()}"
    data = _post_json(url, {"image": img})
    if int(data.get("error_code") or 0) != 0:
        raise RuntimeError(f"百度OCR上传失败: {data.get('error_msg') or data}")
    task_id = ((data.get("result") or {}) or {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"百度OCR未返回 task_id: {data}")
    return str(task_id)


def baidu_essay_get_result(task_id: str) -> dict:
    """查询 task_id 对应的结果。"""
    url = f"{BAIDU_GET_RESULT_URL}?access_token={_baidu_access_token()}"
    data = _post_json(url, {"task_id": str(task_id)})
    if int(data.get("error_code") or 0) != 0:
        raise RuntimeError(f"百度OCR查询失败: {data.get('error_msg') or data}")
    return data


def baidu_essay_parse_status(data: dict) -> Tuple[str, str, str]:
    """
    解析百度 get_result 返回。
    返回 (status, titleText, contentText)：
    - status: pending/processing/success/failed/unknown
    """
    res = (data.get("result") or {}) or {}
    status = str(res.get("status") or "").strip().lower() or "unknown"
    if status != "success":
        return status, "", ""
    essay_res = (res.get("result") or {}) or {}
    overall = (essay_res.get("essayOverall") or {}) or {}
    title = str(overall.get("titleText") or "").strip()
    content = str(overall.get("contentText") or "").strip()
    return status, title, content


def baidu_essay_poll_text(
    image_path: str,
    *,
    poll_interval_sec: float = 1.2,
    timeout_sec: float = 60.0,
    stop_event=None,
) -> Tuple[str, str]:
    """
    上传并轮询直到 success/failed。
    返回 (titleText, contentText)，若缺失则返回空字符串。
    """
    task_id = baidu_essay_create_task(image_path)
    start = time.time()
    while True:
        if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
            raise RuntimeError("已停止批改")
        data = baidu_essay_get_result(task_id)
        res = (data.get("result") or {}) or {}
        status = str(res.get("status") or "").strip().lower()
        if status == "success":
            essay_res = (res.get("result") or {}) or {}
            overall = (essay_res.get("essayOverall") or {}) or {}
            title = str(overall.get("titleText") or "").strip()
            content = str(overall.get("contentText") or "").strip()
            return title, content
        if status == "failed":
            raise RuntimeError(f"百度OCR处理失败: {data}")
        if time.time() - start > timeout_sec:
            raise RuntimeError("百度OCR超时，请稍后重试")
        time.sleep(poll_interval_sec)


ESSAY_SYSTEM_PROMPT_TEMPLATE = """你是一名经验丰富的语文作文阅卷老师。你将收到：作文题目、作文正文、以及用户自定义的「批改标准」与各板块要求。

【最高优先级】用户自定义的批改标准与各板块 Prompt 是批改依据。评分、老师总评、习作提升、写作指导必须严格遵照用户规则执行。【作文分段概述】格式由系统固定为 4 句旁批（开头/中间一/中间二/结尾各 1 句），不得增减；4 句话写什么、如何评价，必须严格按用户自定义要求执行。

你的任务是输出一份【A4 单页作文批改报告】。内容要充实、具体、可打印，目标占用一页 A4 的大半页到接近一页，但不要写到第二页。

一、篇幅硬性要求：
1) 最终可见内容建议控制在 1100-1400 个汉字左右。
2) 不要少于 1000 个汉字，避免报告只占半页。
3) 不输出完整范文，不写长段落，不展开复述原文，不复述用户批改标准原文。
4) 每个板块都要具体到这篇作文，句子简洁，避免套话和重复。

二、输出结构要求，顺序固定：
【作文分段概述】
【老师总评】
【习作提升】
【写作指导】

三、各板块内容要求：
【作文分段概述】{summary_prompt}
【老师总评】{comment_prompt}
【习作提升】{rewrite_prompt}
【写作指导】{guidance_prompt}

四、关于评分的隐藏规则（极其重要，必须严格执行）：
1) {scoring_prompt}
2) 必须按以下评分维度分别打分，各维度得分之和即作文总分：
{dimension_section}
3) 对每个维度给出 0 到该维度满分 的整数分，不要出现小数；所有维度得分之和必须等于作文总分。
4) 但是，不要在报告正文中输出任何“【评分】”、“得分”、“扣分”等相关的板块或文字说明，也就是说正文中绝对不显示评分这一栏。
5) 如果你给出了具体总分，请务必在整个回答的最末尾、另起一行，仅仅输出程序的评分标签：`<essay_score>你的分数</essay_score>`。例如：`<essay_score>45</essay_score>` 或 `<essay_score>88.5</essay_score>`。这个标签只用于程序识别，千万不要在正文里解释它，也不要在正文提及分数。
6) 在 `<essay_score>` 标签之后，再另起一行，单独输出维度得分的隐藏标签：`<essay_dimensions>{{"维度key":得分,"维度key":得分,...}}</essay_dimensions>`。例如：`<essay_dimensions>{{"content":20,"structure":16,"language":22,"relevance":12,"presentation":13}}</essay_dimensions>`。要求：key 必须严格使用上面给出的维度 key；value 为该维度 0 到满分 的整数得分；所有维度得分之和必须等于 `<essay_score>` 中的总分。该标签同样只用于程序识别，千万不要在正文里解释它，也不要在正文提及分数。

五、格式规范：
1) 使用中文标点和自然换行。
2) 各板块标题必须严格使用中文方括号，例如【作文分段概述】【老师总评】【习作提升】【写作指导】，禁止使用 Markdown 的 #、##、### 或 ** 作为标题。
3) 不使用 Markdown 表格、粗体、装饰符号、表情或分隔线。
4) 不要出现“以下是”“范文如下”“根据标准”等引导语。

六、异常情况：
如果正文为空、明显识别失败或与题目无关，仍按上述结构输出，但内容改为提示重新拍照或扫描，并给出简短拍摄建议；如果可以给分，依然在最后输出 `<essay_score>分数</essay_score>`。

七、OCR 噪声宽容：
正文来自手写 OCR，可能存在错别字或漏字，请按上下文语义理解内容，不要逐字扣错字，正常进行评分与评语。"""

DEFAULT_PROMPTS = {
    "summary_content_prompt": "结合本篇作文具体内容；语言简洁像老师旁批；分别点评开头、中间两部分与结尾的亮点或问题；每句写完整、不要省略。",
    "comment_prompt": "4-5 句，概括主要优点、主要问题、提升方向和一句鼓励。",
    "rewrite_prompt": "要求你对整篇文章进行重写！意思就是从头到尾进行作文的提升重写在此栏，提供一篇完整的、升格后的高质量作文。在保持原作者核心立意和基本素材的前提下，全面优化文章结构、语言表达、行文逻辑等，字数要和原文字数相当或略多。自然段之间空一行；段首缩进由系统自动处理，正文里不要写 \\u3000 或全角空格。",
    "guidance_prompt": "写 4 条，每条 35-55 字，覆盖结构、细节、语言、立意中的关键问题。",
    "scoring_prompt": "必须严格根据用户「批改标准」中的评分细则、分值区间、扣分项进行打分，不得自行套用其他标准。",
}

# 语文作文满分 100 的默认五维评分维度（A2-B1 维度化批改）。
# 各维度 full_score 之和为 100；weight 与 full_score 语义一致，保留冗余以便前端展示占比。
DEFAULT_DIMENSIONS = [
    {"key": "content", "name": "内容与立意", "full_score": 25, "weight": 0.25, "description": "立意是否明确、材料是否充实、中心是否突出", "order": 1},
    {"key": "structure", "name": "结构与思路", "full_score": 20, "weight": 0.20, "description": "开头/中段/结尾是否完整、过渡与层次是否清晰", "order": 2},
    {"key": "language", "name": "语言表达", "full_score": 25, "weight": 0.25, "description": "用词、句式、文采、通顺度", "order": 3},
    {"key": "relevance", "name": "扣题程度", "full_score": 15, "weight": 0.15, "description": "是否紧扣题目要求（结合 topic 判断偏题/跑题）", "order": 4},
    {"key": "presentation", "name": "卷面与篇幅", "full_score": 15, "weight": 0.15, "description": "字数是否达标、卷面/书写", "order": 5},
]

# 语文作文等级制（R18/R16）：按得分占比推导五级等级。
# 阈值（得分占比下限）从高到低排列，首个命中的即等级。
_ESSAY_GRADE_LEVELS = [
    (0.90, "优秀"),
    (0.80, "良好"),
    (0.70, "中等"),
    (0.60, "及格"),
    (0.00, "不及格"),
]


def dimensions_total(dimensions: Optional[list[dict]] = None) -> float:
    """维度配置满分之和（缺省默认五维满分 100）。"""
    dims = dimensions if dimensions is not None else DEFAULT_DIMENSIONS
    total = 0.0
    for d in dims or []:
        try:
            total += float((d or {}).get("full_score") or 0)
        except (TypeError, ValueError):
            continue
    return total if total > 0 else 100.0


def derive_essay_grade(score_total, dimensions: Optional[list[dict]] = None) -> str:
    """把作文总分映射为五级等级（优秀/良好/中等/及格/不及格）。

    阈值按得分占比（score / 维度满分之和）划分，因此与总分制（60/100 分等）无关；
    score_total 非法或缺失时返回空串。
    """
    try:
        score = float(score_total)
    except (TypeError, ValueError):
        return ""
    total = dimensions_total(dimensions)
    if total <= 0:
        return ""
    ratio = score / total
    for threshold, label in _ESSAY_GRADE_LEVELS:
        if ratio >= threshold:
            return label
    return "不及格"


def _build_dimension_section(dimensions: Optional[list[dict]] = None) -> str:
    """将维度配置格式化为「维度名（满分 X 分）：评分标准描述」文本。"""
    if not dimensions:
        return ""
    lines = []
    for d in dimensions:
        name = str((d or {}).get("name") or (d or {}).get("key") or "").strip()
        full = (d or {}).get("full_score")
        desc = str((d or {}).get("description") or "").strip()
        if full is None:
            lines.append(f"{name}：{desc}".strip("：") if desc else name)
        else:
            lines.append(f"{name}（满分 {full} 分）：{desc}".rstrip("："))
    return "\n".join(lines)

# 【作文分段概述】格式固定四句；内容由用户 summary_prompt 决定
ESSAY_SUMMARY_FORMAT_RULE = """格式固定（系统规定，不可更改）：本板块只能输出以下 4 行旁批，每行 1 句，将印在试卷右侧留痕，严禁增减行数、合并行或增加小标题：
开头：（1 句）
中间一：（1 句）
中间二：（1 句）
结尾：（1 句）"""


def _build_summary_prompt(user_content_rule: str) -> str:
    """合并固定四句格式 + 用户自定义旁批内容要求。"""
    content_rule = str(user_content_rule or "").strip() or DEFAULT_PROMPTS["summary_content_prompt"]
    return (
        f"{ESSAY_SUMMARY_FORMAT_RULE}\n\n"
        f"旁批内容要求（用户自定义，决定上述 4 句话写什么、怎么评，必须严格执行）：\n"
        f"{content_rule}"
    )


_ESSAY_PARAGRAPH_INDENT = "\u3000\u3000"


def _strip_literal_u3000(text: str) -> str:
    """去掉 AI 误输出的字面量 \\u3000，保留真实全角空格。"""
    return re.sub(r"(?:\\u3000)+", "", text or "")


def _strip_line_leading_indent(line: str) -> str:
    return line.lstrip("\u3000 \t")


def _apply_rewrite_paragraph_indent(text: str) -> str:
    """为习作提升每个非空段落加上两个全角空格的首行缩进。"""
    lines = []
    for line in (text or "").split("\n"):
        stripped = _strip_line_leading_indent(line)
        if stripped:
            lines.append(_ESSAY_PARAGRAPH_INDENT + stripped)
        else:
            lines.append("")
    return "\n".join(lines)


_ESSAY_CANONICAL_SECTIONS = (
    "作文得分",
    "作文分段概述",
    "老师总评",
    "习作提升",
    "写作指导",
    "评分",
)


def normalize_essay_section_headers(text: str) -> str:
    """将 Markdown 标题等变体统一为【板块名】，便于留痕提取与 PDF 排版。"""
    if not text:
        return text
    out = str(text).replace("\r\n", "\n").replace("\r", "\n")
    for name in _ESSAY_CANONICAL_SECTIONS:
        bracketed = f"【{name}】"
        out = re.sub(
            rf"^#{{1,6}}\s*{re.escape(name)}\s*[：:]?\s*$",
            bracketed,
            out,
            flags=re.M,
        )
        out = re.sub(
            rf"^\*\*{re.escape(name)}\*\*\s*[：:]?\s*$",
            bracketed,
            out,
            flags=re.M,
        )
        out = re.sub(
            rf"^(?!【){re.escape(name)}\s*[：:]\s*$",
            bracketed,
            out,
            flags=re.M,
        )
    return out


def normalize_essay_result_text(text: str) -> str:
    """统一板块标题格式、清理字面量 \\u3000，并为【习作提升】加上段首缩进。"""
    if not text:
        return text
    cleaned = normalize_essay_section_headers(_strip_literal_u3000(text))
    if "【习作提升】" not in cleaned:
        return cleaned

    parts = re.split(r"(【习作提升】)", cleaned, maxsplit=1)
    if len(parts) < 3:
        return cleaned

    before, title, after = parts[0], parts[1], parts[2]
    next_idx = after.find("【")
    if next_idx == -1:
        rewrite_content, rest = after, ""
    else:
        rewrite_content, rest = after[:next_idx], after[next_idx:]

    rewrite_content = _apply_rewrite_paragraph_indent(rewrite_content)
    return before + title + rewrite_content + rest


def _merge_section_prompt(user_v: str, default_v: str) -> str:
    """用户自定义板块要求优先，未填写时使用默认。"""
    user_v = str(user_v or "").strip()
    return user_v if user_v else default_v


def _build_rubric_section(rubric_text: str, custom_prompts: dict) -> str:
    """汇总用户批改标准正文与各板块自定义要求。"""
    parts: list[str] = []
    body = str(rubric_text or "").strip()
    if body:
        parts.append(body)

    section_labels = (
        ("scoring_prompt", "【评分细则（用户自定义）】"),
        ("summary_prompt", "【旁批/分段概述内容要求（用户自定义，格式固定四句）】"),
        ("comment_prompt", "【老师总评要求（用户自定义）】"),
        ("rewrite_prompt", "【习作提升要求（用户自定义）】"),
        ("guidance_prompt", "【写作指导要求（用户自定义）】"),
    )
    for key, label in section_labels:
        value = str((custom_prompts or {}).get(key) or "").strip()
        if value:
            parts.append(f"{label}\n{value}")

    return "\n\n".join(parts) if parts else "（未填写，按常规中考/期中作文标准批改）"


def _resolve_essay_model() -> str:
    from app.utils.qwen_settings import resolve_qwen_model

    return resolve_qwen_model(env_var="ESSAY_GRADE_MODEL")


def grade_essay_with_qwen(
    title: str,
    content: str,
    rubric_text: str,
    custom_prompts: dict = None,
    dimensions: Optional[list[dict]] = None,
) -> str:
    """
    调用项目已有 DashScope compatible OpenAI API（在 grading/pipeline.py 中已配置）。
    文字题目与图片题目均使用 qwen3.7-plus（可通过 ESSAY_GRADE_MODEL 覆盖）。

    dimensions: 评分维度配置（list[dict]），缺省使用 DEFAULT_DIMENSIONS；
    维度化评分通过 prompt 中的 {dimension_section} 注入。
    """
    from app.grading.pipeline import _get_openai_client
    from app.utils.qwen_settings import QWEN_CHAT_EXTRA_BODY

    if custom_prompts is None:
        custom_prompts = {}

    dims = list(dimensions) if dimensions else list(DEFAULT_DIMENSIONS)

    merged_prompts = {
        "summary_prompt": _build_summary_prompt(str(custom_prompts.get("summary_prompt") or "").strip()),
    }
    for k, default_v in DEFAULT_PROMPTS.items():
        if k == "summary_content_prompt":
            continue
        merged_prompts[k] = _merge_section_prompt(
            str(custom_prompts.get(k) or "").strip(),
            default_v,
        )
    merged_prompts["dimension_section"] = _build_dimension_section(dims)

    system_prompt = ESSAY_SYSTEM_PROMPT_TEMPLATE.format(**merged_prompts)
    rubric_section = _build_rubric_section(rubric_text, custom_prompts or {})

    client = _get_openai_client()
    model = _resolve_essay_model()

    topic_text = (custom_prompts.get("topic_text") or "").strip()
    topic_image_base64 = (custom_prompts.get("topic_image_base64") or "").strip()

    print("===== ESSAY GRADING DEBUG =====")
    print("model:", model)
    print("topic_text len:", len(topic_text))
    print("topic_image_base64 len:", len(topic_image_base64))
    print("===============================")

    if topic_image_base64:
        topic_section = (
            "【极其重要】本次批改附带了一张题目图片（看图说话/图画作文类）。"
            "该图片即本次作文的【官方指定题目】，请结合画面中的场景、人物、动作与细节理解题意，"
            "并据此审视下方「作文正文」是否紧扣画面、是否偏题跑题。"
            "若作文与画面内容无关，必须在【老师总评】首句指出严重偏题/跑题，并给出极低分数。"
            "（题意以上方图片为准，勿仅当作文字题处理。）"
        )
    elif topic_text:
        topic_section = f"【极其重要警告】本次作文的【官方指定题目和写作要求】如下：\n{topic_text}\n你必须以上述内容为唯一基准，审视下方的“作文正文”。如果发现作文内容与题目要求毫无关系、或者是默写的其他文章，请【必须】在【老师总评】的开头第一句话严厉指出“严重偏题/跑题”，并且必须在最后打分时给出极低的分数！"
    else:
        topic_section = "（未填写）"

    user_prompt_text = f"""{system_prompt}

====================

【批改标准（用户自定义，批改时必须严格遵守）】
{rubric_section}

【识别到的作文题目（OCR）】
{(title or '').strip()}

【老师给定的作文题目要求】
{topic_section}

【作文正文】
{(content or '').strip()}

请严格按上述要求输出报告。评分、总评、习作提升、写作指导须以「批改标准」及用户各板块要求为准；【作文分段概述】格式固定四句，内容按用户旁批要求撰写。
各板块标题必须使用【】括起（如【老师总评】），禁止使用 ### 或 ## 等 Markdown 标题。
特别警告：你必须在整个回答的【最末尾】先单独输出程序的评分标签：`<essay_score>具体分数</essay_score>`（例如：`<essay_score>45</essay_score>` 或 `<essay_score>38.5</essay_score>`，标签内部【只能包含数字】，严禁出现其他文字），紧接着另起一行输出维度得分隐藏标签 `<essay_dimensions>{{"维度key":得分,...}}</essay_dimensions>`（例如：`<essay_dimensions>{{"content":20,"structure":16,"language":22,"relevance":12,"presentation":13}}</essay_dimensions>`），所有维度得分之和必须等于 `<essay_score>` 中的总分。这两个标签都只用于程序识别，千万不要在正文里出现或解释，也不要在正文提及分数。
同时请你作为一名严苛的阅卷老师，仔细阅读并对比“老师给定的作文题目要求”，对这篇作文是否偏题、跑题进行极其严格的评判！一旦偏题，绝不能给高分！
"""
    
    if topic_image_base64:
        user_content = [
            {"type": "image_url", "image_url": {"url": topic_image_base64}},
            {"type": "text", "text": user_prompt_text}
        ]
    else:
        user_content = user_prompt_text

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": user_content},
        ],
        timeout=180,  # 增加超时时间防止断开
        extra_body=QWEN_CHAT_EXTRA_BODY,
    )
    raw = (resp.choices[0].message.content or "").strip()
    return normalize_essay_result_text(raw)


def regrade_essay_with_qwen(
    title: str,
    content: str,
    rubric_text: str,
    custom_prompts: dict = None,
    dimensions: Optional[list[dict]] = None,
) -> str:
    """局部重批：复用已存 OCR 文本 + 既有批改配置重新生成点评（A2-B2）。

    语义：不重新 OCR、不重新走整篇批改链路，仅用「给定维度分（dimensions 的
    full_score 即改后得分）」替换评分配置后重新生成整篇报告。

    与 grade_essay_with_qwen 共享同一套 prompt 组装与输出归一化，逻辑高度重合，
    故直接复用主函数，本函数作为改分端点调用的语义入口，方便测试打桩。
    """
    return grade_essay_with_qwen(title, content, rubric_text, custom_prompts, dimensions)
