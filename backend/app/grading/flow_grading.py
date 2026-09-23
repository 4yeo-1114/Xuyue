# -*- coding: utf-8 -*-
"""流水阅卷 / 集体阅卷 —— 老师端接口 + 共享文件服务。

老师端点走 get_current_user_id（dependencies.py:12）；文件服务校验「请求者是该题 assignee 或管理员」。
留痕：marks 存归一化坐标 [{x,y,type}]，由前端从 marks_json 渲染，后端不合成图片。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.grading.file_auth import user_id_from_request
from app.grading.flow_paths import flow_crops_dir, flow_marks_dir, flow_papers_dir
from app.grading.flow_pipeline import sync_standard_answers
from app.grading.response_log_db import write_response_logs
from app.models.flow_grading import FlowAssignment, FlowBatch, FlowItem, FlowQuestion, FlowReview
from app.models.user import User
from app.utils.school_access import is_school_admin
from app.utils.security import build_download_url

router = APIRouter(prefix="/grading/flow", tags=["flow"])
file_router = APIRouter(prefix="/grading/flow/files", tags=["flow-files"])

_CLAIM_MINUTES = 30


class ReviewSubmitRequest(BaseModel):
    assignment_id: str
    item_id: str
    score: float = 0
    status: str = "correct"  # correct|wrong|partial|unanswered
    marks: Optional[list] = None  # [{x,y,type}]
    comment: Optional[str] = None


class ReviewReviseRequest(BaseModel):
    score: Optional[float] = None
    status: Optional[str] = None
    marks: Optional[list] = None
    comment: Optional[str] = None


def _iso(dt) -> Optional[str]:
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


# ── 老师任务 ──────────────────────────────────────────────────────────────

@router.get("/tasks")
def api_my_tasks(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    rows = (
        db.query(FlowAssignment)
        .filter(FlowAssignment.assignee_user_id == user_id, FlowAssignment.status == "active")
        .all()
    )
    items = []
    for a in rows:
        q = db.query(FlowQuestion).filter(FlowQuestion.id == a.question_id).first()
        b = db.query(FlowBatch).filter(FlowBatch.id == a.batch_id).first()
        if not q or not b:
            continue
        total = q.total_items or 0
        graded = _my_graded_count(db, q.id, user_id)
        items.append(
            {
                "assignment_id": a.id,
                "batch_id": b.id,
                "batch_name": b.name,
                "subject": b.subject,
                "question_no": q.question_no,
                "display_label": q.display_label or f"第{q.question_no}题",
                "max_score": q.max_score,
                "role": a.role,
                "review_mode": q.review_mode or b.review_mode,
                "total_items": total,
                "graded_items": graded,
                "progress": round(graded / total, 4) if total else 0,
            }
        )
    return {"ok": True, "items": items}


def _my_graded_count(db: Session, question_id: str, user_id: str) -> int:
    return (
        db.query(FlowReview)
        .filter(
            FlowReview.question_id == question_id,
            FlowReview.reviewer_user_id == user_id,
            FlowReview.is_current.is_(True),
        )
        .count()
    )


@router.get("/tasks/{assignment_id}")
def api_task_detail(
    assignment_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    a = (
        db.query(FlowAssignment)
        .filter(FlowAssignment.id == assignment_id, FlowAssignment.assignee_user_id == user_id)
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="任务不存在")
    q = db.query(FlowQuestion).filter(FlowQuestion.id == a.question_id).first()
    b = db.query(FlowBatch).filter(FlowBatch.id == a.batch_id).first()
    if not q or not b:
        raise HTTPException(status_code=404, detail="任务数据缺失")
    sync_standard_answers(db, b)
    total = q.total_items or 0
    graded = _my_graded_count(db, q.id, user_id)
    return {
        "ok": True,
        "assignment_id": a.id,
        "batch_id": b.id,
        "batch_name": b.name,
        "subject": b.subject,
        "question_no": q.question_no,
        "display_label": q.display_label or f"第{q.question_no}题",
        "max_score": q.max_score,
        "standard_answer": q.standard_answer,
        "role": a.role,
        "review_mode": q.review_mode or b.review_mode,
        "total_items": total,
        "graded_items": graded,
        "progress": round(graded / total, 4) if total else 0,
    }


@router.get("/tasks/{assignment_id}/next")
def api_next_item(
    assignment_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    a = (
        db.query(FlowAssignment)
        .filter(FlowAssignment.id == assignment_id, FlowAssignment.assignee_user_id == user_id, FlowAssignment.status == "active")
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="任务不存在")
    q = db.query(FlowQuestion).filter(FlowQuestion.id == a.question_id).first()
    b = db.query(FlowBatch).filter(FlowBatch.id == a.batch_id).first()
    if not q or not b:
        raise HTTPException(status_code=404, detail="任务数据缺失")

    sync_standard_answers(db, b)

    item = _claim_next(db, q.id, user_id)
    if not item:
        return {"ok": True, "claimed": False}

    crop_url = _file_url(item.batch_id, item.crop_path or "", user_id)
    paper_url = _file_url(item.batch_id, item.full_paper_path or "", user_id)
    return {
        "ok": True,
        "claimed": True,
        "item_id": item.id,
        "student_name": item.student_name,
        "student_number": item.student_number,
        "paper_name": item.paper_name,
        "crop_url": crop_url,
        "full_paper_url": paper_url,
        "max_score": item.max_score if item.max_score else q.max_score,
        "standard_answer": q.standard_answer,
        "question_no": q.question_no,
        "display_label": q.display_label or f"第{q.question_no}题",
    }


def _claim_next(db: Session, question_id: str, user_id: str) -> Optional[FlowItem]:
    reviewed_ids = [
        r[0]
        for r in db.query(FlowReview.item_id)
        .filter(FlowReview.reviewer_user_id == user_id, FlowReview.is_current.is_(True))
        .all()
    ]
    query = (
        db.query(FlowItem)
        .filter(FlowItem.question_id == question_id)
        .filter(
            (FlowItem.status == "pending")
            | ((FlowItem.status == "claimed") & (FlowItem.claimed_by_user_id == user_id))
        )
        .order_by(FlowItem.paper_name.asc(), FlowItem.id.asc())
    )
    if reviewed_ids:
        query = query.filter(FlowItem.id.notin_(reviewed_ids))
    item = query.with_for_update().first()
    if not item:
        return None
    item.status = "claimed"
    item.claimed_by_user_id = user_id
    item.claimed_at = datetime.utcnow()
    item.claim_expires_at = datetime.utcnow() + timedelta(minutes=_CLAIM_MINUTES)
    db.commit()
    return item


def _file_url(batch_id: str, rel_path: str, user_id: str) -> str:
    if not rel_path:
        return ""
    return build_download_url(f"grading/flow/files/{batch_id}/{rel_path}", user_id)


# ── 提交 / 改分 ───────────────────────────────────────────────────────────

@router.post("/reviews")
def api_submit_review(
    body: ReviewSubmitRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    a = (
        db.query(FlowAssignment)
        .filter(
            FlowAssignment.id == body.assignment_id,
            FlowAssignment.assignee_user_id == user_id,
            FlowAssignment.status == "active",
        )
        .first()
    )
    if not a:
        raise HTTPException(status_code=403, detail="无权提交该任务")
    item = (
        db.query(FlowItem)
        .filter(FlowItem.id == body.item_id, FlowItem.question_id == a.question_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="题目条目不存在")
    question = db.query(FlowQuestion).filter(FlowQuestion.id == a.question_id).first()
    batch = db.query(FlowBatch).filter(FlowBatch.id == a.batch_id).first()
    if not question or not batch:
        raise HTTPException(status_code=404, detail="任务数据缺失")

    review = _write_review(db, a, item, question, batch, user_id, body.score, body.status, body.marks, body.comment)
    result = {
        "ok": True,
        "review_id": review.id,
        "finalized": item.status in ("graded", "arbitrated"),
        "final_score": item.final_score,
        "need_arbitration": item.status == "arbitration_pending",
    }
    db.commit()
    _write_flow_log(batch, question, item, user_id, review.score, review.status)
    return result


@router.post("/reviews/{review_id}/revise")
def api_revise_review(
    review_id: str,
    body: ReviewReviseRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    old = (
        db.query(FlowReview)
        .filter(FlowReview.id == review_id, FlowReview.reviewer_user_id == user_id)
        .first()
    )
    if not old:
        raise HTTPException(status_code=404, detail="批改记录不存在")
    item = db.query(FlowItem).filter(FlowItem.id == old.item_id).first()
    question = db.query(FlowQuestion).filter(FlowQuestion.id == old.question_id).first()
    batch = db.query(FlowBatch).filter(FlowBatch.id == old.batch_id).first()
    if not item or not question or not batch:
        raise HTTPException(status_code=404, detail="数据缺失")
    a = (
        db.query(FlowAssignment)
        .filter(
            FlowAssignment.id == old.assignment_id,
            FlowAssignment.assignee_user_id == user_id,
        )
        .first()
    )
    if not a:
        raise HTTPException(status_code=403, detail="无权修改")

    old.is_current = False
    review = _write_review(
        db, a, item, question, batch, user_id,
        body.score if body.score is not None else old.score,
        body.status or old.status,
        body.marks if body.marks is not None else old.marks_json,
        body.comment if body.comment is not None else old.comment,
        revised_from=old.id,
    )
    db.commit()
    _write_flow_log(batch, question, item, user_id, review.score, review.status)
    return {"ok": True, "review_id": review.id, "final_score": item.final_score}


def _write_review(db, a, item, question, batch, user_id, score, status, marks, comment, revised_from=None):
    round_no = 2 if a.role == "second" else 1
    db.query(FlowReview).filter(
        FlowReview.item_id == item.id,
        FlowReview.reviewer_user_id == user_id,
        FlowReview.is_current.is_(True),
    ).update({"is_current": False})
    review = FlowReview(
        batch_id=item.batch_id,
        question_id=item.question_id,
        item_id=item.id,
        assignment_id=a.id,
        reviewer_user_id=user_id,
        round=round_no,
        score=float(score or 0),
        status=status,
        marks_json=marks,
        comment=comment,
        is_current=True,
        revised_from=revised_from,
        submitted_at=datetime.utcnow(),
    )
    db.add(review)
    db.flush()
    _after_review(db, item, question, batch)
    return review


def _after_review(db: Session, item: FlowItem, question: FlowQuestion, batch: FlowBatch) -> bool:
    mode = question.review_mode or batch.review_mode
    reviews = (
        db.query(FlowReview)
        .filter(FlowReview.item_id == item.id, FlowReview.is_current.is_(True))
        .order_by(FlowReview.submitted_at.asc())
        .all()
    )
    if mode == "double" and len(reviews) < 2:
        # 二评未齐，释放 claim 供另一位老师领取
        item.status = "pending"
        item.claimed_by_user_id = None
        item.claimed_at = None
        item.claim_expires_at = None
        return False
    if mode == "double":
        r1, r2 = reviews[0], reviews[1]
        if abs((r1.score or 0) - (r2.score or 0)) <= 0.001:
            item.final_score = r1.score
            item.final_status = r1.status
            item.final_review_id = r1.id
            item.status = "graded"
        else:
            item.status = "arbitration_pending"
    else:
        if reviews:
            r = reviews[0]
            item.final_score = r.score
            item.final_status = r.status
            item.final_review_id = r.id
            item.status = "graded"
    return True


def _write_flow_log(batch: FlowBatch, question: FlowQuestion, item: FlowItem, reviewer_id: str, score: float, status: str) -> None:
    """旁路写 response_logs（engine="flow"），与现有学情/错题底座打通，失败静默。"""
    max_score = item.max_score if item.max_score else question.max_score
    write_response_logs(
        user_id=reviewer_id,
        folder_safe=batch.id,
        paper_name=item.paper_name,
        engine="flow",
        blocks=[{"index": question.question_no, "score": score, "max_score": max_score, "status": status}],
        subject=batch.subject,
        grade=batch.grade,
    )


# ── 历史 / 速度 ───────────────────────────────────────────────────────────

@router.get("/tasks/{assignment_id}/history")
def api_task_history(
    assignment_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    a = db.query(FlowAssignment).filter(FlowAssignment.id == assignment_id).first()
    if not a or a.assignee_user_id != user_id:
        raise HTTPException(status_code=403, detail="无权查看")
    rows = (
        db.query(FlowReview)
        .filter(
            FlowReview.assignment_id == assignment_id,
            FlowReview.reviewer_user_id == user_id,
        )
        .order_by(FlowReview.submitted_at.desc())
        .limit(200)
        .all()
    )
    out = []
    for r in rows:
        item = db.query(FlowItem).filter(FlowItem.id == r.item_id).first()
        out.append(
            {
                "review_id": r.id,
                "item_id": r.item_id,
                "student_name": item.student_name if item else "",
                "student_number": item.student_number if item else "",
                "paper_name": item.paper_name if item else "",
                "crop_url": _file_url(item.batch_id, item.crop_path or "", user_id) if item else "",
                "score": r.score,
                "status": r.status,
                "comment": r.comment,
                "marks": r.marks_json,
                "round": r.round,
                "is_current": r.is_current,
                "revised_from": r.revised_from,
                "submitted_at": _iso(r.submitted_at),
            }
        )
    return {"ok": True, "items": out}


@router.get("/tasks/{assignment_id}/speed")
def api_task_speed(
    assignment_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    a = db.query(FlowAssignment).filter(FlowAssignment.id == assignment_id).first()
    if not a or a.assignee_user_id != user_id:
        raise HTTPException(status_code=403, detail="无权查看")
    q = db.query(FlowQuestion).filter(FlowQuestion.id == a.question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="数据缺失")
    total = q.total_items or 0
    graded = _my_graded_count(db, q.id, user_id)
    times = [
        r[0]
        for r in db.query(FlowReview.submitted_at)
        .filter(FlowReview.assignment_id == assignment_id, FlowReview.reviewer_user_id == user_id, FlowReview.submitted_at.isnot(None))
        .all()
        if r[0]
    ]
    speed_per_min = 0.0
    if len(times) >= 2:
        span_min = max((max(times) - min(times)).total_seconds() / 60.0, 0.0167)
        speed_per_min = round(len(times) / span_min, 2)
    now = datetime.utcnow()
    recent_minutes = [t for t in times if (now - t).total_seconds() <= 600]
    rolling_speed = round(len(recent_minutes) / 10.0, 2) if recent_minutes else 0.0
    return {
        "ok": True,
        "total_items": total,
        "graded_items": graded,
        "progress": round(graded / total, 4) if total else 0,
        "speed_per_min": speed_per_min,
        "rolling_speed_per_min": rolling_speed,
        "recent": [
            {"submitted_at": _iso(t), "score": 0} for t in sorted(times, reverse=True)[:20]
        ],
    }


# ── 共享文件服务 ──────────────────────────────────────────────────────────

_KIND_DIRS = {"crops": flow_crops_dir, "papers": flow_papers_dir, "marks": flow_marks_dir}


@file_router.get("/{batch_id}/{kind}/{path:path}")
def serve_flow_file(
    batch_id: str,
    kind: str,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if kind not in _KIND_DIRS:
        raise HTTPException(status_code=400, detail="无效文件类型")
    user_id = user_id_from_request(request, resource=f"grading/flow/files/{batch_id}/{kind}/{path}")

    u = db.query(User).filter(User.id == user_id).first()
    admin = bool(u and is_school_admin(u))
    if not admin and not _can_access(db, batch_id, kind, path, user_id):
        raise HTTPException(status_code=403, detail="无权访问该文件")

    base = _KIND_DIRS[kind](batch_id)
    full = (base / path).resolve()
    if not full.is_relative_to(base.resolve()):
        raise HTTPException(status_code=403, detail="无效路径")
    if not full.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(full))


def _can_access(db: Session, batch_id: str, kind: str, path: str, user_id: str) -> bool:
    if kind == "crops":
        m = re.match(r"^q(\d+)/", path)
        if not m:
            return False
        q = (
            db.query(FlowQuestion)
            .filter(FlowQuestion.batch_id == batch_id, FlowQuestion.question_no == int(m.group(1)))
            .first()
        )
        if not q:
            return False
        return (
            db.query(FlowAssignment)
            .filter(
                FlowAssignment.question_id == q.id,
                FlowAssignment.assignee_user_id == user_id,
                FlowAssignment.status == "active",
            )
            .first()
            is not None
        )
    return (
        db.query(FlowAssignment)
        .filter(
            FlowAssignment.batch_id == batch_id,
            FlowAssignment.assignee_user_id == user_id,
            FlowAssignment.status == "active",
        )
        .first()
        is not None
    )
