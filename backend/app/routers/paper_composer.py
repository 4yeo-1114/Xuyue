# -*- coding: utf-8 -*-
"""R6c 薄弱点闭环组卷 REST 层（融合 P2-2 智能组卷）。

POST /api/v1/papers/compose
body: {subject, grade?, weak_kps?, count?, difficulty?, class_id?, student_id?}

- 薄弱点缺省：从 R6a 桥表 wrong_question_kp_bridge 按 class_id（或全校）聚合 top N
  （confidence>=0.8 过滤松匹配），经 PG 资产库抽题组卷。
- 鉴权：class_id 经 can_view_class 校验；student_id 先解析其班级再校验（参考 student_analysis._assert_class_access）。
- 落库：smart_exam_papers（questions JSON 存题列表，含 kp/difficulty/difficulty_source）。
- 降级：PG 不可用 → 503（同 school_assets 模式）；无薄弱点 → 学科+年级随机抽卷不报错。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.assets.database import get_asset_db
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.exam import SmartExamPaper
from app.models.student import Student
from app.models.student_analysis import StudentWrongQuestion
from app.models.wrong_question_kp_bridge import WrongQuestionKpBridge
from app.schemas.common import ApiResponse
from app.services.paper_composer import compose_paper
from app.utils.class_access import can_view_class

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/papers", tags=["paper_composer"])

# 薄弱点缺省聚合 TOP N
_DEFAULT_WEAK_KP_TOP = 6


class ComposePaperRequest(BaseModel):
    subject: str = Field(..., description="学科，如 数学/语文")
    grade: Optional[str] = Field(None, description="学段：小学/初中/高中")
    weak_kps: Optional[List[Any]] = Field(
        None, description="薄弱知识点：kp id / kp 名 / {id?, name?, count?} 列表；缺省自动聚合"
    )
    count: int = Field(10, ge=1, le=50, description="题量")
    difficulty: Optional[str] = Field(None, description="难度偏好：易/中/难 或 1-5")
    class_id: Optional[str] = Field(None, description="班级（用于鉴权 + 缺省薄弱点聚合）")
    student_id: Optional[str] = Field(None, description="学生（解析其班级做鉴权）")


def _guard_enabled() -> None:
    """503 守卫一：未配置资产库（enabled=False）直接拒绝。"""
    if not settings.ASSETS_DB_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db not configured"},
        )


def _safe_query(fn, *args, **kwargs) -> Any:
    """503 守卫二：PG 不可达 / 查询异常 → 503，绝不裸 500（同 school_assets 模式）。"""
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.warning("paper compose assets db query failed", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db unreachable"},
        )


def _aggregate_weak_kps(db: Session, subject: str, class_id: Optional[str],
                        top_n: int = _DEFAULT_WEAK_KP_TOP) -> list:
    """从 R6a 桥表聚合薄弱点：按 (kp_name, kp_id) 计错题频次，confidence>=0.8 过滤松匹配。

    class_id 缺省 → 全校聚合（该学科全部班级错题）。
    """
    q = (
        db.query(
            WrongQuestionKpBridge.kp_name,
            WrongQuestionKpBridge.kp_id,
            func.count().label("cnt"),
        )
        .join(
            StudentWrongQuestion,
            StudentWrongQuestion.id == WrongQuestionKpBridge.wrong_question_id,
        )
        .filter(
            WrongQuestionKpBridge.subject == subject,
            (WrongQuestionKpBridge.confidence.is_(None))
            | (WrongQuestionKpBridge.confidence >= 0.8),
        )
        .group_by(WrongQuestionKpBridge.kp_name, WrongQuestionKpBridge.kp_id)
        .order_by(func.count().desc())
    )
    if class_id:
        q = q.filter(StudentWrongQuestion.class_id == class_id)
    rows = q.limit(top_n).all()
    return [
        {"name": r.kp_name, "id": r.kp_id or "", "count": int(r.cnt or 0)}
        for r in rows
    ]


def _assert_class_access(db: Session, user_id: str, class_id: str) -> None:
    """校验调用者对目标班级有访问权限（同 student_analysis._assert_class_access）。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")


@router.post("/compose", response_model=ApiResponse[dict])
def compose_paper_route(
    body: ComposePaperRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    asset_db: Session = Depends(get_asset_db),
):
    """按薄弱知识点组卷并落库 smart_exam_papers。

    - weak_kps 缺省时按 class_id（或全校）聚合桥表 top N 薄弱点。
    - class_id/student_id 做班级访问鉴权。
    - PG 不可用降级 503；无薄弱点自动切学科+年级随机抽卷。
    """
    # ── 鉴权：解析学生归属班级 + 班级访问校验 ──────────────────────
    target_class_id = body.class_id
    if body.student_id:
        stu = db.query(Student).filter(Student.id == body.student_id).first()
        if not stu:
            raise HTTPException(status_code=404, detail="学生不存在")
        target_class_id = stu.class_id
    if target_class_id:
        _assert_class_access(db, user_id, target_class_id)

    # ── 薄弱点：显式传入优先，否则桥表聚合 ─────────────────────────
    weak_kps: Any = body.weak_kps
    if not weak_kps:
        weak_kps = _aggregate_weak_kps(db, body.subject, target_class_id)
        if weak_kps:
            logger.info(
                "paper compose: aggregated %d weak kps for subject=%s class=%s",
                len(weak_kps), body.subject, target_class_id or "(school)",
            )

    # ── 组卷：PG 抽题（503 降级守卫包裹）───────────────────────────
    _guard_enabled()
    result = _safe_query(
        compose_paper,
        asset_db,
        body.subject,
        body.grade,
        weak_kps,
        body.count,
        body.difficulty,
    )
    questions = result["questions"]

    # ── 落库 smart_exam_papers（questions JSON 存题列表含 kp/difficulty）──
    title = (
        f"{body.subject}{body.grade or ''}薄弱点组卷"
        f"-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    paper = SmartExamPaper(
        user_id=user_id,
        title=title,
        subject=body.subject,
        questions=questions,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    return ApiResponse(data={
        "paper_id": paper.id,
        "title": paper.title,
        "subject": paper.subject,
        "grade": body.grade,
        "class_id": target_class_id,
        "count": len(questions),
        "questions": questions,
        "meta": result["meta"],
        "weak_kps": weak_kps,
    })
