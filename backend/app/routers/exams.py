import base64
import json
import logging
import re
import threading
import time
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.ai_policy import assert_no_sensitive_input, require_ai_access
from app.services.redline_filter import filter_dict, filter_text
from app.utils.class_access import can_view_class

from app.models.exam import Exam, SmartExamPaper

router = APIRouter(prefix="/exams", tags=["exams"])


# H4：试卷邮件发送限流（内存实现）与收件人白名单
_EMAIL_LOCK = threading.Lock()
# key = user_id -> [发送时间戳]
_EMAIL_SENT: dict[str, list[float]] = {}
_EMAIL_WINDOW_SECONDS = 24 * 3600
_EMAIL_MAX_PER_DAY = 20


def _check_email_rate_limit(user_id: str) -> None:
    now = time.time()
    with _EMAIL_LOCK:
        ts_list = [t for t in _EMAIL_SENT.get(user_id, []) if now - t < _EMAIL_WINDOW_SECONDS]
        if len(ts_list) >= _EMAIL_MAX_PER_DAY:
            raise HTTPException(status_code=429, detail="今日邮件发送次数已达上限")
        ts_list.append(now)
        _EMAIL_SENT[user_id] = ts_list


def _allowed_email_target(user: Optional[User], to_email: str) -> bool:
    """H4：只允许发送到本人个人邮箱，或与账号同域名的地址（防开放转发）。"""
    email = (to_email or "").strip()
    if not email:
        return False
    if user and (getattr(user, "personal_email", "") or "").strip().lower() == email.lower():
        return True
    account_domain = ((user.email or "").split("@", 1)[-1] or "").lower() if user else ""
    target_domain = (email.split("@", 1)[-1] or "").lower() if "@" in email else ""
    return bool(account_domain and target_domain == account_domain)


def _prepare_exam_questions_for_save(subject: str, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """保存试卷到云端时，数学/理科题目自动规范化符号。"""
    from app.utils.exam_math_format import is_math_related_subject, normalize_questions_math_notation

    qs = questions if isinstance(questions, list) else []
    if not is_math_related_subject(subject):
        return qs
    return normalize_questions_math_notation(qs)

class SaveExamPaperRequest(BaseModel):
    title: str
    subject: str
    questions: List[Dict[str, Any]]
    # 卷头可编辑字段（11.9-2）：{class,name,number,totalScore}，缺省键=前端默认文案
    header_fields: Optional[Dict[str, Any]] = None

class ExamPaperResponse(BaseModel):
    id: str
    title: str
    subject: str
    questions: List[Dict[str, Any]]
    header_fields: Optional[Dict[str, Any]] = None
    updatedAt: str

@router.get("/papers", response_model=ApiResponse[List[ExamPaperResponse]])
def get_exam_papers(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    papers = db.query(SmartExamPaper).filter(SmartExamPaper.user_id == user_id).order_by(SmartExamPaper.updated_at.desc()).all()
    data = []
    for p in papers:
        data.append({
            "id": p.id,
            "title": p.title,
            "subject": p.subject,
            "questions": p.questions if isinstance(p.questions, list) else [],
            "header_fields": p.header_fields if isinstance(p.header_fields, dict) else None,
            "updatedAt": p.updated_at.isoformat() if p.updated_at else ""
        })
    return ApiResponse(data=data)

@router.post("/papers", response_model=ApiResponse[ExamPaperResponse])
def create_exam_paper(
    body: SaveExamPaperRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    questions = _prepare_exam_questions_for_save(body.subject, body.questions)
    new_paper = SmartExamPaper(
        user_id=user_id,
        title=body.title,
        subject=body.subject,
        questions=questions,
        header_fields=body.header_fields if isinstance(body.header_fields, dict) else None,
    )
    db.add(new_paper)
    db.commit()
    db.refresh(new_paper)
    return ApiResponse(data={
        "id": new_paper.id,
        "title": new_paper.title,
        "subject": new_paper.subject,
        "questions": new_paper.questions if isinstance(new_paper.questions, list) else [],
        "header_fields": new_paper.header_fields if isinstance(new_paper.header_fields, dict) else None,
        "updatedAt": new_paper.updated_at.isoformat() if new_paper.updated_at else ""
    })

@router.patch("/papers/{paper_id}", response_model=ApiResponse[ExamPaperResponse])
def update_exam_paper(
    paper_id: str,
    body: SaveExamPaperRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    paper = db.query(SmartExamPaper).filter(SmartExamPaper.id == paper_id, SmartExamPaper.user_id == user_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在或无权修改")
    
    questions = _prepare_exam_questions_for_save(body.subject, body.questions)
    paper.title = body.title
    paper.subject = body.subject
    paper.questions = questions
    paper.header_fields = body.header_fields if isinstance(body.header_fields, dict) else None
    db.commit()
    db.refresh(paper)
    return ApiResponse(data={
        "id": paper.id,
        "title": paper.title,
        "subject": paper.subject,
        "questions": paper.questions if isinstance(paper.questions, list) else [],
        "header_fields": paper.header_fields if isinstance(paper.header_fields, dict) else None,
        "updatedAt": paper.updated_at.isoformat() if paper.updated_at else ""
    })

@router.delete("/papers/{paper_id}", response_model=ApiResponse[dict])
def delete_exam_paper(
    paper_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    paper = db.query(SmartExamPaper).filter(SmartExamPaper.id == paper_id, SmartExamPaper.user_id == user_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在或无权删除")
    
    db.delete(paper)
    db.commit()
    return ApiResponse(data={"ok": True})

class SendExamEmailRequest(BaseModel):
    pdf_base64: str
    filename: Optional[str] = None
    to_email: Optional[str] = None

@router.post("/send-email", response_model=ApiResponse[dict])
def send_exam_email(
    body: SendExamEmailRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    to_email = ""
    if body.to_email and body.to_email.strip():
        to_email = body.to_email.strip()
    else:
        to_email = (getattr(user, "personal_email", "") or "").strip() if user else ""
        
    if not to_email:
        raise HTTPException(status_code=400, detail="未指定接收邮箱，且个人设置中未配置个人邮箱")

    # H4：收件人限定本人或同域名，加限流与审计日志，防止开放邮件转发
    _check_email_rate_limit(user_id)
    if not _allowed_email_target(user, to_email):
        logging.warning("组卷邮件发送被拒绝（非本人/非同域名收件人）: user_id=%s to_email=%s", user_id, to_email)
        raise HTTPException(status_code=403, detail="仅允许发送到本人个人邮箱或本账号同域名的邮箱")

    pdf_base64 = (body.pdf_base64 or "").strip()
    if not pdf_base64:
        raise HTTPException(status_code=400, detail="缺少试卷 PDF")

    try:
        pdf_bytes = base64.b64decode(pdf_base64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="试卷 PDF 数据无效")
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="试卷 PDF 为空")

    try:
        from app.email_utils import send_email
    except Exception:
        raise HTTPException(status_code=500, detail="邮件模块不可用")

    subject = f"试卷分享：{body.filename or '未命名试卷'}"
    body_text = f"这是通过智能组卷生成的试卷：{body.filename or '未命名试卷'}\n\n请查收附件。"
    filename = (body.filename or "").strip() or "智能组卷_试卷.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"
        
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
    logging.info("组卷邮件发送成功: user_id=%s to_email=%s", user_id, to_email)

class RequirementItem(BaseModel):
    type: str
    count: int
    score: float

class AIGenerateExamRequest(BaseModel):
    topic: Optional[str] = None
    topics: Optional[List[str]] = None
    grade: str
    term: str
    difficulty: str
    subject: Optional[str] = None
    requirements: List[RequirementItem]

import requests
from app.utils.exam_math_format import (
    MATH_EXAM_FORMAT_PROMPT,
    is_math_related_subject,
    normalize_questions_math_notation,
)
from app.utils.figure_render import FIGURE_POLICY_PROMPT, process_question_figures
from app.utils.qwen_settings import get_llm_config, get_llm_thinking_extra

def _filter_redline_exam_question(q: Dict[str, Any]) -> Dict[str, Any]:
    """红线词过滤单题：题干/内容/解析等自然语言字段 + 选项/子问题等字符串列表。

    复用 redline_filter.filter_dict（递归滤白名单 key 的字符串值），
    并对 options / subQuestions 两个字符串数组逐项 filter_text。
    """
    if not isinstance(q, dict):
        return q
    q = filter_dict(q, ["stem", "content", "analysis", "explanation"])
    for key in ("options", "subQuestions"):
        items = q.get(key)
        if isinstance(items, list):
            q[key] = [filter_text(item) if isinstance(item, str) else item for item in items]
    return q


def _resolve_topics(topic: Optional[str], topics: Optional[List[str]]) -> List[str]:
    """合并多知识点：topics 列表优先，topic 兼容旧字段并按顿号/逗号/分号/换行拆分。去重、去空白。"""
    out: List[str] = []
    seen = set()
    for t in (topics or []):
        if isinstance(t, str):
            s = t.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    for seg in re.split(r"[、,，;；\n]+", (topic or "").strip()):
        s = seg.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


@router.post("/ai-generate", response_model=ApiResponse[List[Dict[str, Any]]])
def ai_generate_exam(
    body: AIGenerateExamRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    使用通义千问大模型生成题目。
    我们构建 Prompt 让模型返回严格的 JSON 格式。
    """
    # E08 · 学校级 AI 管控：智能组卷（smart_exam）开关关闭时一律 403；知识点 free-text 命中敏感输入拒答
    require_ai_access(db, user_id, "smart_exam")
    topics = _resolve_topics(body.topic, body.topics)
    for kp in topics:
        if assert_no_sensitive_input(kp):
            raise HTTPException(status_code=403, detail="输入包含身份证号/手机号等敏感个人信息，请移除后重试")
    # 构建 Prompt
    req_lines = []
    for r in body.requirements:
        req_lines.append(f"- 题型：{r.type}，数量：{r.count}题，单题分数：{r.score}分")
    req_str = "\n".join(req_lines)
    subject = (body.subject or "").strip()
    math_format_block = MATH_EXAM_FORMAT_PROMPT if is_math_related_subject(subject) else ""
    kp_text = "、".join(topics)
    coverage_note = ""
    if len(topics) > 1:
        coverage_note = (
            f"【知识点覆盖】：本次试卷需覆盖以下 {len(topics)} 个知识点，题目请大致均匀地分布到这些知识点上，"
            f"不要整张卷都集中在一个知识点：{kp_text}\n"
        )

    prompt = f"""你是一个专业的中国中小学教师。请根据以下要求生成一份试卷的题目：

【学科】：{subject or "未指定（请根据知识点推断，数学/物理/化学题必须遵守下方符号规范）"}
【知识点】：{kp_text}
【年级】：{body.grade}
【学期】：{body.term}
【难度】：{body.difficulty}
{coverage_note}
【题目要求】：
{req_str}
{math_format_block}
{FIGURE_POLICY_PROMPT}

请务必直接输出一个标准的 JSON 数组，包含所有生成的题目（不要输出 markdown 的 ```json 块，也不要输出任何前缀或后缀说明，只输出纯 JSON 数组）。
每个题目对象的字段必须包含：
- id: 随机的唯一字符串（例如 "q_12345"）
- type: 题型的英文字符串（必须是 "choice", "fill", "judge", "short_answer", "essay", "matching", "ordering", "reading", "cloze", "calculation", "application" 中的一个）
- stem: 题干或背景材料（reading 必须填阅读材料全文；其余如果没有可为空字符串）
- content: 题目具体内容或问题（cloze 填含空白的篇章，空白处用「＿＿＿」表示；calculation/application 填计算题/应用题题干）
- score: 数字（使用上方提供的分数）
- options: 字符串数组（choice 提供4个选项；matching 提供左列4项；ordering 提供需按正确顺序排列的乱序项；cloze 可选提供候选词。注意：只输出内容本身，绝对不要在内容前面加上 "A."、"B."、"C."、"D." 这样的前缀！因为前端试卷上已经自带序号标签了）
- subQuestions: 字符串数组（short_answer/reading 提供1到3个子问题；matching 提供右列与左列一一对应的4项；其余为空数组）
- figure: 可选。本题需要配图时给作图规格对象（见【配图出题】），不需要配图的题不要带此字段

示例格式：
[
  {{
    "id": "q_abc1",
    "type": "choice",
    "stem": "",
    "content": "若 a、b 互为倒数，c、d 互为相反数，且 |m|=2，则代数式 2ab-(c+d)/m+m² 的值为（ ）",
    "score": 5,
    "options": ["-3", "-1", "1", "3"]
  }},
  {{
    "id": "q_abc2",
    "type": "short_answer",
    "stem": "阅读以下短文...",
    "content": "根据短文回答：",
    "score": 10,
    "subQuestions": ["第一段的主要内容是什么？", "作者表达了什么情感？"]
  }},
  {{
    "id": "q_abc3",
    "type": "matching",
    "stem": "请将左边的成语与右边对应的意思连线。",
    "content": "",
    "score": 8,
    "options": ["画蛇添足", "亡羊补牢", "守株待兔", "掩耳盗铃"],
    "subQuestions": ["做了多余的事", "出了问题及时补救", "不劳而获", "自欺欺人"]
  }},
  {{
    "id": "q_abc4",
    "type": "short_answer",
    "stem": "",
    "content": "如图所示，抛物线 y=x²-4x+3 与 x 轴交于 A、B 两点（点 A 在点 B 左侧），求 A、B 两点的坐标及顶点坐标。",
    "score": 8,
    "figure": {{"kind": "function", "exprs": ["x^2-4*x+3"], "x_min": -1, "x_max": 5, "y_min": -2, "y_max": 10}}
  }}
]
请确保生成的题目符合指定的知识点和难度，并且数量与要求完全一致。所有文字必须是学生可直接阅读的普通中文试卷用语，不要出现 LaTeX 或 Markdown 标记。
"""

    payload = {
        "model": "qwen3.7-plus",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        # figure 规格把 JSON 撑大，4096 会截断成解析失败（1026 配图出题）
        "max_tokens": 6144,
    }

    try:
        # 直接使用 requests 调用，因为兼容 OpenAI 的格式
        base_url, api_key, qwen_model = get_llm_config(db)
        if not api_key:
            raise HTTPException(status_code=500, detail="系统设置中未配置文本大模型 API Key，无法生成试卷")

        url = f"{base_url}/chat/completions"
        payload["model"] = qwen_model
        payload["messages"] = [{"role": "user", "content": prompt}]
        payload.update(get_llm_thinking_extra(base_url))
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 增加 timeout 以防题目过多导致超时 (180秒)
        response = requests.post(url, json=payload, headers=headers, timeout=180)
        res_json = response.json()
        
        if response.status_code != 200 or "error" in res_json:
            error_msg = res_json.get("error", {}).get("message", str(res_json))
            raise HTTPException(status_code=500, detail=f"AI生成错误: {error_msg}")
        
        result_str = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        
        # 尝试清理 markdown 代码块标记
        if result_str.startswith("```json"):
            result_str = result_str[7:]
        elif result_str.startswith("```"):
            result_str = result_str[3:]
        if result_str.endswith("```"):
            result_str = result_str[:-3]
        result_str = result_str.strip()

        questions = json.loads(result_str)
        if not isinstance(questions, list):
            raise ValueError("AI 返回的不是 JSON 数组")

        if is_math_related_subject(subject):
            questions = normalize_questions_math_notation(questions)

        # AI 输出红线词过滤：题目标题/内容/解析等自然语言字段（best-effort，异常不阻断组卷主流程）
        try:
            questions = [_filter_redline_exam_question(q) if isinstance(q, dict) else q for q in questions]
        except Exception:  # noqa: BLE001 - best-effort，过滤器异常不阻断主流程
            pass

        # 配图收尾（1026「如图所示」没图）：要图的题画真图挂 figure_img；
        # 画不出/引用图没图的整题丢弃（要么带图，要么出没有图的题）
        questions = process_question_figures(questions)

        # E05 · AI 内容统一标识（GB 45438 隐式标识）：AI 组卷响应每题外露 is_ai=true（前端消费零改动）
        for q in questions:
            if isinstance(q, dict):
                q["is_ai"] = True

        return ApiResponse(data=questions)
    except Exception as e:
        print(f"AI Generate Error: {e}")
        print(f"Raw Response: {res_json.get('result', '') if 'res_json' in locals() else 'None'}")
        raise HTTPException(status_code=500, detail="AI 解析失败，请重试或修改提示词")


# ---- 考试记录（exams 表）CRUD ----
# 成绩管理页前端 useExams 由直连 Supabase 迁移到本组接口；演示数据在 MySQL，
# 必须经 can_view_class 校验班级访问权限，防止越权读写。

class CreateExamRequest(BaseModel):
    class_id: str
    subject: str
    title: str
    total_score: int = 100
    exam_date: date


def _assert_class_access(db: Session, user_id: str, class_id: str) -> None:
    """校验调用者对目标班级有访问权限（教师=所带班级，班主任/副班主任=本班，系统管理员/校级管理者/年级组长=全校），否则 403。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")


def _exam_to_record(e: Exam) -> dict:
    """Exam ORM → 前端 ExamRecord 对齐字段。"""
    return {
        "id": e.id,
        "user_id": e.user_id,
        "class_id": e.class_id,
        "subject": e.subject,
        "title": e.title,
        "total_score": e.total_score,
        "exam_date": e.exam_date.isoformat() if e.exam_date else "",
        "created_at": e.created_at.isoformat() if e.created_at else "",
        "updated_at": e.updated_at.isoformat() if e.updated_at else "",
    }


@router.get("", response_model=ApiResponse[List[dict]])
def list_exams(
    class_id: str = Query(...),
    subject: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    q = db.query(Exam).filter(Exam.class_id == class_id)
    if subject:
        q = q.filter(Exam.subject == subject)
    rows = q.order_by(Exam.exam_date.desc()).all()
    return ApiResponse(data=[_exam_to_record(e) for e in rows])


@router.post("", response_model=ApiResponse[dict])
def create_exam(
    body: CreateExamRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, body.class_id)
    exam = Exam(
        user_id=user_id,
        class_id=body.class_id,
        subject=(body.subject or "").strip(),
        title=(body.title or "").strip(),
        total_score=body.total_score,
        exam_date=body.exam_date,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return ApiResponse(data=_exam_to_record(exam))


@router.delete("/{exam_id}", response_model=ApiResponse[dict])
def delete_exam(
    exam_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    # 本人创建，或对该班级有查看权限，均可删除
    if exam.user_id != user_id and not can_view_class(db, user_id, exam.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无权限删除该考试记录")
    db.delete(exam)
    db.commit()
    return ApiResponse(data={"ok": True})
