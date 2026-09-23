# -*- coding: utf-8 -*-
"""流水阅卷 / 集体阅卷 —— 管理端（运维）接口。

权限：校级视野（系统管理员/子系统管理员/校级管理者/年级组长），
复用 _check_admin_permission（routers/admin.py:60）+ is_school_admin（utils/school_access.py:42）。
"""
import random
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.grading.flow_pipeline import cut_status, start_cut, sync_standard_answers
from app.grading.router import _safe_folder_name
from app.grading.user_paths import correct_docs_dir
from app.models.class_teacher import ClassTeacher
from app.models.flow_grading import FlowArbitration, FlowAssignment, FlowBatch, FlowItem, FlowQuestion, FlowReview
from app.models.user import User
from app.routers.admin import _check_admin_permission
from app.utils.security import build_download_url

router = APIRouter(prefix="/admin/flow", tags=["admin-flow"])


class FlowBatchCreateRequest(BaseModel):
    name: str
    subject: str
    grade: Optional[str] = None
    class_ids: List[str] = []
    source_folder_safe: Optional[str] = None
    review_mode: str = "single"
    resolver: str = "roster"
    auto_objective: bool = False


class FlowAssignRequest(BaseModel):
    mode: str = "specified"  # specified | random
    max_teachers: int = 10
    assignments: List[dict] = []  # [{question_no, assignee_ids:[...]}]


def _iso(dt) -> Optional[str]:
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


@router.post("/batches")
def api_create_batch(
    body: FlowBatchCreateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    admin = _check_admin_permission(db, user_id)
    name = (body.name or "").strip()
    subject = (body.subject or "").strip()
    if not name or not subject:
        raise HTTPException(status_code=400, detail="批次名与科目均不能为空")
    if body.review_mode not in ("single", "double"):
        raise HTTPException(status_code=400, detail="review_mode 仅支持 single/double")
    if body.resolver not in ("roster", "barcode"):
        raise HTTPException(status_code=400, detail="resolver 仅支持 roster/barcode")

    source = _safe_folder_name(body.source_folder_safe or "")
    if body.source_folder_safe and not source:
        raise HTTPException(status_code=400, detail="源文件夹名无效")
    if source:
        src_dir = correct_docs_dir() / source
        if not src_dir.is_dir():
            raise HTTPException(status_code=400, detail="源文件夹不存在（需先建文件夹并完成切题）")

    batch = FlowBatch(
        name=name,
        subject=subject,
        grade=(body.grade or "").strip() or None,
        owner_user_id=str(admin.id),
        source_folder_safe=source or None,
        class_ids_json=body.class_ids or [],
        review_mode=body.review_mode,
        resolver=body.resolver,
        auto_objective=body.auto_objective,
        status="created",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return {"ok": True, "batch_id": batch.id, "name": batch.name, "status": batch.status}


@router.get("/batches")
def api_list_batches(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin_permission(db, user_id)
    rows = db.query(FlowBatch).order_by(FlowBatch.created_at.desc()).all()
    return {
        "ok": True,
        "items": [
            {
                "id": b.id,
                "name": b.name,
                "subject": b.subject,
                "grade": b.grade,
                "status": b.status,
                "review_mode": b.review_mode,
                "total_papers": b.total_papers,
                "created_at": _iso(b.created_at),
            }
            for b in rows
        ],
    }


@router.get("/source-folders")
def api_source_folders(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """建批次「源文件夹」下拉数据：列出当前账号 correct_docs 下所有文件夹，
    并标注是否已切题（存在 .manual_layout.json）。已切题的排前面。"""
    _check_admin_permission(db, user_id)
    items: List[dict] = []
    try:
        dirs = [d for d in correct_docs_dir().iterdir() if d.is_dir()]
    except Exception:
        dirs = []
    for d in dirs:
        name = d.name
        display = name
        if name.startswith("cls_") and "__" in name:
            display = name.split("__", 1)[1] or name
        has_layout = (d / ".manual_layout.json").is_file()
        items.append(
            {"folder_name": name, "display_name": display, "has_layout": has_layout}
        )
    items.sort(key=lambda x: (not x["has_layout"], x["display_name"]))
    return {"ok": True, "folders": items}


@router.get("/batches/{batch_id}")
def api_get_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin_permission(db, user_id)
    batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    sync_standard_answers(db, batch)
    questions = (
        db.query(FlowQuestion)
        .filter(FlowQuestion.batch_id == batch_id)
        .order_by(FlowQuestion.question_no.asc())
        .all()
    )
    return {
        "ok": True,
        "batch": {
            "id": batch.id,
            "name": batch.name,
            "subject": batch.subject,
            "grade": batch.grade,
            "status": batch.status,
            "review_mode": batch.review_mode,
            "resolver": batch.resolver,
            "source_folder_safe": batch.source_folder_safe,
            "total_papers": batch.total_papers,
            "created_at": _iso(batch.created_at),
        },
        "questions": [
            {
                "id": q.id,
                "question_no": q.question_no,
                "display_label": q.display_label,
                "max_score": q.max_score,
                "review_mode": q.review_mode,
                "status": q.status,
                "total_items": q.total_items,
                "graded_items": _count_graded(db, q.id),
            }
            for q in questions
        ],
    }


def _count_graded(db: Session, question_id: str) -> int:
    try:
        return (
            db.query(FlowItem)
            .filter(FlowItem.question_id == question_id)
            .filter(FlowItem.status.in_(["graded", "arbitrated"]))
            .count()
        )
    except Exception:
        return 0


def _flow_file_url(batch_id: str, rel_path: str, user_id: str) -> str:
    if not rel_path:
        return ""
    return build_download_url(f"grading/flow/files/{batch_id}/{rel_path}", user_id)


@router.get("/batches/{batch_id}/crops")
def api_batch_crops(
    batch_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """切割预览：按题列出本批次所有裁图条目（含裁图直链），供管理员分配前核对切割是否正确。"""
    _check_admin_permission(db, user_id)
    batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    sync_standard_answers(db, batch)
    questions = (
        db.query(FlowQuestion)
        .filter(FlowQuestion.batch_id == batch_id)
        .order_by(FlowQuestion.question_no.asc())
        .all()
    )
    items = (
        db.query(FlowItem)
        .filter(FlowItem.batch_id == batch_id)
        .order_by(FlowItem.paper_name.asc(), FlowItem.id.asc())
        .all()
    )
    by_qid: dict[str, list[dict]] = {}
    for it in items:
        by_qid.setdefault(it.question_id, []).append(
            {
                "item_id": it.id,
                "student_name": it.student_name,
                "student_number": it.student_number,
                "paper_name": it.paper_name,
                "crop_url": _flow_file_url(batch_id, it.crop_path or "", user_id),
                "status": it.status,
            }
        )
    return {
        "ok": True,
        "questions": [
            {
                "id": q.id,
                "question_no": q.question_no,
                "display_label": q.display_label or f"第{q.question_no}题",
                "crop_dir": q.crop_dir,
                "items": by_qid.get(q.id, []),
            }
            for q in questions
        ],
    }


@router.post("/batches/{batch_id}/cut")
def api_cut_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin_permission(db, user_id)
    batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    if not batch.source_folder_safe:
        raise HTTPException(status_code=400, detail="批次未设置源文件夹，请先编辑批次")
    result = start_cut(batch_id)
    return {"ok": True, **result}


@router.get("/batches/{batch_id}/cut/status")
def api_cut_status(
    batch_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin_permission(db, user_id)
    batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    return {"ok": True, **cut_status(batch_id)}


def _candidate_teachers(db: Session, subject: str, max_teachers: int = 10) -> List[User]:
    """同科目候选教师：User.teaching_subject == subject，或 ClassTeacher.subject == subject。"""
    by_id: dict = {}
    for u in db.query(User).filter(User.teaching_subject == subject).all():
        by_id[str(u.id)] = u
    for ct in db.query(ClassTeacher).filter(ClassTeacher.subject == subject).all():
        if ct.user_id and str(ct.user_id) not in by_id:
            u = db.query(User).filter(User.id == ct.user_id).first()
            if u:
                by_id[str(u.id)] = u
    teachers = list(by_id.values())
    return teachers[:max(1, int(max_teachers or 10))]


@router.get("/batches/{batch_id}/teachers")
def api_list_teachers(
    batch_id: str,
    subject: Optional[str] = None,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin_permission(db, user_id)
    batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    subj = (subject or batch.subject or "").strip()
    teachers = _candidate_teachers(db, subj, 10)
    # 本地自测兜底：同科目老师不足时，把当前账号（管理员）自己加进候选，便于单账号跑通
    if not teachers:
        admin = db.query(User).filter(User.id == user_id).first()
        if admin:
            teachers = [admin]
    return {
        "ok": True,
        "items": [
            {
                "user_id": str(t.id),
                "display_name": t.display_name,
                "teaching_subject": t.teaching_subject,
            }
            for t in teachers
        ],
    }


@router.post("/batches/{batch_id}/assign")
def api_assign(
    batch_id: str,
    body: FlowAssignRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    admin = _check_admin_permission(db, user_id)
    batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    questions = (
        db.query(FlowQuestion)
        .filter(FlowQuestion.batch_id == batch_id)
        .order_by(FlowQuestion.question_no.asc())
        .all()
    )
    if not questions:
        raise HTTPException(status_code=400, detail="批次尚未切割，请先触发切割")
    if body.max_teachers > 10:
        raise HTTPException(status_code=400, detail="最多 10 名老师")
    max_teachers = max(1, min(int(body.max_teachers or 10), 10))

    # 撤销旧分配
    db.query(FlowAssignment).filter(
        FlowAssignment.batch_id == batch_id, FlowAssignment.status == "active"
    ).update({"status": "revoked"})

    def _add(q: FlowQuestion, assignee_id: str, role: str):
        assignee_id = str(assignee_id).strip()
        if not assignee_id:
            return
        # 唯一约束是 (question_id, assignee_user_id, role)，不含 status。
        # 因此「重新分配」时不能盲目新插一行，否则会撞 uq_flow_assignment_question_user_role。
        # 若同 (题,老师,角色) 已有一行（可能是上一步刚被撤销的旧行），复用之并重新激活即可。
        existing = (
            db.query(FlowAssignment)
            .filter(
                FlowAssignment.question_id == q.id,
                FlowAssignment.assignee_user_id == assignee_id,
                FlowAssignment.role == role,
            )
            .first()
        )
        if existing:
            existing.status = "active"
            existing.assigned_by = str(admin.id)
            existing.assigned_at = datetime.utcnow()
            db.add(existing)
        else:
            a = FlowAssignment(
                batch_id=batch_id,
                question_id=q.id,
                assignee_user_id=assignee_id,
                role=role,
                assigned_by=str(admin.id),
                status="active",
            )
            db.add(a)
        created.append({"question_no": q.question_no, "role": role, "assignee_user_id": assignee_id})

    created: List[dict] = []
    if body.mode == "random":
        teachers = _candidate_teachers(db, batch.subject or "", max_teachers)
        # 本地自测兜底：同科目老师不足时，指派给管理员自己（部署后可去掉此兜底）
        if not teachers:
            teachers = [admin]
        double_needed = any((q.review_mode or batch.review_mode) == "double" for q in questions)
        if not teachers or (double_needed and len(teachers) < 2):
            raise HTTPException(status_code=400, detail="同科目候选老师不足")
        shuffled = list(teachers)
        random.shuffle(shuffled)
        n = len(shuffled)
        for i, q in enumerate(questions):
            mode = q.review_mode or batch.review_mode
            if mode == "double":
                a1 = shuffled[i % n]
                a2 = shuffled[(i + 1) % n]
                if n > 1 and a2.id == a1.id:
                    a2 = shuffled[(i + 2) % n]
                _add(q, a1.id, "first")
                _add(q, a2.id, "second")
            else:
                _add(q, shuffled[i % n].id, "single")
    else:
        spec = {int(a.get("question_no")): a.get("assignee_ids") or [] for a in body.assignments}
        for q in questions:
            mode = q.review_mode or batch.review_mode
            ids = spec.get(q.question_no) or []
            if mode == "double":
                if len(ids) < 2:
                    raise HTTPException(status_code=400, detail=f"第{q.question_no}题（双评）需指定两名老师")
                _add(q, ids[0], "first")
                _add(q, ids[1], "second")
            else:
                if not ids:
                    raise HTTPException(status_code=400, detail=f"第{q.question_no}题需指定老师")
                _add(q, ids[0], "single")

    db.commit()
    db.query(FlowQuestion).filter(FlowQuestion.batch_id == batch_id).update({"status": "assigned"})
    batch.status = "grading"
    db.commit()
    return {"ok": True, "created": created}


# ── 进度 / 速度看板 ───────────────────────────────────────────────────────

def _speed_stats(times: List[datetime]) -> tuple:
    times = [t for t in times if t]
    speed_per_min = 0.0
    if len(times) >= 2:
        span_min = max((max(times) - min(times)).total_seconds() / 60.0, 0.0167)
        speed_per_min = round(len(times) / span_min, 2)
    now = datetime.utcnow()
    recent = [t for t in times if (now - t).total_seconds() <= 600]
    rolling = round(len(recent) / 10.0, 2) if recent else 0.0
    return speed_per_min, rolling


@router.get("/batches/{batch_id}/progress")
def api_progress(
    batch_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin_permission(db, user_id)
    batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    assignments = (
        db.query(FlowAssignment)
        .filter(FlowAssignment.batch_id == batch_id, FlowAssignment.status == "active")
        .order_by(FlowAssignment.role.asc())
        .all()
    )
    out = []
    for a in assignments:
        q = db.query(FlowQuestion).filter(FlowQuestion.id == a.question_id).first()
        u = db.query(User).filter(User.id == a.assignee_user_id).first()
        if not q:
            continue
        total = q.total_items or 0
        graded = (
            db.query(FlowReview)
            .filter(
                FlowReview.question_id == q.id,
                FlowReview.reviewer_user_id == a.assignee_user_id,
                FlowReview.is_current.is_(True),
            )
            .count()
        )
        times = [
            r[0]
            for r in db.query(FlowReview.submitted_at)
            .filter(
                FlowReview.question_id == q.id,
                FlowReview.reviewer_user_id == a.assignee_user_id,
                FlowReview.submitted_at.isnot(None),
            )
            .all()
            if r[0]
        ]
        speed_per_min, rolling = _speed_stats(times)
        out.append(
            {
                "assignment_id": a.id,
                "teacher_id": a.assignee_user_id,
                "teacher_name": u.display_name if u else "",
                "question_no": q.question_no,
                "display_label": q.display_label or f"第{q.question_no}题",
                "role": a.role,
                "review_mode": q.review_mode or batch.review_mode,
                "total_items": total,
                "graded_items": graded,
                "progress": round(graded / total, 4) if total else 0,
                "speed_per_min": speed_per_min,
                "rolling_speed_per_min": rolling,
                "last_submitted_at": _iso(max(times)) if times else None,
            }
        )
    return {"ok": True, "items": out}


@router.get("/batches/{batch_id}/questions/{question_id}/reviews")
def api_question_reviews(
    batch_id: str,
    question_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin_permission(db, user_id)
    q = db.query(FlowQuestion).filter(FlowQuestion.id == question_id, FlowQuestion.batch_id == batch_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    items = (
        db.query(FlowItem)
        .filter(FlowItem.question_id == question_id)
        .order_by(FlowItem.paper_name.asc())
        .all()
    )
    out = []
    for it in items:
        reviews = (
            db.query(FlowReview)
            .filter(FlowReview.item_id == it.id, FlowReview.is_current.is_(True))
            .order_by(FlowReview.round.asc())
            .all()
        )
        out.append(
            {
                "item_id": it.id,
                "student_name": it.student_name,
                "student_number": it.student_number,
                "paper_name": it.paper_name,
                "crop_url": build_download_url(f"grading/flow/files/{batch_id}/{it.crop_path}", user_id) if it.crop_path else "",
                "final_score": it.final_score,
                "final_status": it.final_status,
                "status": it.status,
                "reviews": [
                    {
                        "review_id": r.id,
                        "round": r.round,
                        "score": r.score,
                        "status": r.status,
                        "marks": r.marks_json,
                        "comment": r.comment,
                        "reviewer_user_id": r.reviewer_user_id,
                        "submitted_at": _iso(r.submitted_at),
                    }
                    for r in reviews
                ],
            }
        )
    return {"ok": True, "items": out}


# ── 双评仲裁 ──────────────────────────────────────────────────────────────

class ArbitrationRequest(BaseModel):
    final_score: float
    final_status: Optional[str] = None
    reason: Optional[str] = None


@router.get("/batches/{batch_id}/arbitrations")
def api_list_arbitrations(
    batch_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin_permission(db, user_id)
    batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    items = (
        db.query(FlowItem)
        .filter(FlowItem.batch_id == batch_id, FlowItem.status == "arbitration_pending")
        .order_by(FlowItem.paper_name.asc())
        .all()
    )
    out = []
    for it in items:
        q = db.query(FlowQuestion).filter(FlowQuestion.id == it.question_id).first()
        reviews = (
            db.query(FlowReview)
            .filter(FlowReview.item_id == it.id, FlowReview.is_current.is_(True))
            .order_by(FlowReview.round.asc())
            .all()
        )
        out.append(
            {
                "item_id": it.id,
                "question_no": q.question_no if q else None,
                "display_label": q.display_label if q else "",
                "max_score": it.max_score if it.max_score else (q.max_score if q else 0),
                "student_name": it.student_name,
                "student_number": it.student_number,
                "paper_name": it.paper_name,
                "crop_url": build_download_url(f"grading/flow/files/{batch_id}/{it.crop_path}", user_id) if it.crop_path else "",
                "reviews": [
                    {
                        "review_id": r.id,
                        "round": r.round,
                        "score": r.score,
                        "status": r.status,
                        "marks": r.marks_json,
                        "comment": r.comment,
                        "reviewer_user_id": r.reviewer_user_id,
                        "submitted_at": _iso(r.submitted_at),
                    }
                    for r in reviews
                ],
            }
        )
    return {"ok": True, "items": out}


@router.post("/arbitrations/{item_id}")
def api_arbitrate(
    item_id: str,
    body: ArbitrationRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    admin = _check_admin_permission(db, user_id)
    item = db.query(FlowItem).filter(FlowItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")
    reviews = (
        db.query(FlowReview)
        .filter(FlowReview.item_id == item_id, FlowReview.is_current.is_(True))
        .order_by(FlowReview.round.asc())
        .all()
    )
    if len(reviews) < 2:
        raise HTTPException(status_code=400, detail="该条目未满两评，暂无需仲裁")
    r1, r2 = reviews[0], reviews[1]
    arb = FlowArbitration(
        batch_id=item.batch_id,
        question_id=item.question_id,
        item_id=item.id,
        arbiter_user_id=str(admin.id),
        first_review_id=r1.id,
        second_review_id=r2.id,
        first_score=r1.score,
        second_score=r2.score,
        final_score=float(body.final_score),
        final_status=body.final_status or r1.status,
        reason=body.reason,
    )
    db.add(arb)
    item.final_score = float(body.final_score)
    item.final_status = body.final_status or r1.status
    item.final_review_id = r1.id
    item.status = "arbitrated"
    db.commit()
    return {"ok": True, "arbitration_id": arb.id, "final_score": item.final_score}
