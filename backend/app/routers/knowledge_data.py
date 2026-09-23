"""知识点/单元 CRUD：学科配置页数据源，演示数据在 MySQL（前端 useKnowledgeData 由直连 Supabase 迁移到本组接口）"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.knowledge_point import KnowledgePoint
from app.models.subject_unit import SubjectUnit
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/knowledge-data", tags=["knowledge-data"])


def _unit_to_record(u: SubjectUnit) -> dict:
    """SubjectUnit ORM → 前端 UnitRow 对齐字段。"""
    return {
        "id": u.id,
        "user_id": u.user_id,
        "subject": u.subject,
        "semester": u.semester,
        "unit_index": u.unit_index,
        "name": u.name,
        "subtitle": u.subtitle,
    }


def _kp_to_record(k: KnowledgePoint) -> dict:
    """KnowledgePoint ORM → 前端 KPRow 对齐字段（数组/JSON 列原样序列化，前端按 unit_id 自行组装）。"""
    return {
        "id": k.id,
        "user_id": k.user_id,
        "unit_id": k.unit_id,
        "code": k.code,
        "name": k.name,
        "level": k.level,
        "mastery": k.mastery,
        "is_weak": k.is_weak,
        "prerequisite": k.prerequisite,
        "postrequisite": k.postrequisite,
        "related": k.related,
        "hours": k.hours,
        "key_point": k.key_point,
        "difficulty": k.difficulty,
        "common_errors": k.common_errors,
        "resources": k.resources,
    }


class CreateKnowledgePointRequest(BaseModel):
    unit_id: str
    code: str
    name: str
    level: str = ""


class UpdateKnowledgePointRequest(BaseModel):
    unit_id: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    level: Optional[str] = None
    mastery: Optional[float] = None
    is_weak: Optional[bool] = None
    prerequisite: Optional[list] = None
    postrequisite: Optional[list] = None
    related: Optional[list] = None
    hours: Optional[int] = None
    key_point: Optional[str] = None
    difficulty: Optional[str] = None
    common_errors: Optional[str] = None
    resources: Optional[list] = None


class SeedKnowledgePointRow(BaseModel):
    code: str
    name: str
    level: str = ""
    mastery: float = 0
    is_weak: bool = False
    prerequisite: Optional[list] = None
    postrequisite: Optional[list] = None
    related: Optional[list] = None
    hours: int = 0
    key_point: Optional[str] = None
    difficulty: Optional[str] = None
    common_errors: Optional[str] = None
    resources: Optional[list] = None


class SeedUnitRow(BaseModel):
    unit_index: int
    name: str
    subtitle: Optional[str] = None
    knowledgePoints: List[SeedKnowledgePointRow]


class SeedKnowledgeDataRequest(BaseModel):
    subject: str
    semester: str
    units: List[SeedUnitRow]


def _get_own_unit(db: Session, unit_id: str, user_id: str) -> SubjectUnit:
    unit = (
        db.query(SubjectUnit)
        .filter(SubjectUnit.id == unit_id, SubjectUnit.user_id == user_id)
        .first()
    )
    if not unit:
        raise HTTPException(status_code=404, detail="单元不存在")
    return unit


@router.get("", response_model=ApiResponse[dict])
def list_knowledge_data(
    subject: str = Query(...),
    semester: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    units = (
        db.query(SubjectUnit)
        .filter(
            SubjectUnit.user_id == user_id,
            SubjectUnit.subject == subject,
            SubjectUnit.semester == semester,
        )
        .order_by(SubjectUnit.unit_index.asc())
        .all()
    )
    if not units:
        return ApiResponse(data={"units": [], "kps": [], "isEmpty": True})
    unit_ids = [u.id for u in units]
    kps = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.unit_id.in_(unit_ids))
        .order_by(KnowledgePoint.code.asc())
        .all()
    )
    return ApiResponse(
        data={
            "units": [_unit_to_record(u) for u in units],
            "kps": [_kp_to_record(k) for k in kps],
            "isEmpty": False,
        }
    )


@router.post("/knowledge-points", response_model=ApiResponse[dict])
def create_knowledge_point(
    body: CreateKnowledgePointRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _get_own_unit(db, body.unit_id, user_id)
    row = KnowledgePoint(
        user_id=user_id,
        unit_id=body.unit_id,
        code=(body.code or "").strip(),
        name=(body.name or "").strip(),
        level=(body.level or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_kp_to_record(row))


@router.patch("/knowledge-points/{kp_id}", response_model=ApiResponse[dict])
def update_knowledge_point(
    kp_id: str,
    body: UpdateKnowledgePointRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.id == kp_id, KnowledgePoint.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="知识点不存在")
    if body.unit_id is not None:
        _get_own_unit(db, body.unit_id, user_id)
        row.unit_id = body.unit_id
    if body.code is not None:
        row.code = (body.code or "").strip()
    if body.name is not None:
        row.name = (body.name or "").strip()
    if body.level is not None:
        row.level = (body.level or "").strip() or None
    if body.mastery is not None:
        row.mastery = body.mastery
    if body.is_weak is not None:
        row.is_weak = body.is_weak
    if body.prerequisite is not None:
        row.prerequisite = body.prerequisite
    if body.postrequisite is not None:
        row.postrequisite = body.postrequisite
    if body.related is not None:
        row.related = body.related
    if body.hours is not None:
        row.hours = body.hours
    if body.key_point is not None:
        row.key_point = (body.key_point or "").strip() or None
    if body.difficulty is not None:
        row.difficulty = (body.difficulty or "").strip() or None
    if body.common_errors is not None:
        row.common_errors = (body.common_errors or "").strip() or None
    if body.resources is not None:
        row.resources = body.resources
    db.commit()
    db.refresh(row)
    return ApiResponse(data=_kp_to_record(row))


@router.delete("/knowledge-points/{kp_id}", response_model=ApiResponse[dict])
def delete_knowledge_point(
    kp_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    row = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.id == kp_id, KnowledgePoint.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="知识点不存在")
    db.delete(row)
    db.commit()
    return ApiResponse(data={"ok": True})


@router.post("/seed", response_model=ApiResponse[dict])
def seed_knowledge_data(
    body: SeedKnowledgeDataRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    subject = (body.subject or "").strip()
    semester = (body.semester or "").strip()
    unit_records = []
    kp_records = []
    try:
        for u in body.units:
            unit = SubjectUnit(
                user_id=user_id,
                subject=subject,
                semester=semester,
                unit_index=u.unit_index,
                name=(u.name or "").strip(),
                subtitle=(u.subtitle or "").strip() or None,
            )
            db.add(unit)
            db.flush()  # 拿到新 unit id，供 kp.unit_id 引用
            unit_records.append(_unit_to_record(unit))
            for kp in u.knowledgePoints:
                krow = KnowledgePoint(
                    user_id=user_id,
                    unit_id=unit.id,
                    code=(kp.code or "").strip(),
                    name=(kp.name or "").strip(),
                    level=(kp.level or "").strip() or None,
                    mastery=kp.mastery,
                    is_weak=kp.is_weak,
                    prerequisite=kp.prerequisite,
                    postrequisite=kp.postrequisite,
                    related=kp.related,
                    hours=kp.hours,
                    key_point=(kp.key_point or "").strip() or None,
                    difficulty=(kp.difficulty or "").strip() or None,
                    common_errors=(kp.common_errors or "").strip() or None,
                    resources=kp.resources,
                )
                db.add(krow)
                kp_records.append(_kp_to_record(krow))
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="初始化知识点失败，请检查数据后重试")
    return ApiResponse(data={"units": unit_records, "kps": kp_records})
