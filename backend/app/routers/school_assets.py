# -*- coding: utf-8 -*-
"""学校资产引擎只读 REST 层（P0-B3）。

家长端 PG 资产库（app/assets/）的 REST 暴露：

- GET  /school-assets/kp/tree?subject=<学科>         → 知识点树节点
- GET  /school-assets/questions?subject=<学科>&limit=N → 按学科取题
- GET  /school-assets/questions/by-kp?knowledge_point_id=<id>&count=N → 按知识点取题
- GET  /school-assets/questions/random?subject=&grade=&count=N        → 按学段随机抽题
- POST /school-assets/similar-questions               → 相似题（MVP 简版：difflib 文本相似度）

降级守卫（审核硬要求）：
- ASSETS_DB_ENABLED=False → 503 {"enabled": false, "reason": "assets db not configured"}
- PG 不可达 / 查询异常   → 503 {"enabled": false, "reason": "assets db unreachable"}（绝不裸 500）

相似题为 MVP 简版：取候选集后按 difflib.SequenceMatcher 对题干文本相似度排序取 top，
响应顶层标注 source='similarity-mvp'，后续接 fingerprint 正式方案。
"""
from __future__ import annotations

import difflib
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.assets import repo
from app.assets.database import get_asset_db
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/school-assets", tags=["school_assets"])

# 相似题候选集大小（MVP 简版：一次最多取 50 条候选做文本比对）
_SIMILAR_CANDIDATE_LIMIT = 50


def _guard_enabled() -> None:
    """503 守卫一：未配置资产库（enabled=False）直接拒绝。"""
    if not settings.ASSETS_DB_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db not configured"},
        )


def _safe_query(fn, *args, **kwargs) -> Any:
    """503 守卫二：PG 不可达 / 查询异常 → 503，绝不裸 500。"""
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.warning("assets db query failed", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db unreachable"},
        )


@router.get("/kp/tree")
def list_kp_tree(
    subject: str = Query(..., description="学科，如 数学/物理"),
    _db: Session = Depends(get_asset_db),
):
    """按学科返回知识点树节点列表（id/code/name/level/knowledge_nature/unit_id）。"""
    _guard_enabled()
    items = _safe_query(repo.get_kp_tree, subject)
    return {"items": items, "count": len(items)}


@router.get("/questions")
def list_questions(
    subject: str = Query(..., description="学科，如 物理"),
    limit: int = Query(5, ge=1, le=50, description="返回条数"),
    _db: Session = Depends(get_asset_db),
):
    """按学科取题（quality_flag ok/filled/NULL 放行）。"""
    _guard_enabled()
    items = _safe_query(repo.get_questions, subject, limit)
    return {"items": items, "count": len(items)}


@router.get("/questions/by-kp")
def list_questions_by_kp(
    knowledge_point_id: str = Query(..., description="知识点 id"),
    count: int = Query(5, ge=1, le=50, description="返回条数"),
    _db: Session = Depends(get_asset_db),
):
    """经 question_kp 桥接表按知识点取题。"""
    _guard_enabled()
    items = _safe_query(repo.get_questions_by_kp, knowledge_point_id, count)
    return {"items": items, "count": len(items)}


@router.get("/questions/random")
def list_random_questions(
    subject: str = Query(..., description="学科，如 数学"),
    grade: str = Query(..., description="学段：小学/初中/高中/大学"),
    count: int = Query(5, ge=1, le=50, description="返回条数"),
    _db: Session = Depends(get_asset_db),
):
    """按学科+学段随机抽题（ai_verdict != 'reject' 且 quality 放行）。"""
    _guard_enabled()
    items = _safe_query(repo.get_random_questions, subject, grade, count)
    return {"items": items, "count": len(items)}


class SimilarQuestionsRequest(BaseModel):
    question: str
    subject: str
    count: int = Field(default=5, ge=1, le=20)


@router.post("/similar-questions")
def similar_questions(
    body: SimilarQuestionsRequest,
    _db: Session = Depends(get_asset_db),
):
    """相似题（MVP 简版）：候选集内按 difflib 题干文本相似度排序取 top count。

    响应标注 source='similarity-mvp'；每项附 similarity 相似度分。
    正式方案后续接 fingerprint，本实现不做重型算法。
    """
    _guard_enabled()
    candidates = _safe_query(repo.get_questions, body.subject, _SIMILAR_CANDIDATE_LIMIT)
    query_text = (body.question or "").strip()
    scored: list[dict] = []
    for q in candidates:
        q_text = str(q.get("question") or "").strip()
        if not q_text:
            continue
        ratio = difflib.SequenceMatcher(None, query_text, q_text).ratio()
        if ratio > 0:
            item = dict(q)
            item["similarity"] = round(ratio, 4)
            scored.append(item)
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    top = scored[: body.count]
    return {"source": "similarity-mvp", "items": top, "count": len(top)}


@router.get("/filters")
def list_filters(_db: Session = Depends(get_asset_db)):
    """返回筛选下拉可用的枚举值（学科/学段/题型/难度）。"""
    _guard_enabled()
    return _safe_query(repo.get_filters)


@router.get("/questions/search")
def search_questions(
    subject: str | None = Query(None, description="学科，如 数学"),
    grade: str | None = Query(None, description="学段/年级"),
    question_type: str | None = Query(None, description="题型"),
    difficulty: int | None = Query(None, ge=1, description="难度"),
    knowledge_point: str | None = Query(None, description="知识点关键词"),
    keyword: str | None = Query(None, description="题干关键词"),
    page: int = Query(1, ge=1, description="页码，从 1 起"),
    page_size: int = Query(20, ge=1, le=50, description="每页条数"),
    _db: Session = Depends(get_asset_db),
):
    """题库多条件组合检索 + 分页（quality ok/filled/NULL 放行）。

    返回 {items, total, page, page_size}，total 供前端分页条数。
    """
    _guard_enabled()
    items, total = _safe_query(
        repo.search_questions,
        subject,
        grade,
        question_type,
        difficulty,
        knowledge_point,
        keyword,
        page,
        page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
