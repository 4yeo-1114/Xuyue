"""题型模板 CRUD：组卷默认题型，演示数据在 MySQL（前端 useExamTemplates 由直连 Supabase 迁移到本组接口）"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.exam_question_template import ExamQuestionTemplate
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/exam-templates", tags=["exam-templates"])


class CreateTemplateRequest(BaseModel):
    subject: str
    type_name: str
    default_count: int = 1
    default_score_each: int = 0
    sort_order: int = 0


class UpdateTemplateRequest(BaseModel):
    type_name: Optional[str] = None
    default_count: Optional[int] = None
    default_score_each: Optional[int] = None


class ReorderTemplatesRequest(BaseModel):
    ordered_ids: List[str]


class SeedTemplateRow(BaseModel):
    type_name: str
    default_count: int = 1
    default_score_each: int = 0
    sort_order: int = 0


class SeedTemplatesRequest(BaseModel):
    subject: str
    rows: List[SeedTemplateRow]


def _template_to_record(t: ExamQuestionTemplate) -> dict:
    """ExamQuestionTemplate ORM → 前端 ExamTemplate 对齐字段。"""
    return {
        "id": t.id,
        "subject": t.subject,
        "type_name": t.type_name,
        "default_count": t.default_count,
        "default_score_each": t.default_score_each,
        "sort_order": t.sort_order,
    }


@router.get("", response_model=ApiResponse[List[dict]])
def list_exam_templates(
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ExamQuestionTemplate)
        .filter(
            ExamQuestionTemplate.user_id == user_id,
            ExamQuestionTemplate.subject == subject,
        )
        .order_by(ExamQuestionTemplate.sort_order.asc())
        .all()
    )
    return ApiResponse(data=[_template_to_record(t) for t in rows])


@router.post("", response_model=ApiResponse[dict])
def create_exam_template(
    body: CreateTemplateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = ExamQuestionTemplate(
        user_id=user_id,
        subject=(body.subject or "").strip(),
        type_name=(body.type_name or "").strip(),
        default_count=body.default_count,
        default_score_each=body.default_score_each,
        sort_order=body.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_template_to_record(row))


@router.patch("/reorder", response_model=ApiResponse[dict])
def reorder_exam_templates(
    body: ReorderTemplatesRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    for index, tid in enumerate(body.ordered_ids):
        row = (
            db.query(ExamQuestionTemplate)
            .filter(
                ExamQuestionTemplate.id == tid,
                ExamQuestionTemplate.user_id == user_id,
            )
            .first()
        )
        if row:
            row.sort_order = index
    db.commit()
    return ApiResponse(data={"ok": True})


@router.post("/seed", response_model=ApiResponse[dict])
def seed_exam_templates(
    body: SeedTemplatesRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    subject = (body.subject or "").strip()
    rows = [
        ExamQuestionTemplate(
            user_id=user_id,
            subject=subject,
            type_name=(r.type_name or "").strip(),
            default_count=r.default_count,
            default_score_each=r.default_score_each,
            sort_order=r.sort_order,
        )
        for r in body.rows
    ]
    db.add_all(rows)
    db.commit()
    return ApiResponse(data={"ok": True, "inserted": len(rows)})


@router.patch("/{template_id}", response_model=ApiResponse[dict])
def update_exam_template(
    template_id: str,
    body: UpdateTemplateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ExamQuestionTemplate)
        .filter(
            ExamQuestionTemplate.id == template_id,
            ExamQuestionTemplate.user_id == user_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="题型模板不存在")
    if body.type_name is not None:
        row.type_name = (body.type_name or "").strip()
    if body.default_count is not None:
        row.default_count = body.default_count
    if body.default_score_each is not None:
        row.default_score_each = body.default_score_each
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_template_to_record(row))


@router.delete("/{template_id}", response_model=ApiResponse[dict])
def delete_exam_template(
    template_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ExamQuestionTemplate)
        .filter(
            ExamQuestionTemplate.id == template_id,
            ExamQuestionTemplate.user_id == user_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="题型模板不存在")
    db.delete(row)
    db.commit()
    return ApiResponse(data={"ok": True})
