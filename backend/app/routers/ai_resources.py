# -*- coding: utf-8 -*-
"""AI 智能生成（互动课件 / 探究学案 / 多媒体资源）。

前端「智能生成」页（SmartGenPage）原调用 Supabase Edge Function `generate-courseware`，
但本系统为 FastAPI 后端 + RDS，无 Supabase，导致生成永远失败、页面仅展示硬编码 mock 数据。
此模块补齐真正的后端生成能力：复用通义千问（DashScope OpenAI 兼容接口），按 gen_type
生成结构化 Markdown 返回前端渲染，与 lesson_plans / exams 的 AI 端点保持一致——
统一走 E08 学校级 AI 管控（feature flag `smart_gen`）+ 敏感输入拦截。
"""
from __future__ import annotations

import json
import re
from io import BytesIO
from typing import List, Optional
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.ai_generation_history import AiGenerationHistory
from app.schemas.common import ApiResponse
from app.services.ai_policy import assert_no_sensitive_input, require_ai_access
from app.utils.qwen_settings import get_llm_config, get_llm_thinking_extra

router = APIRouter(prefix="/ai-resources", tags=["ai-resources"])

# gen_type -> 中文名 + 生成目标说明（用于 Prompt）
_GEN_TYPE_META = {
    "courseware": ("互动课件", "一份可直接投屏使用的互动课件逐页大纲：每一页给出页面标题、核心内容要点、以及一个互动/提问环节"),
    "worksheet": ("探究学案", "一份可打印分发的探究学案：包含学习目标、探究任务（分步骤）、分层练习（基础/提升）、课堂评价"),
    "multimedia": ("视频推荐", "一份与本课相关的视频推荐清单：列出视频主题、来源平台、搜索关键词、时长与课堂使用建议"),
}


class AiGenerateResourceRequest(BaseModel):
    gen_type: str
    subject: Optional[str] = None
    grade: Optional[str] = None
    content: str = ""
    objective: str = ""
    student_profile: str = ""
    requirements: str = ""


class AiGenerateResourceResult(BaseModel):
    title: str = ""
    markdown: str = ""


class AiGenerationHistorySummary(BaseModel):
    id: str
    gen_type: str
    subject: str = ""
    grade: str = ""
    title: str = ""
    created_at: Optional[str] = None


class AiGenerationHistoryItem(BaseModel):
    id: str
    gen_type: str
    subject: str = ""
    grade: str = ""
    title: str = ""
    content: str = ""
    created_at: Optional[str] = None


def _call_qwen(db: Session, prompt: str, *, max_tokens: int = 4096) -> str:
    base_url, api_key, qwen_model = get_llm_config(db)
    if not api_key:
        raise HTTPException(status_code=500, detail="系统设置中未配置文本大模型 API Key，无法生成资源")
    payload = {
        "model": qwen_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": max_tokens,
        **get_llm_thinking_extra(base_url),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=180)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"AI 服务请求失败: {str(e)}")
    try:
        res_json = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="AI 服务返回非 JSON 响应")
    if response.status_code != 200 or "error" in res_json:
        error_msg = res_json.get("error", {}).get("message", str(res_json))
        raise HTTPException(status_code=500, detail=f"AI生成错误: {error_msg}")
    content = (res_json.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return (content or "").strip()


def _extract_json_object(text: str) -> dict:
    s = (text or "").strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("AI 返回内容不是 JSON 对象")
    obj = json.loads(s[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("AI 返回内容不是 JSON 对象")
    return obj


@router.post("/generate", response_model=ApiResponse[AiGenerateResourceResult])
def ai_generate_resource(
    body: AiGenerateResourceRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """按 gen_type 生成课件/学案/多媒体资源，返回结构化 Markdown（不落库）。"""
    require_ai_access(db, user_id, "smart_gen")

    # 兼容前端传入中文标签（如「互动课件」）
    gen_type = (body.gen_type or "").strip()
    for key, (label, _) in _GEN_TYPE_META.items():
        if gen_type == label:
            gen_type = key
            break
    if gen_type not in _GEN_TYPE_META:
        raise HTTPException(status_code=400, detail="不支持的生成类型")

    if assert_no_sensitive_input("\n".join(filter(None, [
        body.subject, body.grade, body.content, body.objective, body.student_profile, body.requirements,
    ]))):
        raise HTTPException(status_code=403, detail="输入包含身份证号/手机号等敏感个人信息，请移除后重试")

    label, guide = _GEN_TYPE_META[gen_type]
    subject = (body.subject or "").strip()
    grade = (body.grade or "").strip()
    content = (body.content or "").strip()
    objective = (body.objective or "").strip()
    student_profile = (body.student_profile or "").strip()
    requirements = (body.requirements or "").strip()

    if gen_type == "courseware":
        # 互动课件需要逐页完整、内容充实，单独写一份更严格的生成指令
        prompt = f"""你是一名资深的中小学各学科名师与多媒体课件设计专家。请为下面这节课制作一份**内容充实、可直接投屏、逐页完整**的互动课件（PPT）。

【学科】：{subject or "未指定"}
【年级】：{grade or "未指定"}
【课题/教学内容】：{content or "未指定"}
【教学目标】：{objective or "未指定"}
【学生学情】：{student_profile or "未指定"}
【补充要求】：{requirements or "无"}

【硬性要求】
1. 篇幅：正文至少 10 页（只多不少），每一页都要有实质内容，拒绝空泛敷衍。
2. 结构完整，按教学环节依次展开（顺序不要打乱）：
   - 第1页「学习目标」：从知识与技能、过程与方法、情感态度价值观三个维度各写 1~2 条具体目标。
   - 第2页「情境导入」：设计一个贴近学生生活、与课题直接相关的情境或问题，并附 1~2 个引导提问。
   - 第3页起「新知探究」：拆成 2~4 页，每页聚焦一个知识点，写出核心结论、典型例子、方法步骤和易错提醒。
   - 穿插 2~3 页「互动探究」：写明互动形式（课堂提问/小组讨论/当堂小测等）、具体题目，以及预期回答或评价要点。
   - 「例题精讲」1~2 页：给出 1~2 个典型例题并写出分步解题过程。
   - 「分层练习」1 页：基础题、提升题、拓展题各至少 1 题（要把题目写出来）。
   - 最后一页「课堂总结 + 作业布置」：用要点回顾本节课核心内容，并布置具体作业。
3. 每页要点必须具体、可执行：禁止只写「讲解 XX」「了解 XX」这类空话，要写出关键结论、具体例子、方法步骤、易错提醒或具体问题，每页 3~5 条。
4. 语言用中文教学用语，可用 **加粗** 强调关键词；不要表格、不要 LaTeX。

【输出格式】只输出一个 JSON 对象（纯 JSON，不要 ```json 代码块、不要任何前缀或后缀说明）：
- title: 课件标题（字符串）
- content: 课件正文（字符串，Markdown 格式）
Markdown 约定（必须严格遵守）：
- 用 "# " 作为整份课件的总标题，只出现一次。
- 每一页用 "## " 开头，页标题写成「第X页 · 页名」（X 从 1 递增）。
- 页标题下方用 "- " 逐条列出该页要点。
- 用 **加粗** 强调关键词。

示例：
{{
  "title": "《……》互动课件",
  "content": "# 《……》互动课件\\n\\n## 第1页 · 学习目标\\n- **知识**：……\\n- **能力**：……\\n- **素养**：……\\n\\n## 第2页 · 情境导入\\n- ……\\n- 引导提问：……"
}}"""
    elif gen_type == "multimedia":
        prompt = f"""你是一名资深的中国中小学教师与教学资源推荐专家。请根据下面这节课的教学内容，推荐 5~8 个与课题紧密相关的视频资源，供老师直接用于课堂导入、知识讲解或拓展延伸。

【学科】：{subject or "未指定"}
【年级】：{grade or "未指定"}
【教学内容/课题】：{content or "未指定"}
【教学目标】：{objective or "未指定"}
【学生学情】：{student_profile or "未指定"}
【补充要求】：{requirements or "无"}

请务必直接输出一个标准 JSON 对象（不要输出 markdown 的 ```json 块，也不要任何前缀或后缀说明，只输出纯 JSON），字段如下：
- title: 资源标题（字符串，如「《……》相关视频推荐」）
- content: 资源正文（字符串，Markdown 格式）

正文 Markdown 要求：
- 用 "# " 作为整份清单总标题
- 每个视频用 "## " 开头作为视频小标题（如「视频1：……」）
- 每个视频下方用 "- " 逐条列出：来源平台、搜索关键词、时长建议、内容简介、课堂使用建议
- 优先推荐可稳定访问的公开平台（如：国家中小学智慧教育平台、央视网、学习强国、B站、腾讯视频、优酷等），并给出在该平台可搜索到的关键词
- 不要编造具体网址 URL；只给平台名 + 搜索关键词（除非能确认是公开稳定的官方链接）

请确保每个视频都与课题紧密相关、贴合学段实际，可直接帮助老师备课。"""
    else:
        prompt = f"""你是一名资深的中国中小学教师与多媒体教学设计专家。请根据以下信息生成一份教学资源。

【资源类型】：{label}
【生成目标】：{guide}
【学科】：{subject or "未指定"}
【年级】：{grade or "未指定"}
【教学内容/课题】：{content or "未指定"}
【教学目标】：{objective or "未指定"}
【学生学情】：{student_profile or "未指定"}
【补充要求】：{requirements or "无"}

请务必直接输出一个标准 JSON 对象（不要输出 markdown 的 ```json 块，也不要任何前缀或后缀说明，只输出纯 JSON），字段如下：
- title: 资源标题（字符串）
- content: 资源正文（字符串，Markdown 格式）

正文 Markdown 格式要求：
- 使用 # 表示大标题、## 表示小节标题
- 使用 - 或有序列表 1. 2. 3. 分条列出要点
- 使用 **加粗** 强调关键词
- 不要使用表格、不要使用 LaTeX，语言为普通中文教学用语

示例格式：
{{
  "title": "《……》互动课件",
  "content": "# 课题标题\\n\\n## 一、学习目标\\n- ……\\n\\n## 二、教学过程\\n1. 导入：……"
}}

请确保内容贴合学科与学段实际、结构完整、可直接用于课堂，且与用户输入的课题紧密相关。"""

    max_tokens = 8192 if gen_type == "courseware" else 4096
    raw = _call_qwen(db, prompt, max_tokens=max_tokens)
    try:
        obj = _extract_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=502, detail="AI 返回内容格式异常，请重试")

    def _as_str(v) -> str:
        return (v or "").strip() if isinstance(v, str) else ""

    markdown = _as_str(obj.get("content"))
    title = _as_str(obj.get("title"))
    if not markdown and not title:
        raise HTTPException(status_code=502, detail="AI 未返回有效内容，请重试")

    # 生成成功即落库，作为「生成历史」供前端回看/回填
    db.add(AiGenerationHistory(
        user_id=user_id,
        gen_type=gen_type,
        subject=subject,
        grade=grade,
        title=title,
        content=markdown,
    ))
    db.commit()

    return ApiResponse(data=AiGenerateResourceResult(title=title, markdown=markdown))


@router.get("/history", response_model=ApiResponse[List[AiGenerationHistorySummary]])
def list_ai_generation_history(
    limit: int = 30,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """列出当前用户的 AI 生成历史（最新在前，不含正文）。"""
    rows = (
        db.query(AiGenerationHistory)
        .filter(AiGenerationHistory.user_id == user_id)
        .order_by(AiGenerationHistory.created_at.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    data = [
        AiGenerationHistorySummary(
            id=r.id,
            gen_type=r.gen_type,
            subject=r.subject or "",
            grade=r.grade or "",
            title=r.title or "",
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return ApiResponse(data=data)


@router.get("/history/{history_id}", response_model=ApiResponse[AiGenerationHistoryItem])
def get_ai_generation_history(
    history_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """按 id 获取单条历史详情（含完整正文），供点击回填。"""
    row = (
        db.query(AiGenerationHistory)
        .filter(
            AiGenerationHistory.id == history_id,
            AiGenerationHistory.user_id == user_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="历史记录不存在")
    return ApiResponse(data=AiGenerationHistoryItem(
        id=row.id,
        gen_type=row.gen_type,
        subject=row.subject or "",
        grade=row.grade or "",
        title=row.title or "",
        content=row.content or "",
        created_at=row.created_at.isoformat() if row.created_at else None,
    ))


class AiGeneratePptxRequest(BaseModel):
    title: str = ""
    markdown: str = ""
    subject: Optional[str] = None
    grade: Optional[str] = None


def _parse_markdown_to_slides(markdown: str, title: str) -> list[dict]:
    """把课程 Markdown 大纲解析为 PPT 幻灯片列表：每页 {title, bullets}。"""
    lines = (markdown or "").splitlines()
    slides: list[dict] = []
    current_title = (title or "").strip() or "课件"
    current_bullets: list[str] = []
    max_bullets = 8

    def flush():
        # 只有真正含要点才生成一页，避免“# 总标题”或空标题产生空白页
        if current_bullets:
            slides.append({"title": current_title, "bullets": list(current_bullets)})

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        # 一级标题：整体课题（仅在尚未产生任何内容时作为标题，避免正文里的 # 顶掉页标题）
        if stripped.startswith("# ") and not stripped.startswith("## "):
            if not slides and not current_bullets:
                current_title = stripped[2:].strip() or current_title
            continue
        # 二级/三级标题：开启新的一页
        if stripped.startswith("### "):
            flush()
            current_title = stripped[4:].strip() or current_title
            current_bullets = []
            continue
        if stripped.startswith("## "):
            flush()
            current_title = stripped[3:].strip() or current_title
            current_bullets = []
            continue
        # 列表项 / 普通文本 → 该页要点
        bullet = stripped
        if bullet.startswith("- ") or bullet.startswith("* "):
            bullet = bullet[2:].strip()
        elif re.match(r"^\d+[.、]\s*", bullet):
            bullet = re.sub(r"^\d+[.、]\s*", "", bullet)
        if bullet:
            current_bullets.append(bullet)
            if len(current_bullets) >= max_bullets:
                flush()
                current_title = f"{current_title}（续）"
                current_bullets = []

    flush()
    return slides


def _strip_inline_md(text: str) -> str:
    """去除 Markdown 行内格式（**加粗**、`代码`），避免原样出现在 PPT 里。"""
    return (text or "").replace("**", "").replace("`", "").strip()


def _build_pptx_bytes(slides: list[dict], title: str, subject: str, grade: str) -> bytes:
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.oxml.ns import qn
    except ImportError:
        raise HTTPException(status_code=500, detail="服务端未安装 python-pptx，无法生成 PPT，请联系管理员")

    # ── 主题配色（教育风：深靛蓝主色 + 琥珀点缀 + 浅灰底） ──
    PRIMARY = RGBColor(0x2B, 0x3A, 0x67)   # 深靛蓝（封面/标题条）
    PRIMARY_SOFT = RGBColor(0x3A, 0x4C, 0x80)  # 稍亮同色（装饰）
    ACCENT = RGBColor(0xF5, 0x9E, 0x0B)    # 琥珀橙（点缀/项目符号）
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    BODY = RGBColor(0x33, 0x41, 0x55)      # 正文深灰蓝
    MUTED = RGBColor(0x94, 0xA3, 0xB8)     # 页脚浅灰
    FONT = "微软雅黑"
    SLIDE_W = Inches(13.333)               # 16:9
    SLIDE_H = Inches(7.5)

    def _set_run_font(run, name=FONT):
        try:
            run.font.name = name
            rPr = run._r.get_or_add_rPr()
            ea = rPr.find(qn("a:ea"))
            if ea is None:
                ea = rPr.makeelement(qn("a:ea"), {})
                rPr.append(ea)
            ea.set("typeface", name)
        except Exception:
            pass

    def _fill_bg(slide, color):
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = color

    def _add_shape(shape_type, slide, left, top, width, height, color):
        shp = slide.shapes.add_shape(shape_type, left, top, width, height)
        shp.fill.solid()
        shp.fill.fore_color.rgb = color
        shp.line.fill.background()
        try:
            shp.shadow.inherit = False
        except Exception:
            pass
        return shp

    def _rect(slide, left, top, width, height, color):
        return _add_shape(MSO_SHAPE.RECTANGLE, slide, left, top, width, height, color)

    def _add_textbox(slide, left, top, width, height, anchor=MSO_ANCHOR.TOP):
        tb = slide.shapes.add_textbox(left, top, width, height)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        return tf

    def _set_para(p, text, size, color, bold=False, align=PP_ALIGN.LEFT, space_after=Pt(6)):
        p.text = text
        p.alignment = align
        p.space_after = space_after
        for run in p.runs:
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color
            _set_run_font(run)
        return p

    def _add_bullet(tf, text, first):
        """写入一条要点，保留 **加粗** 强调（解析为加粗 run，`代码` 还原为普通文本）。"""
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        para.level = 0
        para.space_after = Pt(10)
        rm = para.add_run()
        rm.text = "▪  "
        rm.font.size = Pt(16)
        rm.font.bold = True
        rm.font.color.rgb = ACCENT
        _set_run_font(rm)
        for seg in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
            if not seg:
                continue
            if seg.startswith("**") and seg.endswith("**") and len(seg) > 4:
                content, bold = seg[2:-2], True
            elif seg.startswith("`") and seg.endswith("`") and len(seg) > 2:
                content, bold = seg[1:-1], False
            else:
                content, bold = seg, False
            rt = para.add_run()
            rt.text = content
            rt.font.size = Pt(16)
            rt.font.bold = bold
            rt.font.color.rgb = BODY
            _set_run_font(rt)
        return para

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]  # 空白版式，全自定义构图

    # ── 封面 ──
    cover = prs.slides.add_slide(blank)
    _fill_bg(cover, PRIMARY)
    # 底部琥珀色块 + 顶部细条（视觉锚点）
    _rect(cover, Inches(0), Inches(6.15), SLIDE_W, Inches(1.35), ACCENT)
    _rect(cover, Inches(0), Inches(0), SLIDE_W, Inches(0.16), ACCENT)
    # 右上角大圆装饰（同色系稍亮）
    _add_shape(MSO_SHAPE.OVAL, cover, Inches(9.5), Inches(-1.0), Inches(4.6), Inches(4.6), PRIMARY_SOFT)
    _add_shape(MSO_SHAPE.OVAL, cover, Inches(10.6), Inches(0.2), Inches(1.0), Inches(1.0), ACCENT)
    # 主标题
    tf = _add_textbox(cover, Inches(0.9), Inches(2.35), Inches(11.5), Inches(1.7), MSO_ANCHOR.MIDDLE)
    _set_para(tf.paragraphs[0], _strip_inline_md(title) or "课件", 36, WHITE, bold=True)
    # 副标题（学科 · 年级）
    sub = " · ".join(filter(None, [subject, grade]))
    if sub:
        tf2 = _add_textbox(cover, Inches(0.95), Inches(4.15), Inches(11.0), Inches(0.6))
        _set_para(tf2.paragraphs[0], sub, 16, RGBColor(0xFF, 0xE0, 0xB2))

    # ── 内容页 ──
    if not slides:
        slides = [{"title": _strip_inline_md(title) or "课件", "bullets": []}]
    total = len(slides)
    for idx, s in enumerate(slides, start=1):
        slide = prs.slides.add_slide(blank)
        _fill_bg(slide, WHITE)
        # 顶部标题条 + 琥珀分隔线
        _rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(1.0), PRIMARY)
        _rect(slide, Inches(0), Inches(1.0), SLIDE_W, Inches(0.06), ACCENT)
        tft = _add_textbox(slide, Inches(0.55), Inches(0), Inches(12.2), Inches(1.0), MSO_ANCHOR.MIDDLE)
        _set_para(tft.paragraphs[0], _strip_inline_md(s["title"]), 20, WHITE, bold=True)
        # 正文左侧装饰小色块
        _rect(slide, Inches(0.55), Inches(1.4), Inches(0.12), Inches(0.42), ACCENT)
        # 正文要点
        tfb = _add_textbox(slide, Inches(0.9), Inches(1.55), Inches(11.65), Inches(5.25), MSO_ANCHOR.TOP)
        first = True
        for raw in (s["bullets"] or [""]):
            text = (raw or "").strip()
            if not text:
                continue
            _add_bullet(tfb, text, first)
            first = False
        # 页脚 + 页码
        tff = _add_textbox(slide, Inches(0.55), Inches(7.08), Inches(9), Inches(0.4))
        foot = " · ".join(filter(None, [subject, grade]))
        if foot:
            _set_para(tff.paragraphs[0], foot, 10, MUTED)
        tfp = _add_textbox(slide, Inches(12.0), Inches(7.08), Inches(0.9), Inches(0.4))
        _set_para(tfp.paragraphs[0], f"{idx} / {total}", 10, MUTED, align=PP_ALIGN.RIGHT)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


@router.post("/generate-pptx")
def ai_generate_pptx(
    body: AiGeneratePptxRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """把已生成的课程 Markdown 大纲转换为可直接使用的 .pptx 课件并返回二进制文件。"""
    require_ai_access(db, user_id, "smart_gen")
    title = (body.title or "").strip() or "课件"
    markdown = (body.markdown or "").strip()
    if not markdown:
        raise HTTPException(status_code=400, detail="暂无课件内容，请先生成后再导出 PPT")

    if assert_no_sensitive_input("\n".join(filter(None, [title, body.subject, body.grade, markdown[:2000]]))):
        raise HTTPException(status_code=403, detail="内容包含身份证号/手机号等敏感个人信息，请移除后重试")

    slides = _parse_markdown_to_slides(markdown, title)
    pptx_bytes = _build_pptx_bytes(
        slides, title, (body.subject or "").strip(), (body.grade or "").strip()
    )

    filename = quote(f"{title}.pptx")
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
