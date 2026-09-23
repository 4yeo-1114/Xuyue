"""食堂电子台账 API：GET/POST /canteen/records。

防篡改设计 = 只增不改（不提供更新/删除）。按 type 分类（晨检/留样/陪餐/消毒/菜单），
宽松 schema：公共字段 type + date 必填，各类型专属字段按白名单写入、忽略未知字段。
"""
from datetime import timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.canteen_record import CanteenRecord
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/canteen", tags=["canteen"])

VALID_TYPES = {"health_check", "sample", "accompany", "disinfection", "menu"}

# 各类型可写字段白名单（防篡改：只落库这些字段）
FIELDS_BY_TYPE = {
    "health_check": ["staff_name", "temperature", "health_status", "pass"],
    "sample": ["meal_type", "dish_name", "sample_qty", "sampler_name", "storage_temp", "review_result"],
    "accompany": ["meal_type", "person_name", "person_role", "comments"],
    "disinfection": ["area", "method", "operator_name", "result"],
    "menu": ["meal_type", "dishes", "nutrition_note"],
}

# 各类型除 date 外的必填字段（与前端 required 标记一致）
REQUIRED_BY_TYPE = {
    "health_check": ["staff_name"],
    "sample": ["meal_type", "dish_name"],
    "accompany": ["meal_type", "person_name"],
    "disinfection": ["area"],
    "menu": ["meal_type", "dishes"],
}


def _iso(dt) -> Optional[str]:
    if not dt:
        return None
    try:
        d = dt
        if getattr(d, "tzinfo", None) is not None:
            d = d.astimezone(timezone.utc).replace(tzinfo=None)
        return d.isoformat(timespec="seconds")
    except Exception:
        return str(dt)


def _to_item(r: CanteenRecord) -> dict:
    return {
        "id": r.id,
        "type": r.type,
        "date": r.date,
        "occurred_at": _iso(r.occurred_at),
        "created_by": r.created_by,
        "staff_name": r.staff_name,
        "temperature": r.temperature,
        "health_status": r.health_status,
        "pass": r.pass_,
        "meal_type": r.meal_type,
        "dish_name": r.dish_name,
        "sample_qty": r.sample_qty,
        "sampler_name": r.sampler_name,
        "storage_temp": r.storage_temp,
        "review_result": r.review_result,
        "person_name": r.person_name,
        "person_role": r.person_role,
        "comments": r.comments,
        "area": r.area,
        "method": r.method,
        "operator_name": r.operator_name,
        "result": r.result,
        "dishes": r.dishes,
        "nutrition_note": r.nutrition_note,
    }


@router.get("/records", response_model=ApiResponse[dict])
def list_records(
    type: str = Query(..., description="台账类型"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rtype = (type or "").strip()
    if rtype not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"未知台账类型: {rtype}")

    q = db.query(CanteenRecord).filter(CanteenRecord.type == rtype)
    total = q.count()
    rows = (
        q.order_by(desc(CanteenRecord.occurred_at), desc(CanteenRecord.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ApiResponse(
        data={
            "type": rtype,
            "items": [_to_item(r) for r in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/records", response_model=ApiResponse[dict])
def create_record(
    body: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rtype = str(body.get("type") or "").strip()
    if rtype not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"未知台账类型: {rtype}")
    date = str(body.get("date") or "").strip()
    if not date:
        raise HTTPException(status_code=400, detail="请填写记录日期")

    for key in REQUIRED_BY_TYPE[rtype]:
        v = body.get(key)
        if v is None or str(v).strip() == "":
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {key}")

    rec = CanteenRecord(type=rtype, date=date, created_by=user_id)
    for key in FIELDS_BY_TYPE[rtype]:
        if key in body and body[key] is not None:
            attr = "pass_" if key == "pass" else key
            setattr(rec, attr, body[key])

    db.add(rec)
    db.commit()
    db.refresh(rec)
    return ApiResponse(data=_to_item(rec))
