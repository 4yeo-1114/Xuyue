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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.assets.database import get_asset_db, get_asset_db_optional
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.exam import SmartExamPaper
from app.models.student import Student
from app.models.student_analysis import StudentWrongQuestion
from app.models.wrong_question_kp_bridge import WrongQuestionKpBridge
from app.schemas.common import ApiResponse
from app.services.ai_policy import assert_no_sensitive_input, require_ai_access
from app.services.paper_composer import (
    compose_paper,
    compose_tiered_papers,
    compose_tiered_papers_ai,
    difficulty_summary,
    read_class_tiers,
    unpack_paper_questions,
)
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


# ── 分层组卷：A/B/C 各一份 ──────────────────────────────────────────


class TieredComposeRequirement(BaseModel):
    """AI 题型模板（仿 AI 组卷）：type 取 ExamQuestion 英文枚举，count 题量，score 单题分。"""

    type: str
    count: int = Field(..., ge=1, le=50)
    score: float = Field(5, ge=0.5, le=100)


class TieredComposeRequest(BaseModel):
    class_id: str = Field(..., description="班级 ID")
    subject: str = Field(..., description="学科，如 数学/语文")
    grade: Optional[str] = Field(None, description="学段：小学/初中/高中")
    exam_folder: Optional[str] = Field(None, description="考试文件夹（元数据留痕）")
    round_id: Optional[str] = Field(None, description="分层推送轮次 ID（元数据留痕）")
    count: int = Field(10, ge=1, le=50, description="每层题量（未传题型模板时生效）")
    weak_kps: Optional[List[Any]] = Field(
        None, description="薄弱知识点；缺省按班级聚合桥表 top N"
    )
    source: str = Field(
        "ai",
        description='题源："ai"=AI 生成（默认，可选题型/知识点）|"bank"=题库抽题',
    )
    topics: Optional[List[str]] = Field(
        None, description="AI 题源：知识点列表；缺省用薄弱点聚合结果"
    )
    requirements: Optional[List[TieredComposeRequirement]] = Field(
        None, description="AI 题源：题型模板 [{type,count,score}]；缺省按 count 自动配比"
    )


@router.post("/tiered-compose", response_model=ApiResponse[dict])
def tiered_compose_route(
    body: TieredComposeRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    asset_db: Optional[Session] = Depends(get_asset_db_optional),
):
    """按当前 A/B/C 分层各组一份卷，落库 smart_exam_papers（标题标注 A层/B层/C层）。

    - 题源 source：ai（默认，LLM 出题，可选知识点/题型）| bank（PG 题库抽题）。
    - 层间差异：难度带权重 + 知识点粒度（A=压轴/跨知识点，B=标准，C=基础/单一知识点）。
    - 无分层 → 400 明确报错；bank 题源 PG 不可用 → 503；AI 失败 → 500（带原因）。
    """
    _assert_class_access(db, user_id, body.class_id)

    # 分层来自主库 students.tier
    tiers = read_class_tiers(db, body.class_id)
    assigned = sum(len(tiers.get(t) or []) for t in ("A", "B", "C"))
    if assigned == 0:
        raise HTTPException(
            status_code=400,
            detail="该班尚未完成分层，请先在分层推送中自动/手动分层",
        )

    source = (body.source or "ai").strip().lower()
    weak_kps: Any = body.weak_kps
    if not weak_kps:
        weak_kps = _aggregate_weak_kps(db, body.subject, body.class_id)

    if source == "bank":
        _guard_enabled()
        if asset_db is None:
            raise HTTPException(
                status_code=503,
                detail={"enabled": False, "reason": "assets db not configured"},
            )
        try:
            # ValueError（参数/分层）→ 400；其他异常经 _safe_query → 503
            result = compose_tiered_papers(
                asset_db,
                body.class_id,
                body.subject,
                body.grade,
                weak_kps,
                body.count,
                body.round_id,
                body.exam_folder,
                tiers,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e) or "分层组卷参数不合法")
        except Exception:
            logger.warning("tiered compose assets db query failed", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail={"enabled": False, "reason": "assets db unreachable"},
            )
    else:
        # AI 题源：E08 智能组卷管控 + 敏感输入闸（与 /exams/ai-generate 同口径）
        require_ai_access(db, user_id, "smart_exam")
        topics = [str(t).strip() for t in (body.topics or []) if str(t).strip()]
        if not topics:
            topics = [str(k.get("name") or "").strip() for k in (weak_kps or []) if isinstance(k, dict)]
            topics = [t for t in topics if t]
        for kp in topics:
            if assert_no_sensitive_input(kp):
                raise HTTPException(
                    status_code=403,
                    detail="输入包含身份证号/手机号等敏感个人信息，请移除后重试",
                )
        reqs = [r.model_dump() for r in (body.requirements or [])]
        # 全局重活排队（1015 总闸：新重活链路必须包 heavy_slot）
        try:
            from app.services.heavy_budget import heavy_slot

            slot_ctx = heavy_slot("tiered-compose")
        except Exception:
            from contextlib import nullcontext

            slot_ctx = nullcontext(0.0)
        try:
            with slot_ctx:
                result = compose_tiered_papers_ai(
                    db,
                    class_id=body.class_id,
                    subject=body.subject,
                    grade=body.grade,
                    topics=topics,
                    requirements=reqs,
                    count=body.count,
                    round_id=body.round_id,
                    exam_folder=body.exam_folder,
                    tiers=tiers,
                )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e) or "分层组卷参数不合法")
        except Exception as e:
            from app.services.ai_question_gen import AIGenerationError

            if isinstance(e, AIGenerationError):
                logger.warning("tiered compose ai failed: %s", e)
                raise HTTPException(status_code=500, detail=str(e) or "AI 解析失败，请重试或修改提示词")
            logger.warning("tiered compose ai unexpected error", exc_info=True)
            raise HTTPException(status_code=500, detail="AI 解析失败，请重试或修改提示词")

    # 落库三份
    saved = []
    for p in result["papers"]:
        paper = SmartExamPaper(
            user_id=user_id,
            title=p["title"],
            subject=body.subject,
            questions=p["payload"],
        )
        db.add(paper)
        db.flush()
        saved.append(
            {
                "paper_id": paper.id,
                "title": paper.title,
                "subject": paper.subject,
                "tier": p["tier"],
                "tier_label": p["meta"].get("tier_label"),
                "count": len(p["questions"]),
                "difficulty": p["difficulty"],
                "meta": p["meta"],
                "questions": p["questions"],
            }
        )
    db.commit()

    return ApiResponse(
        data={
            "batch_id": result["papers"][0]["meta"].get("batch_id") if result["papers"] else None,
            "class_id": body.class_id,
            "subject": body.subject,
            "tiers": result["tiers"],
            "papers": saved,
        }
    )


@router.get("/tiered-compose/result", response_model=ApiResponse[dict])
def tiered_compose_result(
    class_id: str = Query(..., description="班级 ID"),
    subject: str = Query(..., description="学科"),
    round_id: Optional[str] = Query(None, description="按推送轮次过滤"),
    limit: int = Query(20, ge=1, le=100, description="最多返回多少份卷"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """列分层卷清单：最近一次（或按 round_id）生成的 A/B/C 卷。

    从 smart_exam_papers.questions 的 __tiered_meta__ 哨兵读 tier/班级/轮次。
    """
    _assert_class_access(db, user_id, class_id)

    # 只扫本人试卷、标题含「分层卷」的候选（避免全表 JSON 扫）
    rows = (
        db.query(SmartExamPaper)
        .filter(
            SmartExamPaper.user_id == user_id,
            SmartExamPaper.subject == subject,
            SmartExamPaper.title.contains("分层卷"),
        )
        .order_by(SmartExamPaper.created_at.desc())
        .limit(200)
        .all()
    )

    items = []
    for p in rows:
        meta, exam_qs = unpack_paper_questions(p.questions)
        if not meta or meta.get("source") != "tiered-compose":
            continue
        if meta.get("class_id") and meta.get("class_id") != class_id:
            continue
        if round_id and meta.get("round_id") != round_id:
            continue
        items.append(
            {
                "paper_id": p.id,
                "title": p.title,
                "subject": p.subject,
                "tier": meta.get("tier"),
                "tier_label": meta.get("tier_label"),
                "count": len(exam_qs),
                "difficulty": difficulty_summary(exam_qs),
                "meta": meta,
                "batch_id": meta.get("batch_id"),
                "created_at": meta.get("created_at")
                or (p.created_at.isoformat() if p.created_at else None),
                "questions": exam_qs,
            }
        )

    # 最近一批（batch_id）优先展示；否则返回最新 limit 份
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    latest_batch = items[0].get("batch_id") if items else None
    if not round_id and latest_batch:
        batch_items = [it for it in items if it.get("batch_id") == latest_batch]
        # 保证 A/B/C 顺序
        order = {"A": 0, "B": 1, "C": 2}
        batch_items.sort(key=lambda it: order.get(it.get("tier"), 9))
        return ApiResponse(
            data={
                "class_id": class_id,
                "subject": subject,
                "round_id": round_id,
                "batch_id": latest_batch,
                "papers": batch_items,
                "total": len(batch_items),
            }
        )

    return ApiResponse(
        data={
            "class_id": class_id,
            "subject": subject,
            "round_id": round_id,
            "batch_id": None,
            "papers": items[:limit],
            "total": len(items),
        }
    )
