from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.prep_plan import PrepPlan
from app.schemas.prep_plans import PrepPlanCreate, PrepPlanUpdate, PrepPlanResponse
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/prep-plans", tags=["prep_plans"])

@router.get("", response_model=ApiResponse[List[PrepPlanResponse]])
def list_prep_plans(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    query = db.query(PrepPlan).filter(PrepPlan.user_id == user_id)
    if start_date:
        query = query.filter(PrepPlan.date >= start_date)
    if end_date:
        query = query.filter(PrepPlan.date <= end_date)
    
    items = query.order_by(PrepPlan.date.asc(), PrepPlan.created_at.asc()).all()
    return ApiResponse(data=items)

@router.post("", response_model=ApiResponse[PrepPlanResponse])
def create_prep_plan(
    item: PrepPlanCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    db_item = PrepPlan(
        user_id=user_id,
        date=item.date,
        subject=item.subject,
        content=item.content,
        completed=item.completed,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return ApiResponse(data=db_item)

@router.patch("/{plan_id}", response_model=ApiResponse[PrepPlanResponse])
def update_prep_plan(
    plan_id: str,
    item: PrepPlanUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    db_item = db.query(PrepPlan).filter(PrepPlan.id == plan_id, PrepPlan.user_id == user_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="备课计划不存在或无权访问")
    
    update_data = item.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)
        
    db.commit()
    db.refresh(db_item)
    return ApiResponse(data=db_item)

@router.delete("/{plan_id}", response_model=ApiResponse[dict])
def delete_prep_plan(
    plan_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    db_item = db.query(PrepPlan).filter(PrepPlan.id == plan_id, PrepPlan.user_id == user_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="备课计划不存在或无权访问")
    
    db.delete(db_item)
    db.commit()
    return ApiResponse(data={"ok": True})
