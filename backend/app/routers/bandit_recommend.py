# -*- coding: utf-8 -*-
"""R6b contextual bandit 错题推荐 REST 层。

- GET /api/v1/recommend/wrong-questions?student_id=&subject=&limit=5
  → 推荐题列表（PG 题）+ 每题推荐理由（kp_name/错因/置信度/推荐模式 explore|exploit|fallback）

降级契约（同 app/routers/school_assets.py 模式）：
- ASSETS_DB_ENABLED=False → 503 {"enabled": false, "reason": "assets db not configured"}
- PG 不可达 / 查询异常 → 503 {"enabled": false, "reason": "assets db unreachable"}（绝不裸 500）
- 学生无错题 / 无薄弱知识点 / PG 无匹配变式题 → 200 mode=fallback + 空 items（诚实降级）
- 鉴权/班级归属校验：_assert_class_access（can_view_class，防 IDOR）
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.assets.database import get_asset_db_optional
from app.config import settings
from app.database import get_db
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.models.student import Student
from app.services.bandit_recommender import (
    AssetDBUnavailable,
    record_click_reward,
    recommend_for_student,
    recommend_for_student_ai,
)
from app.utils.class_access import can_view_class

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommend", tags=["bandit_recommend"])


def _guard_enabled() -> None:
    """503 守卫一：未配置 PG 资产库（enabled=False）直接拒绝。"""
    if not settings.ASSETS_DB_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db not configured"},
        )


def _assert_class_access(db: Session, user_id: str, class_id: str) -> None:
    """校验调用者对目标班级有访问权限，否则 403（对齐 student_analysis 防 IDOR）。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")


class ClickRewardRequest(BaseModel):
    """点击/答题反馈上报 body。

    reward 语义：答对=1，答错=0，由调用方判定正确性后回传。
    生产建议：后续由服务端从 response_logs 判定正确性，本接口预留该演化路径。
    """

    student_id: str
    subject: str
    kp_name: str
    reward: float

    @field_validator("reward")
    @classmethod
    def _validate_reward(cls, v: float) -> float:
        if v not in (0.0, 1.0):
            raise ValueError("reward 必须为 0（答错）或 1（答对）")
        return v


@router.get("/wrong-questions")
def recommend_wrong_questions(
    student_id: str = Query(..., description="学生 id"),
    subject: str = Query(..., description="学科，如 数学/英语"),
    limit: int = Query(5, ge=1, le=20, description="返回推荐题条数"),
    source: str = Query(
        "bank",
        description='题源："bank"=题库变式题（LinUCB）|"ai"=AI 生成变式题（不依赖题库）',
    ),
    types: Optional[str] = Query(None, description="AI 题源：题型偏好，逗号分隔（如 choice,fill）"),
    topics: Optional[str] = Query(None, description="AI 题源：指定知识点，逗号分隔；缺省取薄弱 kp"),
    hint: Optional[str] = Query(None, description="AI 题源：单题题干原文（不拆逗号），单题举一反三入口"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    asset_db: Optional[Session] = Depends(get_asset_db_optional),
):
    """contextual bandit 错题推荐：同 kp 变式题 + 推荐理由。

    - source=bank（默认）：PG 变式题 + LinUCB；未配置题库 → 503（没接题库的诚实报错）。
    - source=ai：LLM 生成变式题（types/topics 可选出题偏好），不碰题库。
    - 无 reward（response_logs=0）时自动走 explore（确定性薄弱点推荐），不报错。
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    _assert_class_access(db, user_id, student.class_id)

    src = (source or "bank").strip().lower()
    if src == "ai":
        type_list = [s.strip() for s in (types or "").split(",") if s.strip()]
        topic_list = []
        for seg in (topics or "").replace("、", ",").replace("，", ",").split(","):
            seg = seg.strip()
            if seg:
                topic_list.append(seg)
        try:
            result = recommend_for_student_ai(
                db,
                student_id=student_id,
                subject=subject,
                limit=limit,
                types=type_list or None,
                topics=topic_list or None,
                hint=hint,
            )
        except Exception:
            logger.exception("bandit: ai recommend failed, degraded")
            return {
                "mode": "ai",
                "student_id": student_id,
                "subject": subject,
                "reason": "AI 推荐服务异常，请稍后重试",
                "items": [],
            }
        return result

    _guard_enabled()
    if asset_db is None:
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db not configured"},
        )
    try:
        result = recommend_for_student(
            db=db,
            asset_db=asset_db,
            student_id=student_id,
            subject=subject,
            limit=limit,
        )
    except AssetDBUnavailable:
        logger.warning("bandit: assets db unavailable for student=%s", student_id)
        raise HTTPException(
            status_code=503,
            detail={"enabled": False, "reason": "assets db unreachable"},
        )
    except Exception:
        # 意外异常：不裸 500，返回 200 fallback 空（诚实降级），并记录日志
        logger.exception("bandit: recommend failed, degraded to fallback")
        return {
            "mode": "fallback",
            "student_id": student_id,
            "subject": subject,
            "reason": "推荐服务异常，请稍后重试",
            "items": [],
        }
    return result


@router.post("/wrong-questions/click")
def record_wrong_question_click(
    payload: ClickRewardRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """上报一次点击/答题反馈：clicks +1、reward_sum 累加、更新 LinUCB b 向量。

    reward 由调用方判定正确性后回传（0=答错 / 1=答对）；
    生产建议后续改为服务端从 response_logs 判定正确性（预留演化路径）。

    record_click_reward 内部 best-effort（写失败仅告警，不抛异常），
    本端点不额外吞异常：数据库层错误由 get_db 统一处理。
    """
    _guard_enabled()
    student = db.query(Student).filter(Student.id == payload.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    _assert_class_access(db, user_id, student.class_id)

    record_click_reward(
        db=db,
        student_id=payload.student_id,
        subject=payload.subject,
        kp_name=payload.kp_name,
        reward=payload.reward,
    )
    return {"success": True, "clicked": True, "reward": payload.reward}


# ── 客户清单#2：批改后自动配套练习 / 高频错题举一反三 ──────────────
# （独立端点块，不改动上方 bandit 推荐逻辑；读 JSON + 手动 force 重跑）


class AutoVariantsGenerateRequest(BaseModel):
    """手动兜底重跑 body。folder=批改场次 folder_safe（cls_{class_id}__{exam_name}）。

    source："ai"=全部 LLM 生成（types/topics 给出题偏好）| "bank"=题库变式题。
    """

    folder: str
    force: bool = True
    source: Optional[str] = None
    types: Optional[list] = None
    topics: Optional[list] = None


def _assert_folder_class_access(db: Session, user_id: str, folder: str) -> str:
    """从 folder_safe 解析 class_id 并校验班级权限；非班级文件夹返回空串（不做班级鉴权）。"""
    from app.services.auto_class_sync import parse_class_folder

    parsed = parse_class_folder(folder)
    if not parsed:
        return ""
    class_id, _exam = parsed
    _assert_class_access(db, user_id, class_id)
    return class_id


@router.get("/auto-variants")
def get_auto_variants(
    folder: str = Query(..., description="批改场次 folder_safe，如 cls_{class_id}__{exam_name}"),
    user_id: str = Depends(bind_grading_user_context),
    db: Session = Depends(get_db),
):
    """读该场自动配套练习（已生成 JSON）；未生成返回 status=none，不触发生成。"""
    from app.services.auto_variant import read_auto_variants_for_api

    if not (folder or "").strip():
        raise HTTPException(status_code=400, detail="folder 不能为空")
    _assert_folder_class_access(db, user_id, folder.strip())
    return read_auto_variants_for_api(folder.strip())


@router.post("/auto-variants/generate")
def generate_auto_variants(
    payload: AutoVariantsGenerateRequest,
    user_id: str = Depends(bind_grading_user_context),
    db: Session = Depends(get_db),
):
    """手动兜底：force 重跑一场配套练习（幂等键=auto_variants/{folder}.json）。

    source=bank 且未配置题库 → 503（没接题库的诚实报错）；source=ai → 全部 LLM 生成。
    """
    from app.services.auto_variant import (
        auto_generate_variants_after_grading,
        read_auto_variants_for_api,
    )

    folder = (payload.folder or "").strip()
    if not folder:
        raise HTTPException(status_code=400, detail="folder 不能为空")
    _assert_folder_class_access(db, user_id, folder)

    src = (payload.source or "").strip().lower()
    if src == "bank":
        _guard_enabled()
    # 单场单飞已在服务层；此处同步生成（老师点了按钮，给明确结果）
    summary = auto_generate_variants_after_grading(
        user_id,
        folder,
        force=bool(payload.force),
        source=src or None,
        types=[str(t) for t in (payload.types or []) if str(t).strip()] or None,
        topics=[str(t) for t in (payload.topics or []) if str(t).strip()] or None,
    )
    result = read_auto_variants_for_api(folder)
    result["summary"] = summary
    return result
