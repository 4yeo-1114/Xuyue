"""错题本（wrong_questions 表）CRUD 路由

前端原通过 Supabase publishable key 直连远端 Supabase 的 wrong_questions 表
（读 `*, students(name, student_number)`、insert、delete），绕过 can_view_class
班级访问控制（安全 P1）。本路由改为统一走后端班级鉴权，前端 useWrongQuestions
直连迁移到本组接口。created_at / updated_at 由 model server_default 处理，前端不传。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.student import Student
from app.models.class_model import Class
from app.models.wrong_question import WrongQuestion
from app.schemas.common import ApiResponse
from app.utils.class_access import can_view_class

router = APIRouter(prefix="/wrong-questions", tags=["wrong_questions"])


def _assert_class_access(db: Session, user_id: str, class_id: str) -> None:
    """校验调用者对目标班级有访问权限（教师=所带班级，班主任/副班主任=本班，系统管理员/校级管理者/年级组长=全校），否则 403。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")


def _wq_to_dict(wq: WrongQuestion, student_name: str = "", student_number: str = "") -> dict:
    """WrongQuestion ORM → 前端记录（对齐前端直连 Supabase 时的 `*, students(name, student_number)` 形状）。"""
    return {
        "id": wq.id,
        "user_id": wq.user_id,
        "student_id": wq.student_id,
        "class_id": wq.class_id,
        "subject": wq.subject,
        "question_content": wq.question_content,
        "correct_answer": wq.correct_answer,
        "student_answer": wq.student_answer,
        "error_type": wq.error_type,
        "analysis": wq.analysis,
        "exam_id": wq.exam_id,
        "created_at": wq.created_at.isoformat() if wq.created_at else "",
        "updated_at": wq.updated_at.isoformat() if wq.updated_at else "",
        "student_name": student_name,
        "student_number": student_number,
    }


class CreateWrongQuestionRequest(BaseModel):
    student_id: str
    class_id: str
    subject: str
    question_content: str
    correct_answer: Optional[str] = None
    student_answer: Optional[str] = None
    error_type: str = "other"
    analysis: Optional[str] = None
    exam_id: Optional[str] = None


@router.get("", response_model=ApiResponse[list])
def list_wrong_questions(
    class_id: str = Query(...),
    subject: Optional[str] = Query(None),
    student_id: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    q = (
        db.query(WrongQuestion, Student.name, Student.student_number)
        .outerjoin(Student, Student.id == WrongQuestion.student_id)
        .filter(WrongQuestion.class_id == class_id)
    )
    if subject:
        q = q.filter(WrongQuestion.subject == subject)
    if student_id:
        q = q.filter(WrongQuestion.student_id == student_id)
    rows = q.order_by(WrongQuestion.created_at.desc(), WrongQuestion.id.desc()).all()
    return ApiResponse(data=[
        _wq_to_dict(wq, name or "", number or "")
        for wq, name, number in rows
    ])


@router.post("", response_model=ApiResponse[dict])
def create_wrong_question(
    body: CreateWrongQuestionRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, body.class_id)
    student = db.query(Student).filter(Student.id == body.student_id).first()
    if not student:
        raise HTTPException(status_code=400, detail="学生不存在")
    if student.class_id != body.class_id:
        raise HTTPException(status_code=400, detail="学生不属于该班级")
    # R2 多校归属：school_id 优先取学生（回填后已有），兜底查班级
    school_id = getattr(student, "school_id", None)
    if not school_id:
        class_row = db.query(Class).filter(Class.id == body.class_id).first()
        school_id = class_row.school_id if class_row else None
    wq = WrongQuestion(
        user_id=user_id,
        student_id=body.student_id,
        class_id=body.class_id,
        school_id=school_id,
        subject=(body.subject or "").strip(),
        question_content=body.question_content,
        correct_answer=body.correct_answer,
        student_answer=body.student_answer,
        error_type=(body.error_type or "other").strip() or "other",
        analysis=body.analysis,
        exam_id=body.exam_id,
    )
    db.add(wq)
    db.commit()
    db.refresh(wq)
    return ApiResponse(data=_wq_to_dict(wq, student.name, student.student_number))


@router.delete("/{wq_id}", response_model=ApiResponse[dict])
def delete_wrong_question(
    wq_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    wq = db.query(WrongQuestion).filter(WrongQuestion.id == wq_id).first()
    if not wq:
        raise HTTPException(status_code=404, detail="错题记录不存在")
    # 本人创建或对该班级有查看权限均可删除（对齐 exams.py delete_exam 语义）
    if wq.user_id != user_id and not can_view_class(db, user_id, wq.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")
    db.delete(wq)
    db.commit()
    return ApiResponse(data={"ok": True})
