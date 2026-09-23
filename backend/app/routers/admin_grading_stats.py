from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.grading.grading_stats import query_grading_stats
from app.routers.admin import _check_admin_permission
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/admin", tags=["admin_grading_stats"])


@router.get("/grading-stats", response_model=ApiResponse[dict])
def get_grading_stats(
    start_date: date = Query(..., description="开始日期 YYYY-MM-DD"),
    end_date: date = Query(..., description="结束日期 YYYY-MM-DD"),
    user_id: Optional[str] = Query(None, description="选中的教师 user_id"),
    db: Session = Depends(get_db),
    admin_id: str = Depends(get_current_user_id),
):
    _check_admin_permission(db, admin_id)
    if not user_id:
        raise HTTPException(status_code=400, detail="请选择要查看的教师")
    data = query_grading_stats(db, start_date, end_date, user_id=user_id)
    return ApiResponse(data=data)
