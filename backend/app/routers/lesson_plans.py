import base64
import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.class_model import Class
from app.models.lesson_plan import LessonPlan
from app.models.system_settings import SystemSettings
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.lesson_plans import (
    AiGenerateFullRequest,
    AiGenerateOutlineRequest,
    AiGenerateOutlineResult,
    AiGenerateOutlineStep,
    CreateLessonPlanRequest,
    LessonPlanRecord,
    SendLessonPlanEmailRequest,
    UpdateLessonPlanRequest,
)
from app.services.ai_policy import assert_no_sensitive_input, require_ai_access
from app.utils.class_access import can_view_class
from app.utils.qwen_settings import get_llm_config, get_llm_thinking_extra

router = APIRouter(prefix="/lesson-plans", tags=["lesson-plans"])


def _as_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_utc_z(dt: Optional[datetime]) -> Optional[str]:
    d = _as_utc_aware(dt)
    if not d:
        return None
    s = d.isoformat(timespec="seconds")
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    return s


def _clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _to_record(row: LessonPlan) -> LessonPlanRecord:
    return LessonPlanRecord(
        id=row.id,
        user_id=row.user_id,
        class_id=row.class_id,
        school_year=row.school_year or "",
        term=row.term or "",
        grade=row.grade or "",
        subject=row.subject or "",
        title=row.title or "",
        teaching_content=row.teaching_content or "",
        teaching_objectives=row.teaching_objectives or "",
        key_points=row.key_points or "",
        difficult_points=row.difficult_points or "",
        teaching_preparation=row.teaching_preparation or "",
        teaching_process=row.teaching_process or "",
        collective_preparation_advice=row.collective_preparation_advice or "",
        blackboard_design=row.blackboard_design or "",
        teaching_reflection=row.teaching_reflection or "",
        main_author=row.main_author or "",
        deputy_author=row.deputy_author or "",
        lesson_sequence=row.lesson_sequence or "",
        textbook_id=row.textbook_id,
        unit_id=row.unit_id,
        catalog_id=row.catalog_id,
        edition=row.edition,
        chapter=row.chapter,
        completed_at=_iso_utc_z(row.completed_at),
        created_at=_iso_utc_z(row.created_at) or "",
        updated_at=_iso_utc_z(row.updated_at) or "",
    )


def _get_user_display_name(db: Session, user_id: str) -> str:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return (getattr(user, "display_name", None) or getattr(user, "email", None) or user_id).strip()


def _get_class_or_404(db: Session, class_id: str) -> Class:
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="班级不存在")
    return c


# ── AI 备课（分步确认式生成，见 LessonPlanPage.tsx）────────

def _call_qwen(db: Session, prompt: str, *, max_tokens: int = 4096) -> str:
    """调用文本大模型，返回模型原始文本（已去除首尾空白）。"""
    base_url, api_key, qwen_model = get_llm_config(db)
    if not api_key:
        raise HTTPException(status_code=500, detail="系统设置中未配置文本大模型 API Key，无法生成教案")
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
    """从模型输出中提取首个 JSON 对象（容忍 markdown 代码块与前后缀说明）。"""
    s = (text or "").strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("AI 返回内容不是 JSON 对象")
    # 用 raw_decode 从首个 { 开始解析，自动忽略 JSON 之后可能追加的说明文字
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(s[start:])
    except json.JSONDecodeError:
        raise ValueError("AI 返回内容不是 JSON 对象")
    if not isinstance(obj, dict):
        raise ValueError("AI 返回内容不是 JSON 对象")
    return obj


def _ai_sensitive_text(*parts: Optional[str]) -> str:
    return "\n".join(filter(None, (_clean_text(p) for p in parts)))


_SCIENCE_SUBJECTS = {"数学", "物理", "化学", "生物", "科学"}


@router.post("/ai-generate/outline", response_model=ApiResponse[AiGenerateOutlineResult])
def ai_generate_outline(
    body: AiGenerateOutlineRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """AI 备课第一步：生成教学大纲（不落库，供老师确认后进入第二步）。"""
    require_ai_access(db, user_id, "smart_gen")
    subject = _clean_text(body.subject)
    lesson_title = _clean_text(body.lesson_title)
    if not subject:
        raise HTTPException(status_code=400, detail="学科不能为空")
    if not lesson_title:
        raise HTTPException(status_code=400, detail="课题不能为空")
    if assert_no_sensitive_input(_ai_sensitive_text(
        subject, body.grade, body.edition, body.unit_name, lesson_title, body.lesson_sequence,
    )):
        raise HTTPException(status_code=403, detail="输入包含身份证号/手机号等敏感个人信息，请移除后重试")

    science_note = ""
    if subject in _SCIENCE_SUBJECTS:
        science_note = (
            "【特别要求】本学科为理科，教学过程概要（process_summary）中必须包含「随堂练习」阶段，"
            "给出 2-3 道与本课知识点紧密相关的随堂练习题及简要参考答案或解题思路。"
        )

    prompt = f"""你是一名资深的中国中小学教师。请根据以下信息，为该课时撰写一份教学大纲。

【学科】：{subject}
【年级】：{body.grade or "未指定"}
【教材版本】：{body.edition or "未指定"}
【单元】：{body.unit_name or "未指定"}
【课题】：{lesson_title}
【课时序号】：{body.lesson_sequence or "未指定"}
{science_note}

请务必直接输出一个标准 JSON 对象（不要输出 markdown 的 ```json 块，也不要任何前缀或后缀说明，只输出纯 JSON），字段如下：
- title: 课题名称（字符串）
- objectives: 教学目标（必须是字符串，多个要点用换行符 \n 连成一个字符串，绝不要用数组）
- key_points: 教学重点（必须是字符串）
- difficult_points: 教学难点（必须是字符串）
- process_summary: 教学过程概要（数组，每项为对象，含 step 阶段名称 与 point 该阶段要点）

示例格式：
{{
  "title": "……",
  "objectives": "……",
  "key_points": "……",
  "difficult_points": "……",
  "process_summary": [
    {{"step": "导入", "point": "……"}},
    {{"step": "新授", "point": "……"}},
    {{"step": "练习", "point": "……"}},
    {{"step": "小结", "point": "……"}}
  ]
}}

要求内容贴合学科与学段实际、符合新课标导向，语言为可直接使用的普通中文教学用语，不要出现 Markdown 标记或 LaTeX。"""

    content = _call_qwen(db, prompt, max_tokens=4096)
    try:
        obj = _extract_json_object(content)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=502, detail="AI 返回内容格式异常，请重试")

    def _as_str(v) -> str:
        # 兼容千问(字符串)与 DeepSeek(可能返回数组)：数组用换行拼成一个字符串
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, list):
            return "\n".join(str(x).strip() for x in v if str(x).strip())
        return ""

    process_raw = obj.get("process_summary")
    process_summary: Optional[List[AiGenerateOutlineStep]] = None
    if isinstance(process_raw, list):
        steps = [
            AiGenerateOutlineStep(step=_as_str(i.get("step")), point=_as_str(i.get("point")))
            for i in process_raw
            if isinstance(i, dict)
        ]
        process_summary = steps or None

    result = AiGenerateOutlineResult(
        title=_as_str(obj.get("title")) or lesson_title,
        objectives=_as_str(obj.get("objectives")),
        key_points=_as_str(obj.get("key_points")),
        difficult_points=_as_str(obj.get("difficult_points")),
        process_summary=process_summary,
    )
    return ApiResponse(data=result)


@router.post("/ai-generate/full", response_model=ApiResponse[LessonPlanRecord])
def ai_generate_full(
    body: AiGenerateFullRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """AI 备课第二步：按确认大纲生成完整教案并落库，返回教案记录。"""
    require_ai_access(db, user_id, "smart_gen")
    subject = _clean_text(body.subject)
    lesson_title = _clean_text(body.lesson_title)
    if not subject:
        raise HTTPException(status_code=400, detail="学科不能为空")
    if not lesson_title:
        raise HTTPException(status_code=400, detail="课题不能为空")
    if not can_view_class(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="无权限创建该班级教案")
    c = _get_class_or_404(db, body.class_id)

    outline = _clean_text(body.outline)
    if assert_no_sensitive_input(_ai_sensitive_text(
        subject, body.grade, body.edition, body.unit_name, lesson_title, body.lesson_sequence, outline,
    )):
        raise HTTPException(status_code=403, detail="输入包含身份证号/手机号等敏感个人信息，请移除后重试")

    science_note = ""
    if subject in _SCIENCE_SUBJECTS:
        science_note = (
            "【特别要求】本学科为理科，教学过程（teaching_process）中必须包含「随堂练习」环节，"
            "给出 2-3 道与本课知识点紧密相关的随堂练习题及简要参考答案或解题思路。"
        )

    prompt = f"""你是一名资深的中国中小学教师。请根据以下课时信息与已确认的教学大纲，撰写一份结构完整的教案。

【学科】：{subject}
【年级】：{body.grade or "未指定"}
【教材版本】：{body.edition or "未指定"}
【单元】：{body.unit_name or "未指定"}
【课题】：{lesson_title}
【课时序号】：{body.lesson_sequence or "未指定"}
{science_note}

【已确认教学大纲】：
{outline or "（无）"}

请务必直接输出一个标准 JSON 对象（不要输出 markdown 的 ```json 块，也不要任何前缀或后缀说明，只输出纯 JSON），字段如下：
- title: 课题名称（字符串）
- teaching_content: 教学内容（字符串）
- teaching_objectives: 教学目标（字符串）
- key_points: 教学重点（字符串）
- difficult_points: 教学难点（字符串）
- teaching_preparation: 教学准备（字符串）
- teaching_process: 教学过程（字符串，分环节详写）
- collective_preparation_advice: 集体备课建议（字符串）
- blackboard_design: 板书设计（字符串）
- teaching_reflection: 教学反思（字符串）

示例格式：
{{
  "title": "……",
  "teaching_content": "……",
  "teaching_objectives": "……",
  "key_points": "……",
  "difficult_points": "……",
  "teaching_preparation": "……",
  "teaching_process": "……",
  "collective_preparation_advice": "……",
  "blackboard_design": "……",
  "teaching_reflection": "……"
}}

要求内容贴合学科与学段实际、结构完整、可直接用于课堂，语言为普通中文教学用语，不要出现 Markdown 标记或 LaTeX。"""

    content = _call_qwen(db, prompt, max_tokens=8192)
    try:
        obj = _extract_json_object(content)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=502, detail="AI 返回内容格式异常，请重试")

    def _as_str(v) -> str:
        # 兼容千问(字符串)与 DeepSeek(可能返回数组)：数组用换行拼成一个字符串
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, list):
            return "\n".join(str(x).strip() for x in v if str(x).strip())
        return ""

    row = LessonPlan(
        user_id=user_id,
        class_id=body.class_id,
        school_year="",
        term="",
        grade=_clean_text(body.grade) or c.grade,
        subject=subject,
        title=_as_str(obj.get("title")) or lesson_title,
        teaching_content=_as_str(obj.get("teaching_content")),
        teaching_objectives=_as_str(obj.get("teaching_objectives")),
        key_points=_as_str(obj.get("key_points")),
        difficult_points=_as_str(obj.get("difficult_points")),
        teaching_preparation=_as_str(obj.get("teaching_preparation")),
        teaching_process=_as_str(obj.get("teaching_process")),
        collective_preparation_advice=_as_str(obj.get("collective_preparation_advice")),
        blackboard_design=_as_str(obj.get("blackboard_design")),
        teaching_reflection=_as_str(obj.get("teaching_reflection")),
        main_author=_get_user_display_name(db, user_id),
        deputy_author="",
        lesson_sequence=_clean_text(body.lesson_sequence),
        textbook_id=None,
        unit_id=None,
        catalog_id=None,
        edition=_clean_text(body.edition) or None,
        chapter=None,
        completed_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_to_record(row))


# P1：教案邮件发送短窗限流（60 秒内每用户最多 5 次，防开放邮件转发滥用，内存实现、无新依赖）
_EMAIL_BURST_LOCK = threading.Lock()
# key = user_id -> [发送时间戳]
_EMAIL_BURST: dict[str, list[float]] = {}
_EMAIL_BURST_WINDOW_SECONDS = 60
_EMAIL_BURST_MAX = 5


def _check_email_burst_limit(user_id: str) -> None:
    """P1：对 send-email 端点按当前用户短窗限流，超限抛 429。"""
    now = time.time()
    with _EMAIL_BURST_LOCK:
        ts_list = [t for t in _EMAIL_BURST.get(user_id, []) if now - t < _EMAIL_BURST_WINDOW_SECONDS]
        if len(ts_list) >= _EMAIL_BURST_MAX:
            raise HTTPException(status_code=429, detail="发送过于频繁，请稍后再试")
        ts_list.append(now)
        _EMAIL_BURST[user_id] = ts_list


def _allowed_email_target(db: Session, user: Optional[User], to_email: str) -> bool:
    """P1：发送目标白名单——仅允许发送到系统内已注册用户的邮箱（账号邮箱或个人邮箱），
    或与账号同域名的站内邮箱（学校自有域名），白名单外一律拒绝，防止开放邮件转发。"""
    email = (to_email or "").strip()
    if not email or "@" not in email:
        return False
    normalized = email.lower()
    if user is None:
        return False
    # 1) 账号自身邮箱或已配置的个人邮箱（站内已验证）
    if (user.email or "").strip().lower() == normalized:
        return True
    if (getattr(user, "personal_email", "") or "").strip().lower() == normalized:
        return True
    # 2) 与账号同域名（学校自有域名）的邮箱
    account_domain = (user.email or "").split("@", 1)[-1].lower() if user.email else ""
    target_domain = email.split("@", 1)[-1].lower()
    if account_domain and target_domain and target_domain == account_domain:
        return True
    # 3) 系统内任一已注册用户的邮箱（账号邮箱或个人邮箱）
    registered = db.query(User.id).filter(
        (func.lower(User.email) == normalized)
        | (func.lower(User.personal_email) == normalized)
    ).first()
    return registered is not None


@router.get("", response_model=ApiResponse[List[LessonPlanRecord]])
def list_lesson_plans(
    class_id: str = Query(..., description="班级 ID"),
    subject: Optional[str] = Query(None, description="学科"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    query = db.query(LessonPlan).filter(LessonPlan.user_id == user_id, LessonPlan.class_id == class_id)
    if subject is not None:
        query = query.filter(LessonPlan.subject == _clean_text(subject))
    rows = query.order_by(desc(LessonPlan.updated_at), desc(LessonPlan.created_at)).all()
    return ApiResponse(data=[_to_record(row) for row in rows])


@router.post("", response_model=ApiResponse[LessonPlanRecord])
def create_lesson_plan(
    body: CreateLessonPlanRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_view_class(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="无权限创建该班级教案")
    c = _get_class_or_404(db, body.class_id)
    main_author = _clean_text(body.main_author) or _get_user_display_name(db, user_id)
    subject = _clean_text(body.subject)
    if not subject:
        raise HTTPException(status_code=400, detail="学科不能为空")
    row = LessonPlan(
        user_id=user_id,
        class_id=body.class_id,
        school_year=_clean_text(body.school_year),
        term=_clean_text(body.term),
        grade=_clean_text(body.grade) or c.grade,
        subject=subject,
        title=_clean_text(body.title),
        teaching_content=_clean_text(body.teaching_content),
        teaching_objectives=_clean_text(body.teaching_objectives),
        key_points=_clean_text(body.key_points),
        difficult_points=_clean_text(body.difficult_points),
        teaching_preparation=_clean_text(body.teaching_preparation),
        teaching_process=_clean_text(body.teaching_process),
        collective_preparation_advice=_clean_text(body.collective_preparation_advice),
        blackboard_design=_clean_text(body.blackboard_design),
        teaching_reflection=_clean_text(body.teaching_reflection),
        main_author=main_author,
        deputy_author=_clean_text(body.deputy_author),
        lesson_sequence=_clean_text(body.lesson_sequence),
        textbook_id=_clean_text(body.textbook_id) or None,
        unit_id=_clean_text(body.unit_id) or None,
        catalog_id=_clean_text(body.catalog_id) or None,
        edition=_clean_text(body.edition) or None,
        chapter=_clean_text(body.chapter) or None,
        completed_at=body.completed_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_to_record(row))


@router.patch("/{lesson_plan_id}", response_model=ApiResponse[LessonPlanRecord])
def update_lesson_plan(
    lesson_plan_id: str,
    body: UpdateLessonPlanRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = db.query(LessonPlan).filter(LessonPlan.id == lesson_plan_id, LessonPlan.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="教案不存在")
    if not can_view_class(db, user_id, row.class_id):
        raise HTTPException(status_code=403, detail="无权限编辑该班级教案")

    if body.school_year is not None:
        row.school_year = _clean_text(body.school_year)
    if body.term is not None:
        row.term = _clean_text(body.term)
    if body.grade is not None:
        row.grade = _clean_text(body.grade)
    if body.subject is not None:
        subject = _clean_text(body.subject)
        if not subject:
            raise HTTPException(status_code=400, detail="学科不能为空")
        row.subject = subject
    if body.title is not None:
        row.title = _clean_text(body.title)
    if body.teaching_content is not None:
        row.teaching_content = _clean_text(body.teaching_content)
    if body.teaching_objectives is not None:
        row.teaching_objectives = _clean_text(body.teaching_objectives)
    if body.key_points is not None:
        row.key_points = _clean_text(body.key_points)
    if body.difficult_points is not None:
        row.difficult_points = _clean_text(body.difficult_points)
    if body.teaching_preparation is not None:
        row.teaching_preparation = _clean_text(body.teaching_preparation)
    if body.teaching_process is not None:
        row.teaching_process = _clean_text(body.teaching_process)
    if body.collective_preparation_advice is not None:
        row.collective_preparation_advice = _clean_text(body.collective_preparation_advice)
    if body.blackboard_design is not None:
        row.blackboard_design = _clean_text(body.blackboard_design)
    if body.teaching_reflection is not None:
        row.teaching_reflection = _clean_text(body.teaching_reflection)
    if body.main_author is not None:
        row.main_author = _clean_text(body.main_author) or _get_user_display_name(db, user_id)
    if body.deputy_author is not None:
        row.deputy_author = _clean_text(body.deputy_author)
    if body.lesson_sequence is not None:
        row.lesson_sequence = _clean_text(body.lesson_sequence)
    if body.textbook_id is not None:
        row.textbook_id = _clean_text(body.textbook_id) or None
    if body.unit_id is not None:
        row.unit_id = _clean_text(body.unit_id) or None
    if body.catalog_id is not None:
        row.catalog_id = _clean_text(body.catalog_id) or None
    if body.edition is not None:
        row.edition = _clean_text(body.edition) or None
    if body.chapter is not None:
        row.chapter = _clean_text(body.chapter) or None
    if body.completed_at is not None:
        row.completed_at = body.completed_at

    db.commit()
    db.refresh(row)
    return ApiResponse(data=_to_record(row))


@router.delete("/{lesson_plan_id}", response_model=ApiResponse[None])
def delete_lesson_plan(
    lesson_plan_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = db.query(LessonPlan).filter(LessonPlan.id == lesson_plan_id, LessonPlan.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="教案不存在")
    db.delete(row)
    db.commit()
    return ApiResponse(data=None)


@router.post("/{lesson_plan_id}/send-email", response_model=ApiResponse[dict])
def send_lesson_plan_email(
    lesson_plan_id: str,
    body: SendLessonPlanEmailRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = db.query(LessonPlan).filter(LessonPlan.id == lesson_plan_id, LessonPlan.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="教案不存在")

    # P1：短窗限流，防止开放邮件转发滥用（60 秒内每用户最多 5 次）
    _check_email_burst_limit(user_id)

    user = db.query(User).filter(User.id == user_id).first()
    to_email = ""
    if body.to_email and body.to_email.strip():
        to_email = body.to_email.strip()
    else:
        to_email = (getattr(user, "personal_email", "") or "").strip() if user else ""

    if not to_email:
        raise HTTPException(status_code=400, detail="未指定接收邮箱，且个人设置中未配置个人邮箱")

    # P1：发送目标白名单——仅允许站内已验证邮箱（学校域名）或系统内注册用户邮箱
    if not _allowed_email_target(db, user, to_email):
        raise HTTPException(status_code=403, detail="仅允许发送到本校已验证邮箱或系统内注册用户邮箱")

    pdf_base64 = (body.pdf_base64 or "").strip()
    if not pdf_base64:
        raise HTTPException(status_code=400, detail="缺少教案 PDF")

    try:
        pdf_bytes = base64.b64decode(pdf_base64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="教案 PDF 数据无效")
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="教案 PDF 为空")

    try:
        from app.email_utils import send_email
    except Exception:
        raise HTTPException(status_code=500, detail="邮件模块不可用")

    class_label = _get_class_or_404(db, row.class_id).name
    subject = f"教案发送：{row.title or '未命名教案'}"
    body_text = (
        f"教案名称：{row.title or '未命名教案'}\n"
        f"年级：{row.grade or '—'}\n"
        f"学科：{row.subject or '—'}\n"
        f"班级：{class_label or '—'}\n"
        f"主备者：{row.main_author or _get_user_display_name(db, user_id)}\n"
        f"发送时间：{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    filename = (body.filename or "").strip() or f"{(row.title or '教案').replace('/', '_')}.pdf"
    try:
        send_email(
            to_email,
            subject,
            body_text,
            attachments=[
                {
                    "filename": filename,
                    "content": pdf_bytes,
                    "maintype": "application",
                    "subtype": "pdf",
                }
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {str(e)}")

    return ApiResponse(data={"ok": True, "to_email": to_email})
