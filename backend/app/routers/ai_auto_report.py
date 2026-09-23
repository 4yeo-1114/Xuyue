# -*- coding: utf-8 -*-
"""AI 助教自动分析报告 API（与 ai_chat 对话分离，共用前端 FloatingChat 展示）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.services.ai_auto_report.generator import stream_auto_report
from app.services.ai_auto_report.store import get_report, list_pending, mark_consumed
from app.services.audit.access_log import log_access, resolve_user_role

router = APIRouter(
    prefix="/ai-chat/auto-reports",
    tags=["ai_auto_report"],
    dependencies=[Depends(bind_grading_user_context)],
)


@router.get("/pending")
def api_list_pending_auto_reports(user_id: str = Depends(get_current_user_id)):
    return {"ok": True, "reports": list_pending(user_id)}


@router.post("/{report_id}/consume")
def api_consume_auto_report(report_id: str, user_id: str = Depends(get_current_user_id)):
    if not mark_consumed(report_id, user_id):
        raise HTTPException(status_code=404, detail="报告不存在或已处理")
    return {"ok": True}


@router.post("/{report_id}/stream")
def api_stream_auto_report(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    report = get_report(report_id, user_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在或已过期")
    if report.get("status") != "pending":
        raise HTTPException(status_code=409, detail="报告已处理")

    payload = report.get("payload") or {}
    # E03/E14：AI auto-report 拉取留痕（写失败不阻断）
    try:
        class_meta = payload.get("class") or {}
        role = resolve_user_role(db, user_id)
        log_access(
            db,
            user_id=user_id,
            user_role=role,
            action="ai_report",
            target_type="class",
            target_id=str(class_meta.get("class_id") or ""),
            detail={"report_type": payload.get("report_kind"), "title": report.get("title")},
        )
    except Exception:  # noqa: BLE001
        pass
    return StreamingResponse(
        stream_auto_report(db, payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
