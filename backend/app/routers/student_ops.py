"""学生端运营域（C 域）路由：争章/学分银行/兑换/校外实践/校园生活/图片佐证。

前缀 /student-ops，挂载后为 /api/v1/student-ops。
契约：docs/contracts/12-student-ops-contract.md（C0）+ 99-reconciliation.md（画像字段）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import asc, desc, func as sa_func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.grading.file_auth import user_id_from_request
from app.models.badge_award import BadgeAward
from app.models.badge_definition import BadgeDefinition
from app.models.book_borrow import BookBorrow
from app.models.campus_club import CampusClub
from app.models.class_model import Class
from app.models.club_attendance import ClubAttendance
from app.models.club_enrollment import ClubEnrollment
from app.models.credit_account import CreditAccount
from app.models.credit_transaction import CreditTransaction
from app.models.health_check import HealthCheck
from app.models.attendance_record import AttendanceRecord
from app.models.practice_record import PracticeRecord
from app.models.reading_record import ReadingRecord
from app.models.redemption_record import RedemptionRecord
from app.models.reward_product import RewardProduct
from app.models.student import Student
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.student_ops.requests import (
    AttendanceBatchCreate,
    BadgeAwardRequest,
    BadgeDefinitionCreate,
    BadgeDefinitionUpdate,
    ManualCreditRequest,
    PracticeCreate,
    PracticeReview,
    PracticeUpdate,
    RedemptionCreate,
    RedemptionStatusUpdate,
    RewardProductCreate,
    RewardProductUpdate,
)
from app.services.ai_chat_access import get_accessible_class_ids
from app.services.student_ops.access import (
    can_manage_badge_definitions,
    can_manage_class_ops,
    can_manage_clubs,
    can_manage_products,
    can_review_practice,
    can_review_redemption,
    is_global_admin,
)
from app.utils.class_access import can_view_class
from app.services.student_ops.config import (
    BATCH_AWARD_LIMIT,
    CLUB_FULL_ATTENDANCE_POINTS,
    DEFAULT_PAGE_SIZE,
    EVIDENCE_MAX_IMAGES,
    HEALTH_ALERT_POINTS,
    MAX_PAGE_SIZE,
    PRACTICE_REWARD_POINTS,
    READING_TOP10_POINTS,
)
from app.services.student_ops.credits import (
    apply_credit_to_account,
    apply_credit_change,
    get_locked_account,
    reconcile_account,
)
from app.services.student_ops.growth import (
    delete_growth_records,
    growth_record_exists,
    write_growth_record,
)
from app.services.student_ops.upload import resolve_evidence_file, save_evidence_image
from app.utils.security import build_download_url

router = APIRouter(prefix="/student-ops", tags=["student-ops"])


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

class _DomainFailure(Exception):
    """批量处理中单条失败（带错误码）。"""

    def __init__(self, reason: str):
        self.reason = reason


_PRACTICE_TYPE_LABELS = {
    "housework": "家务劳动",
    "volunteer": "志愿服务",
    "talent": "校外才艺",
    "study_tour": "研学活动",
}

# 实践审核通过 → 画像维度映射（volunteer 同时归属德+劳）
_PRACTICE_GROWTH_DIMENSIONS = {
    "housework": ["labor"],
    "volunteer": ["moral", "labor"],
    "talent": ["aesthetic"],
    "study_tour": ["intellectual"],
}

# 实践审核通过 → 二级指标 code 映射（C 域自动加分归类到指标字典，见 docs/migrations/2026-08-12）
_PRACTICE_INDICATOR_CODES = {
    "housework": {"labor": "labor_practice"},
    "volunteer": {"moral": "moral_activity", "labor": "labor_practice"},
    "talent": {"aesthetic": "aesthetic_activity"},
    "study_tour": {"intellectual": "intellectual_analysis"},
}


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="validation_error: 日期格式应为 YYYY-MM-DD")


def _parse_bool(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return 1
    if v in ("0", "false", "no", "n", "off"):
        return 0
    return None


def _pagination(page: int, page_size: int) -> tuple[int, int]:
    page = page if page and page > 0 else 1
    page_size = page_size if page_size and page_size > 0 else DEFAULT_PAGE_SIZE
    page_size = min(page_size, MAX_PAGE_SIZE)
    return page, page_size


def _list_scope(db: Session, user_id: str) -> tuple[Optional[set[str]], Optional[set[str]]]:
    """列表端点可见范围（P0-1 越权收敛）。

    返回 (own_student_ids, visible_class_ids)：
    - (None, None) → 全校可见（系统管理员/子系统管理员/校级管理者/年级组长）
    - own_student_ids 非空 → 学生本人，仅可见自己的记录
    - 否则 visible_class_ids 为教师/班主任可访问班级集合（空集 = 不可见任何记录）
    """
    if is_global_admin(db, user_id):
        return None, None
    me = db.query(Student).filter(Student.user_id == user_id).first()
    if me:
        return {me.id}, {me.class_id}
    return None, set(get_accessible_class_ids(db, user_id))


def _can_return_borrow(db: Session, user_id: str, borrow: BookBorrow) -> bool:
    """还书权限：借书学生本人 / 该生所在班级教师（含班主任）/ 管理角色。"""
    if is_global_admin(db, user_id):
        return True
    me = db.query(Student).filter(Student.user_id == user_id).first()
    if me and me.id == borrow.student_id:
        return True
    return can_view_class(db, user_id, borrow.class_id)


def _term_range(today: date) -> tuple[date, str]:
    """学年学期划分：9 月起为上学期，2-8 月为下学期。"""
    if today.month >= 9:
        return date(today.year, 9, 1), f"{today.year}-{today.year + 1}-1"
    return date(today.year - 1, 9, 1), f"{today.year - 1}-{today.year}-2"


# ---------------------------------------------------------------------------
# 序列化器（camelCase，C0 §0.2）
# ---------------------------------------------------------------------------

def _badge_def_dict(b: BadgeDefinition) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "description": b.description,
        "badgeType": b.badge_type,
        "category": b.category,
        "iconUrl": b.icon_url,
        "pointsAwarded": b.points_awarded,
        "minGrade": b.min_grade,
        "maxGrade": b.max_grade,
        "isActive": bool(b.is_active),
        "sortOrder": b.sort_order,
        "createdAt": b.created_at.isoformat() if b.created_at else "",
    }


def _badge_award_dict(a: BadgeAward, student_name: Optional[str] = None,
                      badge_name: Optional[str] = None) -> dict:
    return {
        "id": a.id,
        "studentId": a.student_id,
        "studentName": student_name,
        "badgeDefinitionId": a.badge_definition_id,
        "badgeDefinitionName": badge_name,
        "classId": a.class_id,
        "awardedBy": a.awarded_by,
        "awardDate": a.award_date.isoformat() if a.award_date else "",
        "reason": a.reason,
        "creditTransactionId": a.credit_transaction_id,
        "createdAt": a.created_at.isoformat() if a.created_at else "",
    }


def _credit_account_dict(acc: CreditAccount, student_name: Optional[str] = None,
                         class_name: Optional[str] = None, class_id: Optional[str] = None) -> dict:
    return {
        "accountId": acc.id,
        "studentId": acc.student_id,
        "studentName": student_name,
        "classId": class_id,
        "className": class_name,
        "balance": acc.balance or 0,
        "totalEarned": acc.total_earned or 0,
        "totalSpent": acc.total_spent or 0,
        "updatedAt": acc.updated_at.isoformat() if acc.updated_at else "",
    }


def _credit_txn_dict(t: CreditTransaction, student_name: Optional[str] = None,
                     class_name: Optional[str] = None, operator_name: Optional[str] = None) -> dict:
    return {
        "id": t.id,
        "studentId": t.student_id,
        "studentName": student_name,
        "className": class_name,
        "amount": t.amount,
        "transactionType": t.transaction_type,
        "balanceAfter": t.balance_after,
        "sourceType": t.source_type,
        "sourceId": t.source_id,
        "description": t.description,
        "operatorName": operator_name,
        "createdAt": t.created_at.isoformat() if t.created_at else "",
    }


def _reward_product_dict(p: RewardProduct) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "imageUrl": p.image_url,
        "productType": p.product_type,
        "pointsRequired": p.points_required,
        "stock": p.stock,
        "stockWarning": p.stock_warning,
        "isActive": bool(p.is_active),
        "exchangeLimitPerStudent": p.exchange_limit_per_student,
        "sortOrder": p.sort_order,
        "createdAt": p.created_at.isoformat() if p.created_at else "",
    }


def _redemption_dict(r: RedemptionRecord, student_name: Optional[str] = None,
                     product_name: Optional[str] = None, balance_after: Optional[int] = None) -> dict:
    return {
        "id": r.id,
        "studentId": r.student_id,
        "studentName": student_name,
        "productId": r.product_id,
        "productName": product_name,
        "classId": r.class_id,
        "pointsSpent": r.points_spent,
        "status": r.status,
        "operatorId": r.operator_id,
        "approverId": r.approver_id,
        "approvedAt": r.approved_at.isoformat() if r.approved_at else "",
        "deliveredAt": r.delivered_at.isoformat() if r.delivered_at else "",
        "notes": r.notes,
        "creditTransactionId": r.credit_transaction_id,
        "balanceAfter": balance_after,
        "createdAt": r.created_at.isoformat() if r.created_at else "",
    }


def _practice_dict(p: PracticeRecord, student_name: Optional[str] = None) -> dict:
    return {
        "id": p.id,
        "studentId": p.student_id,
        "studentName": student_name,
        "classId": p.class_id,
        "practiceType": p.practice_type,
        "title": p.title,
        "description": p.description,
        "practiceDate": p.practice_date.isoformat() if p.practice_date else "",
        "durationHours": float(p.duration_hours) if p.duration_hours is not None else None,
        "location": p.location,
        "evidenceImages": p.evidence_images or [],
        "status": p.status,
        "reviewerId": p.reviewer_id,
        "reviewComment": p.review_comment,
        "reviewedAt": p.reviewed_at.isoformat() if p.reviewed_at else "",
        "creditTransactionId": p.credit_transaction_id,
        "recordedBy": p.recorded_by,
        "createdAt": p.created_at.isoformat() if p.created_at else "",
    }


def _club_dict(c: CampusClub, teacher_name: Optional[str] = None) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "teacherId": c.teacher_id,
        "teacherName": teacher_name,
        "maxMembers": c.max_members,
        "isActive": bool(c.is_active),
        "createdAt": c.created_at.isoformat() if c.created_at else "",
    }


def _enrollment_dict(e: ClubEnrollment, student_name: Optional[str] = None) -> dict:
    return {
        "id": e.id,
        "studentId": e.student_id,
        "studentName": student_name,
        "clubId": e.club_id,
        "classId": e.class_id,
        "status": e.status,
        "enrolledAt": e.enrolled_at.isoformat() if e.enrolled_at else "",
        "leftAt": e.left_at.isoformat() if e.left_at else "",
        "recordedBy": e.recorded_by,
        "createdAt": e.created_at.isoformat() if e.created_at else "",
    }


def _attendance_dict(a: ClubAttendance, student_name: Optional[str] = None) -> dict:
    return {
        "id": a.id,
        "studentId": a.student_id,
        "studentName": student_name,
        "clubId": a.club_id,
        "classId": a.class_id,
        "sessionDate": a.session_date.isoformat() if a.session_date else "",
        "attendStatus": a.attend_status,
        "remarks": a.remarks,
        "recordedBy": a.recorded_by,
        "createdAt": a.created_at.isoformat() if a.created_at else "",
    }


def _book_borrow_dict(b: BookBorrow, student_name: Optional[str] = None) -> dict:
    return {
        "id": b.id,
        "studentId": b.student_id,
        "studentName": student_name,
        "classId": b.class_id,
        "bookTitle": b.book_title,
        "bookIsbn": b.book_isbn,
        "bookAuthor": b.book_author,
        "borrowedAt": b.borrowed_at.isoformat() if b.borrowed_at else "",
        "dueAt": b.due_at.isoformat() if b.due_at else "",
        "returnedAt": b.returned_at.isoformat() if b.returned_at else "",
        "status": b.status,
        "recordedBy": b.recorded_by,
        "notes": b.notes,
        "createdAt": b.created_at.isoformat() if b.created_at else "",
    }


def _reading_dict(r: ReadingRecord, student_name: Optional[str] = None) -> dict:
    return {
        "id": r.id,
        "studentId": r.student_id,
        "studentName": student_name,
        "classId": r.class_id,
        "bookTitle": r.book_title,
        "pagesRead": r.pages_read,
        "readingMinutes": r.reading_minutes,
        "readingDate": r.reading_date.isoformat() if r.reading_date else "",
        "recordedBy": r.recorded_by,
        "createdAt": r.created_at.isoformat() if r.created_at else "",
    }


def _health_dict(h: HealthCheck, student_name: Optional[str] = None) -> dict:
    return {
        "id": h.id,
        "studentId": h.student_id,
        "studentName": student_name,
        "classId": h.class_id,
        "checkType": h.check_type,
        "checkDate": h.check_date.isoformat() if h.check_date else "",
        "temperature": float(h.temperature) if h.temperature is not None else None,
        "healthStatus": h.health_status,
        "symptoms": h.symptoms,
        "isAlert": bool(h.is_alert),
        "handledBy": h.handled_by,
        "handleNotes": h.handle_notes,
        "recordedBy": h.recorded_by,
        "createdAt": h.created_at.isoformat() if h.created_at else "",
    }


def _attendance_record_dict(a: AttendanceRecord, student_name: Optional[str] = None) -> dict:
    return {
        "id": a.id,
        "studentId": a.student_id,
        "studentName": student_name,
        "classId": a.class_id,
        "date": a.date.isoformat() if a.date else "",
        "checkType": a.check_type,
        "status": a.status,
        "reason": a.reason,
        "recordedBy": a.recorded_by,
        "createdAt": a.created_at.isoformat() if a.created_at else "",
    }


# ---------------------------------------------------------------------------
# 4.1 争章颁章
# ---------------------------------------------------------------------------

@router.get("/badge-definitions", response_model=ApiResponse)
def list_badge_definitions(
    badge_type: Optional[str] = Query(None, alias="badgeType"),
    category: Optional[str] = Query(None),
    is_active: Optional[str] = Query(None, alias="isActive"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    del user_id
    q = db.query(BadgeDefinition)
    if badge_type:
        q = q.filter(BadgeDefinition.badge_type == badge_type)
    if category:
        q = q.filter(BadgeDefinition.category == category)
    active = _parse_bool(is_active)
    if active is not None:
        q = q.filter(BadgeDefinition.is_active == active)
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(asc(BadgeDefinition.sort_order), desc(BadgeDefinition.created_at)) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return ApiResponse(data={
        "items": [_badge_def_dict(b) for b in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.post("/badge-definitions", response_model=ApiResponse)
def create_badge_definition(
    body: BadgeDefinitionCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_badge_definitions(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可管理章定义")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="validation_error: 章名称不能为空")
    if db.query(BadgeDefinition).filter(BadgeDefinition.name == name).first():
        raise HTTPException(status_code=400, detail="validation_error: 章定义名称已存在")
    if body.points_awarded < 1:
        raise HTTPException(status_code=400, detail="validation_error: pointsAwarded 必须 ≥ 1")
    b = BadgeDefinition(
        name=name,
        description=body.description,
        badge_type=body.badge_type,
        category=body.category,
        icon_url=body.icon_url,
        points_awarded=body.points_awarded,
        min_grade=body.min_grade,
        max_grade=body.max_grade,
        is_active=1 if body.is_active else 0,
        sort_order=body.sort_order,
        created_by=user_id,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return ApiResponse(data=_badge_def_dict(b))


@router.patch("/badge-definitions/{badge_id}", response_model=ApiResponse)
def update_badge_definition(
    badge_id: str,
    body: BadgeDefinitionUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_badge_definitions(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可管理章定义")
    b = db.query(BadgeDefinition).filter(BadgeDefinition.id == badge_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="not_found: 章定义不存在")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="validation_error: 章名称不能为空")
        dup = db.query(BadgeDefinition).filter(BadgeDefinition.name == name, BadgeDefinition.id != badge_id).first()
        if dup:
            raise HTTPException(status_code=400, detail="validation_error: 章定义名称已存在")
        b.name = name
    if body.description is not None:
        b.description = body.description
    if body.badge_type is not None:
        b.badge_type = body.badge_type
    if body.category is not None:
        b.category = body.category
    if body.icon_url is not None:
        b.icon_url = body.icon_url
    if body.points_awarded is not None:
        if body.points_awarded < 1:
            raise HTTPException(status_code=400, detail="validation_error: pointsAwarded 必须 ≥ 1")
        b.points_awarded = body.points_awarded
    if body.min_grade is not None:
        b.min_grade = body.min_grade
    if body.max_grade is not None:
        b.max_grade = body.max_grade
    if body.is_active is not None:
        b.is_active = 1 if body.is_active else 0
    if body.sort_order is not None:
        b.sort_order = body.sort_order
    db.commit()
    db.refresh(b)
    return ApiResponse(data=_badge_def_dict(b))


@router.delete("/badge-definitions/{badge_id}", response_model=ApiResponse)
def delete_badge_definition(
    badge_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_badge_definitions(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可管理章定义")
    b = db.query(BadgeDefinition).filter(BadgeDefinition.id == badge_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="not_found: 章定义不存在")
    b.is_active = 0  # 软删除（停用）
    db.commit()
    return ApiResponse(data={"id": b.id, "isActive": False})


def _award_single(
    db: Session,
    student: Student,
    badge: BadgeDefinition,
    award_date: date,
    reason: Optional[str],
    operator_id: str,
    allowed_class_ids: set,
) -> dict:
    """颁章给单个学生（调用方需在 savepoint 内）。失败抛 _DomainFailure。"""
    if student.class_id not in allowed_class_ids:
        raise _DomainFailure("no_permission")
    existing = db.query(BadgeAward).filter(
        BadgeAward.student_id == student.id,
        BadgeAward.badge_definition_id == badge.id,
        BadgeAward.award_date == award_date,
    ).first()
    if existing:
        raise _DomainFailure("duplicate_entry")
    award = BadgeAward(
        student_id=student.id,
        badge_definition_id=badge.id,
        class_id=student.class_id,
        awarded_by=operator_id,
        award_date=award_date,
        reason=reason,
    )
    db.add(award)
    db.flush()
    _, txn = apply_credit_change(
        db, student.id, student.class_id, badge.points_awarded,
        "badge_award", operator_id, f"获得【{badge.name}】",
        source_type="badge_definition", source_id=badge.id,
    )
    award.credit_transaction_id = txn.id
    write_growth_record(
        db, student.id, student.class_id, badge.category,
        "badge_award", award.id, badge.points_awarded,
        note=f"获得【{badge.name}】", created_by=operator_id, occurred_at=award_date,
    )
    return {
        "id": award.id,
        "studentId": student.id,
        "studentName": student.name,
        "badgeDefinitionName": badge.name,
        "pointsEarned": badge.points_awarded,
        "awardDate": award_date.isoformat(),
    }


@router.post("/badge-awards", response_model=ApiResponse)
def award_badges(
    body: BadgeAwardRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    badge = db.query(BadgeDefinition).filter(BadgeDefinition.id == body.badge_definition_id).first()
    if not badge:
        raise HTTPException(status_code=404, detail="not_found: 章定义不存在")
    if not badge.is_active:
        raise HTTPException(status_code=400, detail="validation_error: 章定义已停用")
    award_date = _parse_date(body.award_date)
    if not award_date:
        raise HTTPException(status_code=400, detail="validation_error: 请提供 awardDate")
    if not body.student_ids:
        raise HTTPException(status_code=400, detail="validation_error: studentIds 不能为空")
    if len(body.student_ids) > BATCH_AWARD_LIMIT:
        raise HTTPException(status_code=400, detail=f"validation_error: 批量颁章每批最多 {BATCH_AWARD_LIMIT} 人")
    if len(set(body.student_ids)) != len(body.student_ids):
        raise HTTPException(status_code=400, detail="validation_error: studentIds 存在重复")

    students_map = {s.id: s for s in db.query(Student).filter(Student.id.in_(body.student_ids)).all()}
    allowed_class_ids = {
        cid for cid in {s.class_id for s in students_map.values()}
        if can_manage_class_ops(db, user_id, cid)
    }

    failures: list[dict] = []
    awards: list[dict] = []
    success_count = 0
    for sid in body.student_ids:
        student = students_map.get(sid)
        if student is None:
            failures.append({"studentId": sid, "studentName": "", "reason": "student_not_found"})
            continue
        try:
            with db.begin_nested():
                awards.append(_award_single(db, student, badge, award_date, body.reason, user_id, allowed_class_ids))
                success_count += 1
        except _DomainFailure as e:
            failures.append({"studentId": sid, "studentName": student.name, "reason": e.reason})
        except IntegrityError:
            failures.append({"studentId": sid, "studentName": student.name, "reason": "duplicate_entry"})
    db.commit()
    return ApiResponse(data={
        "successCount": success_count,
        "failCount": len(failures),
        "failures": failures,
        "awards": awards,
    })


@router.get("/badge-awards", response_model=ApiResponse)
def list_badge_awards(
    class_id: Optional[str] = Query(None, alias="classId"),
    student_id: Optional[str] = Query(None, alias="studentId"),
    badge_definition_id: Optional[str] = Query(None, alias="badgeDefinitionId"),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(BadgeAward)
    if class_id:
        if not can_view_class(db, user_id, class_id):
            raise HTTPException(status_code=403, detail="forbidden: 无该班级查看权限")
        q = q.filter(BadgeAward.class_id == class_id)
    if student_id:
        q = q.filter(BadgeAward.student_id == student_id)
    if badge_definition_id:
        q = q.filter(BadgeAward.badge_definition_id == badge_definition_id)
    d1, d2 = _parse_date(start_date), _parse_date(end_date)
    if d1:
        q = q.filter(BadgeAward.award_date >= d1)
    if d2:
        q = q.filter(BadgeAward.award_date <= d2)
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(BadgeAward.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(BadgeAward.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(BadgeAward.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {a.student_id for a in rows}
    def_ids = {a.badge_definition_id for a in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    badges = {b.id: b.name for b in db.query(BadgeDefinition).filter(BadgeDefinition.id.in_(def_ids)).all()} if def_ids else {}
    return ApiResponse(data={
        "items": [_badge_award_dict(a, names.get(a.student_id), badges.get(a.badge_definition_id)) for a in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.delete("/badge-awards/{award_id}", response_model=ApiResponse)
def revoke_badge_award(
    award_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    award = db.query(BadgeAward).filter(BadgeAward.id == award_id).first()
    if not award:
        raise HTTPException(status_code=404, detail="not_found: 颁章记录不存在")
    if not (is_global_admin(db, user_id) or award.awarded_by == user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅管理员或颁发人本人可撤销")

    rollback_failed = False
    if award.credit_transaction_id:
        txn = db.query(CreditTransaction).filter(CreditTransaction.id == award.credit_transaction_id).first()
        points = txn.amount if txn else 0
        if points > 0:
            account = get_locked_account(db, award.student_id)
            if (account.balance or 0) >= points:
                apply_credit_to_account(
                    db, account, award.class_id, -points, "adjustment", user_id,
                    description=f"撤销颁章退分, 原颁章ID={award.id}",
                    source_type="badge_award", source_id=award.id,
                )
            else:
                # 积分已被后续变动消耗，无法安全回滚：仅删除颁章记录，不退分
                rollback_failed = True
        delete_growth_records(db, "badge_award", award.id)
    db.delete(award)
    db.commit()
    if rollback_failed:
        raise HTTPException(
            status_code=409,
            detail="credit_rollback_failed: 积分已后续变动，已删除颁章记录，未退分，需人工处理",
        )
    return ApiResponse(data={"id": award.id, "deleted": True})


# ---------------------------------------------------------------------------
# 4.2 学分银行
# ---------------------------------------------------------------------------

@router.get("/credit-accounts", response_model=ApiResponse)
def list_credit_accounts(
    class_id: Optional[str] = Query(None, alias="classId"),
    sort_by: str = Query("balance_desc", alias="sortBy"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(CreditAccount, Student.class_id).join(Student, Student.id == CreditAccount.student_id)
    if class_id:
        if not can_manage_class_ops(db, user_id, class_id) and not is_global_admin(db, user_id):
            raise HTTPException(status_code=403, detail="forbidden: 无该班级查看权限")
        q = q.filter(Student.class_id == class_id)
    elif not is_global_admin(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 教师必须指定班级")
    if sort_by == "balance_asc":
        q = q.order_by(asc(CreditAccount.balance))
    elif sort_by == "total_earned_desc":
        q = q.order_by(desc(CreditAccount.total_earned))
    else:
        q = q.order_by(desc(CreditAccount.balance))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    student_ids = [acc.student_id for acc, _ in rows]
    class_ids = {cid for _, cid in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    class_names = {c.id: f"{c.grade}{c.name}" for c in db.query(Class).filter(Class.id.in_(class_ids)).all()} if class_ids else {}
    return ApiResponse(data={
        "items": [
            _credit_account_dict(acc, names.get(acc.student_id), class_names.get(cid), cid)
            for acc, cid in rows
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.get("/credit-transactions", response_model=ApiResponse)
def list_credit_transactions(
    student_id: Optional[str] = Query(None, alias="studentId"),
    class_id: Optional[str] = Query(None, alias="classId"),
    transaction_type: Optional[str] = Query(None, alias="transactionType"),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(CreditTransaction)
    if class_id:
        q = q.filter(CreditTransaction.class_id == class_id)
    if student_id:
        q = q.filter(CreditTransaction.student_id == student_id)
    if transaction_type:
        q = q.filter(CreditTransaction.transaction_type == transaction_type)
    if start_date:
        q = q.filter(CreditTransaction.created_at >= _parse_date(start_date))
    if end_date:
        q = q.filter(CreditTransaction.created_at < _parse_date(end_date) + timedelta(days=1))
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(CreditTransaction.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(CreditTransaction.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(CreditTransaction.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {t.student_id for t in rows}
    class_ids = {t.class_id for t in rows}
    operator_ids = {t.operator_id for t in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    class_names = {c.id: f"{c.grade}{c.name}" for c in db.query(Class).filter(Class.id.in_(class_ids)).all()} if class_ids else {}
    op_names = {u.id: u.display_name for u in db.query(User).filter(User.id.in_(operator_ids)).all()} if operator_ids else {}
    return ApiResponse(data={
        "items": [
            _credit_txn_dict(t, names.get(t.student_id), class_names.get(t.class_id), op_names.get(t.operator_id))
            for t in rows
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.post("/credit-transactions/manual", response_model=ApiResponse)
def manual_credit(
    body: ManualCreditRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.id == body.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="not_found: 学生不存在")
    if not can_manage_class_ops(db, user_id, student.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该学生班级管理权限")
    if body.amount == 0:
        raise HTTPException(status_code=400, detail="validation_error: amount 不能为 0")
    if not (body.description or "").strip():
        raise HTTPException(status_code=400, detail="validation_error: description 必填")
    txn_type = "manual_add" if body.amount > 0 else "manual_deduct"
    account, txn = apply_credit_change(
        db, student.id, student.class_id, body.amount, txn_type, user_id,
        description=body.description, source_type="manual",
    )
    db.commit()
    return ApiResponse(data={
        "id": txn.id,
        "studentId": student.id,
        "amount": txn.amount,
        "transactionType": txn.transaction_type,
        "balanceAfter": txn.balance_after,
        "balance": account.balance,
        "description": txn.description,
        "createdAt": txn.created_at.isoformat() if txn.created_at else "",
    })


@router.get("/credit-report", response_model=ApiResponse)
def credit_report(
    class_id: Optional[str] = Query(None, alias="classId"),
    grade: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    group_by: str = Query("class", alias="groupBy"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not is_global_admin(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 报表仅管理员/校级管理者可查看")
    acct_q = db.query(CreditAccount).join(Student, Student.id == CreditAccount.student_id)
    if class_id:
        acct_q = acct_q.filter(Student.class_id == class_id)
    if grade:
        acct_q = acct_q.join(Class, Class.id == Student.class_id).filter(Class.grade == grade)

    total_students = acct_q.count()
    total_balance = acct_q.with_entities(sa_func.coalesce(sa_func.sum(CreditAccount.balance), 0)).scalar() or 0
    avg_balance = round(total_balance / total_students, 2) if total_students else 0

    txn_q = db.query(CreditTransaction)
    if class_id:
        txn_q = txn_q.filter(CreditTransaction.class_id == class_id)
    if grade:
        txn_q = txn_q.join(Class, Class.id == CreditTransaction.class_id).filter(Class.grade == grade)
    if start_date:
        txn_q = txn_q.filter(CreditTransaction.created_at >= _parse_date(start_date))
    if end_date:
        txn_q = txn_q.filter(CreditTransaction.created_at < _parse_date(end_date) + timedelta(days=1))
    earned = txn_q.with_entities(
        sa_func.coalesce(sa_func.sum(CreditTransaction.amount), 0)
    ).filter(CreditTransaction.amount > 0).scalar() or 0
    spent = txn_q.with_entities(
        sa_func.coalesce(sa_func.sum(CreditTransaction.amount), 0)
    ).filter(CreditTransaction.amount < 0).scalar() or 0

    by_class = []
    if group_by in ("class", "grade"):
        rows = (
            db.query(
                Student.class_id,
                sa_func.count(sa_func.distinct(CreditAccount.student_id)),
                sa_func.coalesce(sa_func.sum(CreditAccount.balance), 0),
            )
            .join(CreditAccount, CreditAccount.student_id == Student.id)
        )
        if class_id:
            rows = rows.filter(Student.class_id == class_id)
        if grade:
            rows = rows.join(Class, Class.id == Student.class_id).filter(Class.grade == grade)
        rows = rows.group_by(Student.class_id).all()
        class_names = {c.id: f"{c.grade}{c.name}" for c in db.query(Class).filter(Class.id.in_([r[0] for r in rows])).all()}
        by_class = [
            {"classId": r[0], "className": class_names.get(r[0], ""), "studentCount": r[1],
             "totalBalance": int(r[2]), "avgBalance": round(int(r[2]) / r[1], 2) if r[1] else 0}
            for r in rows
        ]

    by_type = []
    if group_by == "transaction_type":
        txn_rows = (
            db.query(
                CreditTransaction.transaction_type,
                sa_func.count(CreditTransaction.id),
                sa_func.coalesce(sa_func.sum(CreditTransaction.amount), 0),
            )
        )
        if class_id:
            txn_rows = txn_rows.filter(CreditTransaction.class_id == class_id)
        if grade:
            txn_rows = txn_rows.join(Class, Class.id == CreditTransaction.class_id).filter(Class.grade == grade)
        if start_date:
            txn_rows = txn_rows.filter(CreditTransaction.created_at >= _parse_date(start_date))
        if end_date:
            txn_rows = txn_rows.filter(CreditTransaction.created_at < _parse_date(end_date) + timedelta(days=1))
        txn_rows = txn_rows.group_by(CreditTransaction.transaction_type).all()
        by_type = [
            {"type": r[0], "totalAmount": int(r[2]), "count": r[1]}
            for r in txn_rows
        ]

    return ApiResponse(data={
        "summary": {
            "totalStudents": total_students,
            "totalBalance": int(total_balance),
            "avgBalance": avg_balance,
            "totalEarnedPeriod": int(earned),
            "totalSpentPeriod": int(abs(spent)),
        },
        "byClass": by_class,
        "byType": by_type,
    })


@router.get("/credit-reconciliation", response_model=ApiResponse)
def credit_reconciliation(
    student_id: Optional[str] = Query(None, alias="studentId"),
    class_id: Optional[str] = Query(None, alias="classId"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not is_global_admin(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 对账仅管理员可用")
    q = db.query(CreditAccount)
    if student_id:
        q = q.filter(CreditAccount.student_id == student_id)
    if class_id:
        q = q.join(Student, Student.id == CreditAccount.student_id).filter(Student.class_id == class_id)
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(CreditAccount.updated_at)).offset((page - 1) * page_size).limit(page_size).all()
    items = [reconcile_account(db, acc.student_id) for acc in rows]
    return ApiResponse(data={
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


# ---------------------------------------------------------------------------
# 4.3 兑换管理
# ---------------------------------------------------------------------------

@router.get("/reward-products", response_model=ApiResponse)
def list_reward_products(
    product_type: Optional[str] = Query(None, alias="productType"),
    is_active: Optional[str] = Query(None, alias="isActive"),
    keyword: Optional[str] = Query(None),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    del user_id
    q = db.query(RewardProduct)
    if product_type:
        q = q.filter(RewardProduct.product_type == product_type)
    active = _parse_bool(is_active)
    if active is not None:
        q = q.filter(RewardProduct.is_active == active)
    if keyword:
        q = q.filter(RewardProduct.name.like(f"%{keyword}%"))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(asc(RewardProduct.sort_order), desc(RewardProduct.created_at)) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return ApiResponse(data={
        "items": [_reward_product_dict(p) for p in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.get("/reward-products/stock-stats", response_model=ApiResponse)
def reward_product_stock_stats(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """激励终端·库存统计：各商品库存 + 低库存/缺货清单 + 近 12 周实物兑换消耗趋势。"""
    if not is_global_admin(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 库存报表仅管理员/校级管理者可查看")
    products = db.query(RewardProduct) \
        .order_by(asc(RewardProduct.sort_order), desc(RewardProduct.created_at)).all()
    items = []
    low_stock_items = []
    physical_count = 0
    total_stock = 0
    out_of_stock_count = 0
    for p in products:
        stock = p.stock or 0
        is_physical = p.product_type == "physical"
        low = is_physical and stock <= p.stock_warning
        item = {
            "id": p.id,
            "name": p.name,
            "productType": p.product_type,
            "stock": stock,
            "stockWarning": p.stock_warning,
            "pointsRequired": p.points_required,
            "isActive": bool(p.is_active),
            "lowStock": low,
            "outOfStock": is_physical and stock <= 0,
        }
        items.append(item)
        if is_physical:
            physical_count += 1
            total_stock += stock
            if low:
                low_stock_items.append(item)
            if stock <= 0:
                out_of_stock_count += 1

    # 库存趋势 = 近 12 周实物兑换消耗（按创建时间周聚合），供前端绘制趋势图
    trend_start = datetime.utcnow() - timedelta(days=12 * 7)
    redemptions = (
        db.query(RedemptionRecord)
        .join(RewardProduct, RewardProduct.id == RedemptionRecord.product_id)
        .filter(
            RedemptionRecord.status != "cancelled",
            RewardProduct.product_type == "physical",
            RedemptionRecord.created_at >= trend_start,
        )
        .all()
    )
    trend_map: dict[str, dict] = {}
    for r in redemptions:
        d = r.created_at.date() if r.created_at else date.today()
        week_start = d - timedelta(days=d.weekday())
        key = week_start.isoformat()
        bucket = trend_map.setdefault(key, {"period": key, "count": 0, "pointsSpent": 0})
        bucket["count"] += 1
        bucket["pointsSpent"] += r.points_spent or 0
    trend = sorted(trend_map.values(), key=lambda b: b["period"])

    return ApiResponse(data={
        "summary": {
            "totalProducts": len(items),
            "physicalProducts": physical_count,
            "lowStockCount": len(low_stock_items),
            "outOfStockCount": out_of_stock_count,
            "totalStock": total_stock,
        },
        "items": items,
        "lowStockItems": low_stock_items,
        "trend": trend,
    })


@router.post("/reward-products", response_model=ApiResponse)
def create_reward_product(
    body: RewardProductCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_products(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可管理商品库")
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="validation_error: 商品名称不能为空")
    if body.points_required < 1:
        raise HTTPException(status_code=400, detail="validation_error: pointsRequired 必须 ≥ 1")
    p = RewardProduct(
        name=body.name.strip(),
        description=body.description,
        image_url=body.image_url,
        product_type=body.product_type,
        points_required=body.points_required,
        stock=body.stock,
        stock_warning=body.stock_warning,
        is_active=1 if body.is_active else 0,
        exchange_limit_per_student=body.exchange_limit_per_student,
        sort_order=body.sort_order,
        created_by=user_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return ApiResponse(data=_reward_product_dict(p))


@router.patch("/reward-products/{product_id}", response_model=ApiResponse)
def update_reward_product(
    product_id: str,
    body: RewardProductUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_products(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可管理商品库")
    p = db.query(RewardProduct).filter(RewardProduct.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="not_found: 商品不存在")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="validation_error: 商品名称不能为空")
        p.name = name
    if body.description is not None:
        p.description = body.description
    if body.image_url is not None:
        p.image_url = body.image_url
    if body.product_type is not None:
        p.product_type = body.product_type
    if body.points_required is not None:
        if body.points_required < 1:
            raise HTTPException(status_code=400, detail="validation_error: pointsRequired 必须 ≥ 1")
        p.points_required = body.points_required
    if body.stock is not None:
        p.stock = max(0, body.stock)
    if body.stock_warning is not None:
        p.stock_warning = body.stock_warning
    if body.is_active is not None:
        p.is_active = 1 if body.is_active else 0
    if body.exchange_limit_per_student is not None:
        p.exchange_limit_per_student = body.exchange_limit_per_student
    if body.sort_order is not None:
        p.sort_order = body.sort_order
    db.commit()
    db.refresh(p)
    return ApiResponse(data=_reward_product_dict(p))


@router.delete("/reward-products/{product_id}", response_model=ApiResponse)
def delete_reward_product(
    product_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_products(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可管理商品库")
    p = db.query(RewardProduct).filter(RewardProduct.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="not_found: 商品不存在")
    p.is_active = 0  # 下架（软删除）
    db.commit()
    return ApiResponse(data={"id": p.id, "isActive": False})


@router.post("/redemptions", response_model=ApiResponse)
def create_redemption(
    body: RedemptionCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.id == body.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="not_found: 学生不存在")
    if not can_manage_class_ops(db, user_id, student.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该学生班级管理权限")

    # SELECT ... FOR UPDATE 先锁账户，再锁商品（固定顺序避免死锁）→ 防超卖
    account = get_locked_account(db, student.id)
    product = (
        db.query(RewardProduct)
        .filter(RewardProduct.id == body.product_id)
        .with_for_update()
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="not_found: 商品不存在")
    if not product.is_active:
        raise HTTPException(status_code=400, detail="validation_error: 商品已下架")

    if (account.balance or 0) < product.points_required:
        raise HTTPException(status_code=400, detail="insufficient_balance: 积分不足，无法兑换")
    if product.product_type == "physical" and (product.stock or 0) <= 0:
        raise HTTPException(status_code=400, detail="out_of_stock: 商品库存不足")
    if product.exchange_limit_per_student > 0:
        cnt = db.query(RedemptionRecord).filter(
            RedemptionRecord.student_id == student.id,
            RedemptionRecord.product_id == product.id,
            RedemptionRecord.status != "cancelled",
        ).count()
        if cnt >= product.exchange_limit_per_student:
            raise HTTPException(status_code=400, detail="limit_exceeded: 超过每学生兑换上限")

    redemption = RedemptionRecord(
        student_id=student.id,
        product_id=product.id,
        class_id=student.class_id,
        points_spent=product.points_required,
        status="pending",
        operator_id=user_id,
    )
    db.add(redemption)
    db.flush()

    txn = apply_credit_to_account(
        db, account, student.class_id, -product.points_required, "redemption", user_id,
        description=f"兑换【{product.name}】",
        source_type="reward_product", source_id=redemption.id,
    )
    if product.product_type == "physical":
        product.stock = max(0, (product.stock or 1) - 1)
    redemption.credit_transaction_id = txn.id
    db.commit()
    return ApiResponse(data=_redemption_dict(
        redemption, student.name, product.name, balance_after=txn.balance_after))


@router.get("/redemptions", response_model=ApiResponse)
def list_redemptions(
    class_id: Optional[str] = Query(None, alias="classId"),
    student_id: Optional[str] = Query(None, alias="studentId"),
    product_id: Optional[str] = Query(None, alias="productId"),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(RedemptionRecord)
    if class_id:
        q = q.filter(RedemptionRecord.class_id == class_id)
    if student_id:
        q = q.filter(RedemptionRecord.student_id == student_id)
    if product_id:
        q = q.filter(RedemptionRecord.product_id == product_id)
    if status:
        q = q.filter(RedemptionRecord.status == status)
    if start_date:
        q = q.filter(RedemptionRecord.created_at >= _parse_date(start_date))
    if end_date:
        q = q.filter(RedemptionRecord.created_at < _parse_date(end_date) + timedelta(days=1))
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(RedemptionRecord.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(RedemptionRecord.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(RedemptionRecord.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {r.student_id for r in rows}
    product_ids = {r.product_id for r in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    products = {p.id: p.name for p in db.query(RewardProduct).filter(RewardProduct.id.in_(product_ids)).all()} if product_ids else {}
    return ApiResponse(data={
        "items": [_redemption_dict(r, names.get(r.student_id), products.get(r.product_id)) for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.patch("/redemptions/{redemption_id}/status", response_model=ApiResponse)
def update_redemption_status(
    redemption_id: str,
    body: RedemptionStatusUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_review_redemption(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可审核兑换")
    redemption = db.query(RedemptionRecord).filter(RedemptionRecord.id == redemption_id).first()
    if not redemption:
        raise HTTPException(status_code=404, detail="not_found: 兑换记录不存在")

    target = body.status
    current = redemption.status
    if target not in ("approved", "delivered", "cancelled"):
        raise HTTPException(status_code=400, detail="validation_error: 非法状态")
    if target == current:
        raise HTTPException(status_code=400, detail="validation_error: 状态未变化")

    now = datetime.utcnow()
    if target == "approved":
        if current != "pending":
            raise HTTPException(status_code=400, detail="validation_error: 仅待处理记录可审核通过")
        redemption.status = "approved"
        redemption.approver_id = user_id
        redemption.approved_at = now
        if body.notes is not None:
            redemption.notes = body.notes
        db.commit()
        return ApiResponse(data=_redemption_dict(redemption))

    if target == "delivered":
        if current != "approved":
            raise HTTPException(status_code=400, detail="validation_error: 仅已审核记录可发放")
        redemption.status = "delivered"
        redemption.delivered_at = now
        if body.notes is not None:
            redemption.notes = body.notes
        db.commit()
        return ApiResponse(data=_redemption_dict(redemption))

    # cancelled：退分 + 回库存（pending/approved 均可取消）
    if current not in ("pending", "approved"):
        raise HTTPException(status_code=400, detail="validation_error: 当前状态不可取消")
    account = get_locked_account(db, redemption.student_id)
    product = (
        db.query(RewardProduct)
        .filter(RewardProduct.id == redemption.product_id)
        .with_for_update()
        .first()
    )
    apply_credit_to_account(
        db, account, redemption.class_id, redemption.points_spent, "adjustment", user_id,
        description=f"兑换取消退分, 原兑换ID={redemption.id}",
        source_type="reward_product", source_id=redemption.id,
    )
    if product and product.product_type == "physical":
        product.stock = (product.stock or 0) + 1
    redemption.status = "cancelled"
    if body.notes is not None:
        redemption.notes = body.notes
    db.commit()
    return ApiResponse(data=_redemption_dict(redemption))


@router.get("/redemptions/report", response_model=ApiResponse)
def redemptions_report(
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    class_id: Optional[str] = Query(None, alias="classId"),
    group_by: str = Query("week", alias="groupBy"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """激励终端·兑换报表：兑换量 TOP/周月趋势/消耗积分汇总/状态分布。

    取消记录不参与消耗统计（积分已退回、库存已恢复），但计入状态分布全貌。
    """
    if class_id:
        if not can_manage_class_ops(db, user_id, class_id) and not is_global_admin(db, user_id):
            raise HTTPException(status_code=403, detail="forbidden: 无该班级报表权限")
    elif not is_global_admin(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 教师必须指定班级")

    q = db.query(RedemptionRecord)
    if class_id:
        q = q.filter(RedemptionRecord.class_id == class_id)
    d1, d2 = _parse_date(start_date), _parse_date(end_date)
    if d1:
        q = q.filter(RedemptionRecord.created_at >= d1)
    if d2:
        q = q.filter(RedemptionRecord.created_at < d2 + timedelta(days=1))
    all_rows = q.all()

    active = [r for r in all_rows if r.status != "cancelled"]
    total_points = sum((r.points_spent or 0) for r in active)
    total_count = len(active)

    # 状态分布（含取消，便于看全貌）
    status_map: dict[str, int] = {}
    for r in all_rows:
        status_map[r.status] = status_map.get(r.status, 0) + 1

    # 兑换量 TOP 商品（不含取消）
    product_map: dict[str, dict] = {}
    for r in active:
        bucket = product_map.setdefault(
            r.product_id, {"productId": r.product_id, "count": 0, "pointsSpent": 0})
        bucket["count"] += 1
        bucket["pointsSpent"] += r.points_spent or 0
    product_ids = list(product_map.keys())
    names = {p.id: p.name for p in db.query(RewardProduct).filter(
        RewardProduct.id.in_(product_ids)).all()} if product_ids else {}
    top_products = sorted(product_map.values(), key=lambda b: (-b["count"], -b["pointsSpent"]))[:10]
    for b in top_products:
        b["productName"] = names.get(b["productId"], "")

    # 周/月趋势（不含取消）
    trend_map: dict[str, dict] = {}
    for r in active:
        d = r.created_at.date() if r.created_at else date.today()
        key = d.strftime("%Y-%m") if group_by == "month" else (d - timedelta(days=d.weekday())).isoformat()
        bucket = trend_map.setdefault(key, {"period": key, "count": 0, "pointsSpent": 0})
        bucket["count"] += 1
        bucket["pointsSpent"] += r.points_spent or 0
    trend = sorted(trend_map.values(), key=lambda b: b["period"])

    return ApiResponse(data={
        "summary": {
            "totalRedemptions": total_count,
            "totalPointsSpent": total_points,
            "activeCount": total_count,
            "cancelledCount": status_map.get("cancelled", 0),
        },
        "statusDistribution": [
            {"status": k, "count": v} for k, v in sorted(status_map.items())
        ],
        "topProducts": top_products,
        "trend": trend,
    })


# ---------------------------------------------------------------------------
# 4.4 校外实践
# ---------------------------------------------------------------------------

@router.post("/practice-records", response_model=ApiResponse)
def create_practice_record(
    body: PracticeCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.id == body.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="not_found: 学生不存在")
    if not can_manage_class_ops(db, user_id, student.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该学生班级管理权限")
    if body.practice_type not in _PRACTICE_TYPE_LABELS:
        raise HTTPException(status_code=400, detail="validation_error: 非法实践类型")
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="validation_error: 实践标题不能为空")
    practice_date = _parse_date(body.practice_date)
    if not practice_date:
        raise HTTPException(status_code=400, detail="validation_error: 请提供 practiceDate")
    if body.evidence_images is not None and len(body.evidence_images) > EVIDENCE_MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"validation_error: 单条实践记录图片最多 {EVIDENCE_MAX_IMAGES} 张")
    record = PracticeRecord(
        student_id=student.id,
        class_id=student.class_id,
        practice_type=body.practice_type,
        title=body.title.strip(),
        description=body.description,
        practice_date=practice_date,
        duration_hours=body.duration_hours,
        location=body.location,
        evidence_images=body.evidence_images,
        status="pending",
        recorded_by=user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ApiResponse(data=_practice_dict(record, student.name))


@router.get("/practice-records", response_model=ApiResponse)
def list_practice_records(
    class_id: Optional[str] = Query(None, alias="classId"),
    student_id: Optional[str] = Query(None, alias="studentId"),
    practice_type: Optional[str] = Query(None, alias="practiceType"),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(PracticeRecord)
    if class_id:
        q = q.filter(PracticeRecord.class_id == class_id)
    if student_id:
        q = q.filter(PracticeRecord.student_id == student_id)
    if practice_type:
        q = q.filter(PracticeRecord.practice_type == practice_type)
    if status:
        q = q.filter(PracticeRecord.status == status)
    if start_date:
        q = q.filter(PracticeRecord.practice_date >= _parse_date(start_date))
    if end_date:
        q = q.filter(PracticeRecord.practice_date <= _parse_date(end_date))
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(PracticeRecord.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(PracticeRecord.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(PracticeRecord.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {r.student_id for r in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    return ApiResponse(data={
        "items": [_practice_dict(r, names.get(r.student_id)) for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.patch("/practice-records/{record_id}", response_model=ApiResponse)
def update_practice_record(
    record_id: str,
    body: PracticeUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    record = db.query(PracticeRecord).filter(PracticeRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="not_found: 实践记录不存在")
    if not (record.recorded_by == user_id or can_manage_class_ops(db, user_id, record.class_id)):
        raise HTTPException(status_code=403, detail="forbidden: 仅录入人/管理员可编辑")
    if record.status == "approved":
        raise HTTPException(status_code=400, detail="validation_error: 已审核通过的实践记录不允许编辑")

    student = db.query(Student).filter(Student.id == (body.student_id or record.student_id)).first()
    if body.student_id is not None:
        if not student:
            raise HTTPException(status_code=404, detail="not_found: 学生不存在")
        record.student_id = student.id
        record.class_id = student.class_id
    if body.practice_type is not None:
        if body.practice_type not in _PRACTICE_TYPE_LABELS:
            raise HTTPException(status_code=400, detail="validation_error: 非法实践类型")
        record.practice_type = body.practice_type
    if body.title is not None:
        if not body.title.strip():
            raise HTTPException(status_code=400, detail="validation_error: 实践标题不能为空")
        record.title = body.title.strip()
    if body.description is not None:
        record.description = body.description
    if body.practice_date is not None:
        d = _parse_date(body.practice_date)
        if not d:
            raise HTTPException(status_code=400, detail="validation_error: 请提供 practiceDate")
        record.practice_date = d
    if body.duration_hours is not None:
        record.duration_hours = body.duration_hours
    if body.location is not None:
        record.location = body.location
    if body.evidence_images is not None:
        if len(body.evidence_images) > EVIDENCE_MAX_IMAGES:
            raise HTTPException(status_code=400, detail=f"validation_error: 单条实践记录图片最多 {EVIDENCE_MAX_IMAGES} 张")
        record.evidence_images = body.evidence_images
    db.commit()
    db.refresh(record)
    return ApiResponse(data=_practice_dict(record, student.name if student else None))


@router.patch("/practice-records/{record_id}/review", response_model=ApiResponse)
def review_practice_record(
    record_id: str,
    body: PracticeReview,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    record = db.query(PracticeRecord).filter(PracticeRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="not_found: 实践记录不存在")
    if not can_review_practice(db, user_id, record.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无实践审核权限")
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="validation_error: 审核状态仅支持 approved/rejected")
    if record.status == "approved":
        raise HTTPException(status_code=400, detail="validation_error: 该记录已审核通过")

    now = datetime.utcnow()
    student = db.query(Student).filter(Student.id == record.student_id).first()
    if body.status == "approved":
        _, txn = apply_credit_change(
            db, record.student_id, record.class_id, PRACTICE_REWARD_POINTS,
            "practice_approved", user_id,
            f"【{record.title}】实践审核通过",
            source_type="practice_record", source_id=record.id,
        )
        record.credit_transaction_id = txn.id
        # 画像联动：按实践类型映射维度 + 二级指标归类
        for dim in _PRACTICE_GROWTH_DIMENSIONS.get(record.practice_type, ["moral"]):
            write_growth_record(
                db, record.student_id, record.class_id, dim,
                "practice_record", record.id, PRACTICE_REWARD_POINTS,
                note=f"【{_PRACTICE_TYPE_LABELS.get(record.practice_type, record.practice_type)}】{record.title}",
                created_by=user_id, occurred_at=record.practice_date,
                indicator_code=_PRACTICE_INDICATOR_CODES.get(record.practice_type, {}).get(dim),
            )
        record.status = "approved"
    else:
        record.status = "rejected"
    record.reviewer_id = user_id
    record.review_comment = body.review_comment
    record.reviewed_at = now
    db.commit()
    db.refresh(record)
    return ApiResponse(data=_practice_dict(record, student.name if student else None))


@router.delete("/practice-records/{record_id}", response_model=ApiResponse)
def delete_practice_record(
    record_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    record = db.query(PracticeRecord).filter(PracticeRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="not_found: 实践记录不存在")
    if not (record.recorded_by == user_id or can_manage_class_ops(db, user_id, record.class_id)):
        raise HTTPException(status_code=403, detail="forbidden: 仅录入人/管理员可删除")
    if record.credit_transaction_id:
        txn = db.query(CreditTransaction).filter(CreditTransaction.id == record.credit_transaction_id).first()
        points = txn.amount if txn else 0
        if points > 0:
            account = get_locked_account(db, record.student_id)
            if (account.balance or 0) >= points:
                apply_credit_to_account(
                    db, account, record.class_id, -points, "adjustment", user_id,
                    description=f"删除实践记录退分, 原实践ID={record.id}",
                    source_type="practice_record", source_id=record.id,
                )
        delete_growth_records(db, "practice_record", record.id)
    db.delete(record)
    db.commit()
    return ApiResponse(data={"id": record.id, "deleted": True})


# ---------------------------------------------------------------------------
# 4.5 校园生活
# ---------------------------------------------------------------------------

# ---- 社团 ----
@router.get("/clubs", response_model=ApiResponse)
def list_clubs(
    keyword: Optional[str] = Query(None),
    is_active: Optional[str] = Query(None, alias="isActive"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    del user_id
    q = db.query(CampusClub)
    if keyword:
        q = q.filter(CampusClub.name.like(f"%{keyword}%"))
    active = _parse_bool(is_active)
    if active is not None:
        q = q.filter(CampusClub.is_active == active)
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(CampusClub.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    teacher_ids = {c.teacher_id for c in rows if c.teacher_id}
    teacher_names = {u.id: u.display_name for u in db.query(User).filter(User.id.in_(teacher_ids)).all()} if teacher_ids else {}
    return ApiResponse(data={
        "items": [_club_dict(c, teacher_names.get(c.teacher_id)) for c in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.post("/clubs", response_model=ApiResponse)
def create_club(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_clubs(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可创建社团")
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="validation_error: 社团名称不能为空")
    club = CampusClub(
        name=name,
        description=body.get("description"),
        teacher_id=body.get("teacherId") or body.get("teacher_id"),
        max_members=body.get("maxMembers") or body.get("max_members") or 0,
        is_active=1 if (body.get("isActive", body.get("is_active", True)) not in (0, "0", False)) else 0,
    )
    db.add(club)
    db.commit()
    db.refresh(club)
    return ApiResponse(data=_club_dict(club))


@router.patch("/clubs/{club_id}", response_model=ApiResponse)
def update_club(
    club_id: str,
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_clubs(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可管理社团")
    club = db.query(CampusClub).filter(CampusClub.id == club_id).first()
    if not club:
        raise HTTPException(status_code=404, detail="not_found: 社团不存在")
    if body.get("name") is not None:
        name = body["name"].strip()
        if not name:
            raise HTTPException(status_code=400, detail="validation_error: 社团名称不能为空")
        club.name = name
    if body.get("description") is not None:
        club.description = body["description"]
    if body.get("teacherId") is not None or body.get("teacher_id") is not None:
        club.teacher_id = body.get("teacherId") or body.get("teacher_id")
    if body.get("maxMembers") is not None or body.get("max_members") is not None:
        club.max_members = body.get("maxMembers") or body.get("max_members") or 0
    if body.get("isActive") is not None or body.get("is_active") is not None:
        club.is_active = 1 if (body.get("isActive", body.get("is_active")) not in (0, "0", False)) else 0
    db.commit()
    db.refresh(club)
    return ApiResponse(data=_club_dict(club))


@router.delete("/clubs/{club_id}", response_model=ApiResponse)
def delete_club(
    club_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_clubs(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 仅系统管理员可管理社团")
    club = db.query(CampusClub).filter(CampusClub.id == club_id).first()
    if not club:
        raise HTTPException(status_code=404, detail="not_found: 社团不存在")
    club.is_active = 0  # 软删除
    db.commit()
    return ApiResponse(data={"id": club.id, "isActive": False})


@router.get("/clubs/{club_id}/enrollments", response_model=ApiResponse)
def list_club_enrollments(
    club_id: str,
    status: Optional[str] = Query(None),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    club = db.query(CampusClub).filter(CampusClub.id == club_id).first()
    if not club:
        raise HTTPException(status_code=404, detail="not_found: 社团不存在")
    q = db.query(ClubEnrollment).filter(ClubEnrollment.club_id == club_id)
    if status:
        q = q.filter(ClubEnrollment.status == status)
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(ClubEnrollment.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(ClubEnrollment.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(ClubEnrollment.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {e.student_id for e in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    return ApiResponse(data={
        "items": [_enrollment_dict(e, names.get(e.student_id)) for e in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.post("/club-enrollments", response_model=ApiResponse)
def batch_club_enrollments(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    club_id = body.get("clubId") or body.get("club_id")
    student_ids = body.get("studentIds") or body.get("student_ids") or []
    enrolled_at = _parse_date(body.get("enrolledAt") or body.get("enrolled_at"))
    if not club_id:
        raise HTTPException(status_code=400, detail="validation_error: 缺少 clubId")
    if not student_ids:
        raise HTTPException(status_code=400, detail="validation_error: studentIds 不能为空")
    club = db.query(CampusClub).filter(CampusClub.id == club_id).first()
    if not club or not club.is_active:
        raise HTTPException(status_code=404, detail="not_found: 社团不存在或已停用")
    if not enrolled_at:
        enrolled_at = date.today()

    students_map = {s.id: s for s in db.query(Student).filter(Student.id.in_(student_ids)).all()}
    allowed_class_ids = {
        cid for cid in {s.class_id for s in students_map.values()}
        if can_manage_class_ops(db, user_id, cid)
    }
    failures: list[dict] = []
    created = 0
    for sid in student_ids:
        student = students_map.get(sid)
        if student is None:
            failures.append({"studentId": sid, "reason": "student_not_found"})
            continue
        if student.class_id not in allowed_class_ids:
            failures.append({"studentId": sid, "studentName": student.name, "reason": "no_permission"})
            continue
        try:
            with db.begin_nested():
                if db.query(ClubEnrollment).filter(
                    ClubEnrollment.student_id == sid, ClubEnrollment.club_id == club_id,
                ).first():
                    raise _DomainFailure("duplicate_entry")
                db.add(ClubEnrollment(
                    student_id=sid, club_id=club_id, class_id=student.class_id,
                    status="enrolled", enrolled_at=enrolled_at, recorded_by=user_id,
                ))
                created += 1
        except _DomainFailure as e:
            failures.append({"studentId": sid, "studentName": student.name, "reason": e.reason})
    db.commit()
    return ApiResponse(data={
        "successCount": created,
        "failCount": len(failures),
        "failures": failures,
    })


@router.patch("/club-enrollments/{enrollment_id}", response_model=ApiResponse)
def update_club_enrollment(
    enrollment_id: str,
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    enrollment = db.query(ClubEnrollment).filter(ClubEnrollment.id == enrollment_id).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="not_found: 报名记录不存在")
    if not can_manage_class_ops(db, user_id, enrollment.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级管理权限")
    status = body.get("status")
    if status == "left":
        enrollment.status = "left"
        enrollment.left_at = date.today()
    elif status and status in ("enrolled",):
        enrollment.status = "enrolled"
        enrollment.left_at = None
    else:
        raise HTTPException(status_code=400, detail="validation_error: 非法状态")
    db.commit()
    db.refresh(enrollment)
    return ApiResponse(data=_enrollment_dict(enrollment))


def _maybe_club_full_attendance_growth(db: Session, student_id: str, club_id: str,
                                       class_id: str, recorded_by: str) -> None:
    """本学期该生对该社团全勤（出席所有已录考勤场次）→ 社团全勤成长 +30。"""
    today = datetime.utcnow().date()
    term_start, term_key = _term_range(today)
    total_sessions = db.query(sa_func.count(sa_func.distinct(ClubAttendance.session_date))).filter(
        ClubAttendance.club_id == club_id,
        ClubAttendance.session_date >= term_start,
    ).scalar() or 0
    if total_sessions <= 0:
        return
    present = db.query(sa_func.count(sa_func.distinct(ClubAttendance.session_date))).filter(
        ClubAttendance.club_id == club_id,
        ClubAttendance.student_id == student_id,
        ClubAttendance.session_date >= term_start,
        ClubAttendance.attend_status == "present",
    ).scalar() or 0
    if present < total_sessions:
        return
    club = db.query(CampusClub).filter(CampusClub.id == club_id).first()
    note = f"【社团全勤】{club.name if club else ''}（{term_key}）"
    if growth_record_exists(db, student_id, "club_activity", note=note):
        return
    write_growth_record(
        db, student_id, class_id, "physical", "club_activity", None,
        CLUB_FULL_ATTENDANCE_POINTS, note=note, created_by=recorded_by, occurred_at=today,
        indicator_code="physical_fitness",
    )


@router.post("/club-attendance", response_model=ApiResponse)
def batch_club_attendance(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    club_id = body.get("clubId") or body.get("club_id")
    session_date = _parse_date(body.get("sessionDate") or body.get("session_date"))
    records = body.get("records") or []
    if not club_id or not session_date:
        raise HTTPException(status_code=400, detail="validation_error: 缺少 clubId/sessionDate")
    if not records:
        raise HTTPException(status_code=400, detail="validation_error: records 不能为空")
    club = db.query(CampusClub).filter(CampusClub.id == club_id).first()
    if not club or not club.is_active:
        raise HTTPException(status_code=404, detail="not_found: 社团不存在或已停用")

    student_ids = [r.get("studentId") or r.get("student_id") for r in records if r.get("studentId") or r.get("student_id")]
    students_map = {s.id: s for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    allowed_class_ids = {
        cid for cid in {s.class_id for s in students_map.values()}
        if can_manage_class_ops(db, user_id, cid)
    }
    failures: list[dict] = []
    created = 0
    for rec in records:
        sid = rec.get("studentId") or rec.get("student_id")
        status = rec.get("attendStatus") or rec.get("attend_status") or "present"
        remarks = rec.get("remarks")
        if not sid:
            continue
        student = students_map.get(sid)
        if student is None:
            failures.append({"studentId": sid, "reason": "student_not_found"})
            continue
        if student.class_id not in allowed_class_ids:
            failures.append({"studentId": sid, "studentName": student.name, "reason": "no_permission"})
            continue
        try:
            with db.begin_nested():
                existing = db.query(ClubAttendance).filter(
                    ClubAttendance.student_id == sid,
                    ClubAttendance.club_id == club_id,
                    ClubAttendance.session_date == session_date,
                ).first()
                if existing:
                    raise _DomainFailure("duplicate_entry")
                db.add(ClubAttendance(
                    student_id=sid, club_id=club_id, class_id=student.class_id,
                    session_date=session_date, attend_status=status, remarks=remarks,
                    recorded_by=user_id,
                ))
                created += 1
        except _DomainFailure as e:
            failures.append({"studentId": sid, "studentName": student.name, "reason": e.reason})

    db.flush()
    # 全勤联动：对所有成功记录出席的学生触发检查
    for sid in students_map:
        if any(f.get("studentId") == sid for f in failures):
            continue
        if sid in allowed_class_ids:
            _maybe_club_full_attendance_growth(db, sid, club_id, students_map[sid].class_id, user_id)
    db.commit()
    return ApiResponse(data={
        "successCount": created,
        "failCount": len(failures),
        "failures": failures,
    })


@router.get("/club-attendance", response_model=ApiResponse)
def list_club_attendance(
    club_id: Optional[str] = Query(None, alias="clubId"),
    session_date: Optional[str] = Query(None, alias="sessionDate"),
    class_id: Optional[str] = Query(None, alias="classId"),
    student_id: Optional[str] = Query(None, alias="studentId"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(ClubAttendance)
    if club_id:
        q = q.filter(ClubAttendance.club_id == club_id)
    d = _parse_date(session_date)
    if d:
        q = q.filter(ClubAttendance.session_date == d)
    if class_id:
        q = q.filter(ClubAttendance.class_id == class_id)
    if student_id:
        q = q.filter(ClubAttendance.student_id == student_id)
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(ClubAttendance.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(ClubAttendance.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(ClubAttendance.session_date), desc(ClubAttendance.created_at)) \
        .offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {a.student_id for a in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    return ApiResponse(data={
        "items": [_attendance_dict(a, names.get(a.student_id)) for a in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


# ---- 图书借阅 ----
@router.get("/book-borrows", response_model=ApiResponse)
def list_book_borrows(
    class_id: Optional[str] = Query(None, alias="classId"),
    student_id: Optional[str] = Query(None, alias="studentId"),
    status: Optional[str] = Query(None),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(BookBorrow)
    if class_id:
        q = q.filter(BookBorrow.class_id == class_id)
    if student_id:
        q = q.filter(BookBorrow.student_id == student_id)
    if status:
        q = q.filter(BookBorrow.status == status)
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(BookBorrow.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(BookBorrow.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(BookBorrow.borrowed_at)).offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {b.student_id for b in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    return ApiResponse(data={
        "items": [_book_borrow_dict(b, names.get(b.student_id)) for b in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.post("/book-borrows", response_model=ApiResponse)
def create_book_borrow(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    student_id = body.get("studentId") or body.get("student_id")
    book_title = body.get("bookTitle") or body.get("book_title")
    if not student_id or not book_title:
        raise HTTPException(status_code=400, detail="validation_error: 缺少 studentId/bookTitle")
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="not_found: 学生不存在")
    if not can_manage_class_ops(db, user_id, student.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该学生班级管理权限")
    borrowed_at = body.get("borrowedAt") or body.get("borrowed_at") or datetime.utcnow()
    due_at = body.get("dueAt") or body.get("due_at")
    if isinstance(borrowed_at, str):
        try:
            borrowed_at = datetime.fromisoformat(borrowed_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="validation_error: borrowedAt 格式错误")
    if not due_at:
        raise HTTPException(status_code=400, detail="validation_error: 缺少 dueAt 应还时间")
    if isinstance(due_at, str):
        try:
            due_at = datetime.fromisoformat(due_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="validation_error: dueAt 格式错误")
    borrow = BookBorrow(
        student_id=student.id,
        class_id=student.class_id,
        book_title=book_title.strip(),
        book_isbn=body.get("bookIsbn") or body.get("book_isbn"),
        book_author=body.get("bookAuthor") or body.get("book_author"),
        borrowed_at=borrowed_at,
        due_at=due_at,
        status="borrowed",
        recorded_by=user_id,
        notes=body.get("notes"),
    )
    db.add(borrow)
    db.commit()
    db.refresh(borrow)
    return ApiResponse(data=_book_borrow_dict(borrow, student.name))


@router.patch("/book-borrows/{borrow_id}/return", response_model=ApiResponse)
def return_book_borrow(
    borrow_id: str,
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    borrow = db.query(BookBorrow).filter(BookBorrow.id == borrow_id).first()
    if not borrow:
        raise HTTPException(status_code=404, detail="not_found: 借阅记录不存在")
    if not _can_return_borrow(db, user_id, borrow):
        raise HTTPException(status_code=403, detail="forbidden: 仅借书学生本人/本班教师/管理员可归还")
    returned_at = body.get("returnedAt") or body.get("returned_at") or datetime.utcnow()
    if isinstance(returned_at, str):
        try:
            returned_at = datetime.fromisoformat(returned_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="validation_error: returnedAt 格式错误")
    borrow.returned_at = returned_at
    borrow.status = "returned"
    if body.get("notes") is not None:
        borrow.notes = body["notes"]
    db.commit()
    db.refresh(borrow)
    return ApiResponse(data=_book_borrow_dict(borrow))


@router.get("/book-borrows/overdue", response_model=ApiResponse)
def list_overdue_book_borrows(
    class_id: Optional[str] = Query(None, alias="classId"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    q = db.query(BookBorrow).filter(
        BookBorrow.returned_at.is_(None),
        BookBorrow.due_at < now,
    )
    if class_id:
        q = q.filter(BookBorrow.class_id == class_id)
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(BookBorrow.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(BookBorrow.class_id.in_(visible_class_ids))
    # 自动标记逾期
    for b in q.all():
        if b.status != "overdue":
            b.status = "overdue"
    db.commit()
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(asc(BookBorrow.due_at)).offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {b.student_id for b in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    return ApiResponse(data={
        "items": [_book_borrow_dict(b, names.get(b.student_id)) for b in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


# ---- 阅读打卡 ----
def _maybe_reading_top10_growth(db: Session, student_id: str, class_id: str,
                                reading_date: date, recorded_by: str) -> None:
    """阅读月榜前 10 → 阅读之星成长 +20（本月已写则跳过）。"""
    month_start = reading_date.replace(day=1)
    if month_start.month == 12:
        month_end = date(month_start.year + 1, 1, 1)
    else:
        month_end = date(month_start.year, month_start.month + 1, 1)
    rows = db.query(
        ReadingRecord.student_id,
    ).filter(
        ReadingRecord.reading_date >= month_start,
        ReadingRecord.reading_date < month_end,
        ReadingRecord.class_id == class_id,
    ).group_by(ReadingRecord.student_id) \
        .order_by(desc(sa_func.sum(ReadingRecord.pages_read))) \
        .limit(10).all()
    top_ids = [r.student_id for r in rows]
    if student_id not in top_ids:
        return
    rank = top_ids.index(student_id) + 1
    month_key = month_start.strftime("%Y-%m")
    note = f"【阅读之星】月度第{rank}名（{month_key}）"
    if growth_record_exists(db, student_id, "reading_record", note=note):
        return
    write_growth_record(
        db, student_id, class_id, "intellectual", "reading_record", None,
        READING_TOP10_POINTS, note=note, created_by=recorded_by, occurred_at=reading_date,
        indicator_code="intellectual_ability",
    )


@router.get("/reading-records", response_model=ApiResponse)
def list_reading_records(
    class_id: Optional[str] = Query(None, alias="classId"),
    student_id: Optional[str] = Query(None, alias="studentId"),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(ReadingRecord)
    if class_id:
        q = q.filter(ReadingRecord.class_id == class_id)
    if student_id:
        q = q.filter(ReadingRecord.student_id == student_id)
    if start_date:
        q = q.filter(ReadingRecord.reading_date >= _parse_date(start_date))
    if end_date:
        q = q.filter(ReadingRecord.reading_date <= _parse_date(end_date))
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(ReadingRecord.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(ReadingRecord.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(ReadingRecord.reading_date), desc(ReadingRecord.created_at)) \
        .offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {r.student_id for r in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    return ApiResponse(data={
        "items": [_reading_dict(r, names.get(r.student_id)) for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.post("/reading-records", response_model=ApiResponse)
def create_reading_record(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    student_id = body.get("studentId") or body.get("student_id")
    book_title = body.get("bookTitle") or body.get("book_title")
    reading_date = _parse_date(body.get("readingDate") or body.get("reading_date"))
    if not student_id or not book_title:
        raise HTTPException(status_code=400, detail="validation_error: 缺少 studentId/bookTitle")
    if not reading_date:
        raise HTTPException(status_code=400, detail="validation_error: 请提供 readingDate")
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="not_found: 学生不存在")
    if not can_manage_class_ops(db, user_id, student.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该学生班级管理权限")
    rec = ReadingRecord(
        student_id=student.id,
        class_id=student.class_id,
        book_title=book_title.strip(),
        pages_read=body.get("pagesRead") or body.get("pages_read") or 0,
        reading_minutes=body.get("readingMinutes") or body.get("reading_minutes") or 0,
        reading_date=reading_date,
        recorded_by=user_id,
    )
    db.add(rec)
    db.flush()
    _maybe_reading_top10_growth(db, student.id, student.class_id, reading_date, user_id)
    db.commit()
    db.refresh(rec)
    return ApiResponse(data=_reading_dict(rec, student.name))


@router.post("/reading-records/batch", response_model=ApiResponse)
def batch_reading_records(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    records = body.get("records") or []
    if not records:
        raise HTTPException(status_code=400, detail="validation_error: records 不能为空")
    student_ids = [r.get("studentId") or r.get("student_id") for r in records]
    students_map = {s.id: s for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    allowed_class_ids = {
        cid for cid in {s.class_id for s in students_map.values()}
        if can_manage_class_ops(db, user_id, cid)
    }
    failures: list[dict] = []
    created = 0
    for rec in records:
        sid = rec.get("studentId") or rec.get("student_id")
        book_title = rec.get("bookTitle") or rec.get("book_title")
        reading_date = _parse_date(rec.get("readingDate") or rec.get("reading_date"))
        if not sid or not book_title or not reading_date:
            failures.append({"studentId": sid or "", "reason": "validation_error"})
            continue
        student = students_map.get(sid)
        if student is None:
            failures.append({"studentId": sid, "reason": "student_not_found"})
            continue
        if student.class_id not in allowed_class_ids:
            failures.append({"studentId": sid, "studentName": student.name, "reason": "no_permission"})
            continue
        try:
            with db.begin_nested():
                r = ReadingRecord(
                    student_id=sid, class_id=student.class_id, book_title=book_title.strip(),
                    pages_read=rec.get("pagesRead") or rec.get("pages_read") or 0,
                    reading_minutes=rec.get("readingMinutes") or rec.get("reading_minutes") or 0,
                    reading_date=reading_date, recorded_by=user_id,
                )
                db.add(r)
                db.flush()
                _maybe_reading_top10_growth(db, sid, student.class_id, reading_date, user_id)
                created += 1
        except _DomainFailure as e:
            failures.append({"studentId": sid, "studentName": student.name, "reason": e.reason})
    db.commit()
    return ApiResponse(data={
        "successCount": created,
        "failCount": len(failures),
        "failures": failures,
    })


@router.get("/reading-leaderboard", response_model=ApiResponse)
def reading_leaderboard(
    period: str = Query("month"),
    class_id: Optional[str] = Query(None, alias="classId"),
    limit: int = Query(50),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    today = datetime.utcnow().date()
    if period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        label = "week"
    elif period == "term":
        start, label = _term_range(today)
        end = today
    else:  # month
        start = today.replace(day=1)
        if start.month == 12:
            end = date(start.year, 12, 31)
        else:
            end = date(start.year, start.month + 1, 1) - timedelta(days=1)
        label = "month"
    limit = min(max(limit, 1), 200)
    q = db.query(
        ReadingRecord.student_id,
        ReadingRecord.class_id,
        sa_func.sum(ReadingRecord.pages_read).label("total_pages"),
        sa_func.sum(ReadingRecord.reading_minutes).label("total_minutes"),
        sa_func.count(ReadingRecord.id).label("books_count"),
    ).filter(
        ReadingRecord.reading_date >= start,
        ReadingRecord.reading_date <= end,
    )
    if class_id:
        q = q.filter(ReadingRecord.class_id == class_id)
    _, visible_class_ids = _list_scope(db, user_id)
    if visible_class_ids is not None:
        if class_id:
            if class_id not in visible_class_ids:
                raise HTTPException(status_code=403, detail="forbidden: 无该班级查看权限")
        else:
            q = q.filter(ReadingRecord.class_id.in_(visible_class_ids))
    rows = q.group_by(ReadingRecord.student_id, ReadingRecord.class_id) \
        .order_by(desc("total_pages"), desc("total_minutes")) \
        .limit(limit).all()
    student_ids = [r.student_id for r in rows]
    class_ids = {r.class_id for r in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    class_names = {c.id: f"{c.grade}{c.name}" for c in db.query(Class).filter(Class.id.in_(class_ids)).all()} if class_ids else {}
    leaderboard = [
        {
            "rank": i + 1,
            "studentId": r.student_id,
            "studentName": names.get(r.student_id, ""),
            "className": class_names.get(r.class_id, ""),
            "totalPages": int(r.total_pages or 0),
            "totalMinutes": int(r.total_minutes or 0),
            "booksCount": int(r.books_count or 0),
        }
        for i, r in enumerate(rows)
    ]
    return ApiResponse(data={
        "period": label,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "leaderboard": leaderboard,
    })


# ---- 晨午检 ----
def _compute_health_alert(temperature, health_status: str) -> tuple[int, str]:
    """根据体温/状态自动标记预警。返回 (is_alert, health_status)。"""
    t = float(temperature) if temperature is not None else None
    alert = 0
    status = (health_status or "normal").strip() or "normal"
    if t is not None and t >= 37.3:
        alert = 1
        status = "abnormal"
    if status == "abnormal":
        alert = 1
    return alert, status


def _consecutive_alert_days(db: Session, student_id: str, end_date: date) -> int:
    days = 0
    cur = end_date
    while True:
        row = db.query(HealthCheck).filter(
            HealthCheck.student_id == student_id,
            HealthCheck.check_date == cur,
            HealthCheck.is_alert == 1,
        ).first()
        if row:
            days += 1
            cur = cur - timedelta(days=1)
        else:
            break
    return days


def _maybe_health_alert_growth(db: Session, student_id: str, class_id: str,
                               check_date: date, recorded_by: str) -> None:
    """连续 3 天异常 → health_check 留痕成长（0 分，仅记录）。"""
    if _consecutive_alert_days(db, student_id, check_date) >= 3:
        note = f"【健康关注】连续异常（{check_date.isoformat()}）"
        if not growth_record_exists(db, student_id, "health_check", note=note):
            write_growth_record(
                db, student_id, class_id, "physical", "health_check", None,
                HEALTH_ALERT_POINTS, note=note, created_by=recorded_by, occurred_at=check_date,
                indicator_code="physical_metrics",
            )


@router.get("/health-checks", response_model=ApiResponse)
def list_health_checks(
    class_id: Optional[str] = Query(None, alias="classId"),
    student_id: Optional[str] = Query(None, alias="studentId"),
    check_type: Optional[str] = Query(None, alias="checkType"),
    check_date: Optional[str] = Query(None, alias="checkDate"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(HealthCheck)
    if class_id:
        q = q.filter(HealthCheck.class_id == class_id)
    if student_id:
        q = q.filter(HealthCheck.student_id == student_id)
    if check_type:
        q = q.filter(HealthCheck.check_type == check_type)
    d = _parse_date(check_date)
    if d:
        q = q.filter(HealthCheck.check_date == d)
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(HealthCheck.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(HealthCheck.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(HealthCheck.check_date), desc(HealthCheck.created_at)) \
        .offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {h.student_id for h in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    return ApiResponse(data={
        "items": [_health_dict(h, names.get(h.student_id)) for h in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.post("/health-checks", response_model=ApiResponse)
def batch_health_checks(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    class_id = body.get("classId") or body.get("class_id")
    check_type = body.get("checkType") or body.get("check_type")
    check_date = _parse_date(body.get("checkDate") or body.get("check_date"))
    records = body.get("records") or []
    if not class_id or not check_type or not check_date:
        raise HTTPException(status_code=400, detail="validation_error: 缺少 classId/checkType/checkDate")
    if check_type not in ("morning", "afternoon"):
        raise HTTPException(status_code=400, detail="validation_error: 非法检查类型")
    if not records:
        raise HTTPException(status_code=400, detail="validation_error: records 不能为空")
    if not can_manage_class_ops(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级管理权限")

    student_ids = [r.get("studentId") or r.get("student_id") for r in records]
    students_map = {s.id: s for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    failures: list[dict] = []
    created = 0
    for rec in records:
        sid = rec.get("studentId") or rec.get("student_id")
        if not sid:
            continue
        student = students_map.get(sid)
        if student is None:
            failures.append({"studentId": sid, "reason": "student_not_found"})
            continue
        if student.class_id != class_id:
            failures.append({"studentId": sid, "studentName": student.name, "reason": "no_permission"})
            continue
        temperature = rec.get("temperature")
        health_status = rec.get("healthStatus") or rec.get("health_status") or "normal"
        is_alert, health_status = _compute_health_alert(temperature, health_status)
        try:
            with db.begin_nested():
                existing = db.query(HealthCheck).filter(
                    HealthCheck.student_id == sid,
                    HealthCheck.check_type == check_type,
                    HealthCheck.check_date == check_date,
                ).first()
                if existing:
                    raise _DomainFailure("duplicate_entry")
                db.add(HealthCheck(
                    student_id=sid, class_id=student.class_id, check_type=check_type,
                    check_date=check_date, temperature=temperature, health_status=health_status,
                    symptoms=rec.get("symptoms"), is_alert=is_alert, recorded_by=user_id,
                ))
                created += 1
        except _DomainFailure as e:
            failures.append({"studentId": sid, "studentName": student.name, "reason": e.reason})

    db.flush()
    for rec in records:
        sid = rec.get("studentId") or rec.get("student_id")
        if not sid or sid not in students_map or any(f.get("studentId") == sid for f in failures):
            continue
        student = students_map[sid]
        is_alert, _ = _compute_health_alert(rec.get("temperature"), rec.get("healthStatus") or "normal")
        if is_alert:
            _maybe_health_alert_growth(db, sid, student.class_id, check_date, user_id)
    db.commit()
    return ApiResponse(data={
        "successCount": created,
        "failCount": len(failures),
        "failures": failures,
    })


@router.patch("/health-checks/{check_id}", response_model=ApiResponse)
def update_health_check(
    check_id: str,
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    hc = db.query(HealthCheck).filter(HealthCheck.id == check_id).first()
    if not hc:
        raise HTTPException(status_code=404, detail="not_found: 检查记录不存在")
    if not can_manage_class_ops(db, user_id, hc.class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级管理权限")
    if body.get("temperature") is not None:
        hc.temperature = body["temperature"]
    if body.get("healthStatus") is not None or body.get("health_status") is not None:
        hc.health_status = body.get("healthStatus") or body.get("health_status")
    if body.get("symptoms") is not None:
        hc.symptoms = body["symptoms"]
    if body.get("handledBy") is not None or body.get("handled_by") is not None:
        hc.handled_by = body.get("handledBy") or body.get("handled_by")
    if body.get("handleNotes") is not None or body.get("handle_notes") is not None:
        hc.handle_notes = body.get("handleNotes") or body.get("handle_notes")
    if body.get("isAlert") is not None or body.get("is_alert") is not None:
        hc.is_alert = 1 if (body.get("isAlert", body.get("is_alert")) not in (0, "0", False)) else 0
    else:
        is_alert, health_status = _compute_health_alert(hc.temperature, hc.health_status)
        hc.is_alert = is_alert
        hc.health_status = health_status
    db.commit()
    db.refresh(hc)
    return ApiResponse(data=_health_dict(hc))


@router.get("/health-alerts", response_model=ApiResponse)
def list_health_alerts(
    class_id: Optional[str] = Query(None, alias="classId"),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(HealthCheck).filter(HealthCheck.is_alert == 1)
    if class_id:
        q = q.filter(HealthCheck.class_id == class_id)
    if start_date:
        q = q.filter(HealthCheck.check_date >= _parse_date(start_date))
    if end_date:
        q = q.filter(HealthCheck.check_date <= _parse_date(end_date))
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(HealthCheck.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(HealthCheck.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(HealthCheck.check_date)).offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {h.student_id for h in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    items = []
    for h in rows:
        d = _health_dict(h, names.get(h.student_id))
        d["consecutiveAlertDays"] = _consecutive_alert_days(db, h.student_id, h.check_date)
        d["isHandled"] = bool(h.handled_by)
        items.append(d)
    return ApiResponse(data={"items": items, "total": total, "page": page, "pageSize": page_size})


# ---- 晨午检请假/出勤 ----
_ATTENDANCE_STATUSES = {"present", "leave", "late", "absent"}


@router.post("/attendance", response_model=ApiResponse)
def batch_attendance(
    body: AttendanceBatchCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """批量登记某班某日晨/午请假出勤（present/leave/late/absent）。"""
    class_id = body.class_id
    at_date = _parse_date(body.date)
    if not at_date:
        raise HTTPException(status_code=400, detail="validation_error: 请提供 date")
    if body.check_type not in ("morning", "afternoon"):
        raise HTTPException(status_code=400, detail="validation_error: 非法检查类型")
    if not body.records:
        raise HTTPException(status_code=400, detail="validation_error: records 不能为空")
    if not can_manage_class_ops(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级管理权限")

    student_ids = [r.student_id for r in body.records]
    students_map = {s.id: s for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    failures: list[dict] = []
    created = 0
    for rec in body.records:
        status = (rec.status or "present").strip()
        if status not in _ATTENDANCE_STATUSES:
            failures.append({"studentId": rec.student_id, "reason": "validation_error: 非法出勤状态"})
            continue
        student = students_map.get(rec.student_id)
        if student is None:
            failures.append({"studentId": rec.student_id, "reason": "student_not_found"})
            continue
        if student.class_id != class_id:
            failures.append({"studentId": rec.student_id, "studentName": student.name, "reason": "no_permission"})
            continue
        try:
            with db.begin_nested():
                existing = db.query(AttendanceRecord).filter(
                    AttendanceRecord.student_id == rec.student_id,
                    AttendanceRecord.check_type == body.check_type,
                    AttendanceRecord.date == at_date,
                ).first()
                if existing:
                    raise _DomainFailure("duplicate_entry")
                db.add(AttendanceRecord(
                    student_id=rec.student_id, class_id=class_id, date=at_date,
                    check_type=body.check_type, status=status,
                    reason=rec.reason, recorded_by=user_id,
                ))
                created += 1
        except _DomainFailure as e:
            failures.append({"studentId": rec.student_id, "studentName": student.name, "reason": e.reason})
        except IntegrityError:
            failures.append({"studentId": rec.student_id, "studentName": student.name, "reason": "duplicate_entry"})
    db.commit()
    return ApiResponse(data={
        "successCount": created,
        "failCount": len(failures),
        "failures": failures,
    })


@router.get("/attendance", response_model=ApiResponse)
def list_attendance_records(
    class_id: Optional[str] = Query(None, alias="classId"),
    student_id: Optional[str] = Query(None, alias="studentId"),
    check_type: Optional[str] = Query(None, alias="checkType"),
    check_date: Optional[str] = Query(None, alias="date"),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, alias="startDate"),
    end_date: Optional[str] = Query(None, alias="endDate"),
    page: int = Query(1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(AttendanceRecord)
    if class_id:
        q = q.filter(AttendanceRecord.class_id == class_id)
    if student_id:
        q = q.filter(AttendanceRecord.student_id == student_id)
    if check_type:
        q = q.filter(AttendanceRecord.check_type == check_type)
    d = _parse_date(check_date)
    if d:
        q = q.filter(AttendanceRecord.date == d)
    if status:
        q = q.filter(AttendanceRecord.status == status)
    d1, d2 = _parse_date(start_date), _parse_date(end_date)
    if d1:
        q = q.filter(AttendanceRecord.date >= d1)
    if d2:
        q = q.filter(AttendanceRecord.date <= d2)
    own_student_ids, visible_class_ids = _list_scope(db, user_id)
    if own_student_ids is not None:
        q = q.filter(AttendanceRecord.student_id.in_(own_student_ids))
    elif visible_class_ids is not None:
        q = q.filter(AttendanceRecord.class_id.in_(visible_class_ids))
    page, page_size = _pagination(page, page_size)
    total = q.count()
    rows = q.order_by(desc(AttendanceRecord.date), desc(AttendanceRecord.created_at)) \
        .offset((page - 1) * page_size).limit(page_size).all()
    student_ids = {a.student_id for a in rows}
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    return ApiResponse(data={
        "items": [_attendance_record_dict(a, names.get(a.student_id)) for a in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    })


@router.get("/attendance/stats", response_model=ApiResponse)
def attendance_stats(
    class_id: str = Query(..., alias="classId"),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    check_type: Optional[str] = Query(None, alias="checkType"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """出勤统计：按班级日期区间聚合应到/实到/请假/缺勤/迟到/异常率。"""
    if not can_manage_class_ops(db, user_id, class_id) and not is_global_admin(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级报表权限")
    d1, d2 = _parse_date(from_date), _parse_date(to_date)
    if not d1:
        d1 = d2 if d2 else (date.today() - timedelta(days=30))
    if not d2:
        d2 = d1 + timedelta(days=30)
    if d2 < d1:
        raise HTTPException(status_code=400, detail="validation_error: from 不能晚于 to")

    q = db.query(AttendanceRecord).filter(
        AttendanceRecord.class_id == class_id,
        AttendanceRecord.date >= d1,
        AttendanceRecord.date <= d2,
    )
    if check_type:
        q = q.filter(AttendanceRecord.check_type == check_type)
    rows = q.all()

    counts = {"present": 0, "leave": 0, "late": 0, "absent": 0}
    for r in rows:
        if r.status in counts:
            counts[r.status] += 1
    total = len(rows)
    abnormal = counts["leave"] + counts["late"] + counts["absent"]
    anomaly_rate = round(abnormal / total, 4) if total else 0.0

    date_map: dict[str, dict] = {}
    student_map: dict[str, dict] = {}
    for r in rows:
        key = r.date.isoformat()
        dbucket = date_map.setdefault(
            key, {"date": key, "present": 0, "leave": 0, "late": 0, "absent": 0, "total": 0})
        dbucket[r.status] = dbucket.get(r.status, 0) + 1
        dbucket["total"] += 1
        sbucket = student_map.setdefault(
            r.student_id, {"studentId": r.student_id, "present": 0, "leave": 0, "late": 0, "absent": 0, "total": 0})
        sbucket[r.status] = sbucket.get(r.status, 0) + 1
        sbucket["total"] += 1

    by_date = [date_map[k] for k in sorted(date_map.keys())]
    student_ids = list(student_map.keys())
    names = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(student_ids)).all()} if student_ids else {}
    by_student = [
        {**student_map[sid], "studentName": names.get(sid, "")}
        for sid in student_ids
    ]
    cls = db.query(Class).filter(Class.id == class_id).first()
    return ApiResponse(data={
        "classId": class_id,
        "className": f"{cls.grade}{cls.name}" if cls else "",
        "from": d1.isoformat(),
        "to": d2.isoformat(),
        "summary": {
            "expected": total,
            "present": counts["present"],
            "leave": counts["leave"],
            "late": counts["late"],
            "absent": counts["absent"],
            "anomalyRate": anomaly_rate,
        },
        "byDate": by_date,
        "byStudent": by_student,
    })


# ---------------------------------------------------------------------------
# 4.6 文件上传 + 直链（复用 download ticket）
# ---------------------------------------------------------------------------

@router.post("/upload-evidence", response_model=ApiResponse)
def upload_evidence(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    del db
    if not user_id:
        raise HTTPException(status_code=401, detail="unauthorized: 未登录")
    contents = file.file.read()
    try:
        result = save_evidence_image(contents, file.filename or "image.jpg")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"internal_error: 图片保存失败 {str(e)}")
    return ApiResponse(data=result)


@router.get("/get-file-url", response_model=ApiResponse)
def get_file_url(
    path: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    del db
    if not path:
        raise HTTPException(status_code=400, detail="validation_error: 缺少 path")
    # 防目录穿越校验
    safe = path.replace("\\", "/")
    if ".." in safe.split("/") or safe.startswith("/"):
        raise HTTPException(status_code=403, detail="forbidden: 无效路径")
    resource = f"student-ops/files/{safe}"
    download_url = build_download_url(resource, user_id)
    return ApiResponse(data={"downloadUrl": download_url})


@router.get("/files/{file_path:path}")
def serve_student_ops_file(file_path: str, request: Request):
    """复用 download ticket 机制校验后返回文件（C0 §3 图片佐证）。"""
    resource = f"student-ops/files/{file_path}"
    user_id_from_request(request, resource=resource)
    file_path_resolved = resolve_evidence_file(file_path)
    return FileResponse(str(file_path_resolved))
