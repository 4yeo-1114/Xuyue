"""班级 CRUD、任课教师；协作教师可在「我的班级」中看到对应班级"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import asc

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.class_model import Class
from app.models.class_teacher import ClassTeacher
from app.models.user import User
from app.schemas.classes import (
    ClassRecord,
    CreateClassRequest,
    UpdateClassRequest,
    ClassTeacherRecord,
    AddClassTeacherRequest,
    PatchClassTeacherRequest,
)
from app.schemas.common import ApiResponse
from app.utils.class_access import can_manage_teachers, can_view_class, _is_global_admin, is_class_owner

router = APIRouter(prefix="/classes", tags=["classes"])


def _orm_to_record(
    c: Class,
    viewer_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> ClassRecord:
    my_role: Optional[str] = None
    is_owner = False
    if viewer_id and db:
        if _is_global_admin(db, viewer_id):
            is_owner = True
            my_role = "head"
        else:
            is_owner = c.user_id == viewer_id
            if is_owner:
                my_role = "head"
            else:
                ct = (
                    db.query(ClassTeacher)
                    .filter(ClassTeacher.class_id == c.id, ClassTeacher.user_id == viewer_id)
                    .first()
                )
                if ct:
                    my_role = ct.role
    return ClassRecord(
        id=c.id,
        user_id=c.user_id,
        school_level=c.school_level,
        grade=c.grade,
        name=c.name,
        student_count=c.student_count,
        created_at=c.created_at.isoformat() if c.created_at else "",
        updated_at=c.updated_at.isoformat() if c.updated_at else "",
        my_role=my_role,
        is_owner=is_owner,
    )


def _merge_class_lists(db: Session, user_id: str, school_level: Optional[str], grade: Optional[str]) -> List[Class]:
    if _is_global_admin(db, user_id):
        # 全局管理员看全校
        q = db.query(Class)
        if school_level:
            q = q.filter(Class.school_level == school_level)
        if grade:
            q = q.filter(Class.grade == grade)
        return q.order_by(asc(Class.name)).all()

    q1 = db.query(Class).filter(Class.user_id == user_id)
    if school_level:
        q1 = q1.filter(Class.school_level == school_level)
    if grade:
        q1 = q1.filter(Class.grade == grade)
    owned = q1.all()

    q2 = (
        db.query(Class)
        .join(ClassTeacher, ClassTeacher.class_id == Class.id)
        .filter(ClassTeacher.user_id == user_id)
    )
    if school_level:
        q2 = q2.filter(Class.school_level == school_level)
    if grade:
        q2 = q2.filter(Class.grade == grade)
    invited = q2.all()

    seen = set()
    out: List[Class] = []
    for c in owned + invited:
        if c.id in seen:
            continue
        seen.add(c.id)
        out.append(c)
    out.sort(key=lambda x: x.name or "")
    return out


@router.get("", response_model=ApiResponse[List[ClassRecord]])
def list_classes(
    school_level: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rows = _merge_class_lists(db, user_id, school_level, grade)
    return ApiResponse(data=[_orm_to_record(c, viewer_id=user_id, db=db) for c in rows])


@router.post("", response_model=ApiResponse[ClassRecord])
def create_class(
    body: CreateClassRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    exists = (
        db.query(Class)
        .filter(
            Class.user_id == user_id,
            Class.school_level == body.school_level,
            Class.grade == body.grade,
            Class.name == body.name,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="该班级已存在")
    c = Class(
        user_id=user_id,
        school_level=body.school_level,
        grade=body.grade,
        name=body.name,
        student_count=0,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    try:
        from app.grading.wrong_question_db import ensure_class_wrong_question_dir
        from app.grading.user_paths import reset_grading_user_id, set_grading_user_id

        token = set_grading_user_id(user_id)
        try:
            ensure_class_wrong_question_dir(c.id)
        finally:
            reset_grading_user_id(token)
    except Exception:
        pass
    return ApiResponse(data=_orm_to_record(c, viewer_id=user_id, db=db))


@router.patch("/{class_id}", response_model=ApiResponse[ClassRecord])
def update_class(
    class_id: str,
    body: UpdateClassRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c or not is_class_owner(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在或无权操作")
    exists = (
        db.query(Class)
        .filter(
            Class.user_id == c.user_id,
            Class.school_level == c.school_level,
            Class.grade == c.grade,
            Class.name == body.name,
            Class.id != class_id,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="该班级名称已存在")
    c.name = body.name
    from app.models.class_analysis import ClassAnalysisReport

    db.query(ClassAnalysisReport).filter(ClassAnalysisReport.class_id == class_id).update(
        {ClassAnalysisReport.class_name: body.name},
        synchronize_session=False,
    )
    db.commit()
    db.refresh(c)
    return ApiResponse(data=_orm_to_record(c, viewer_id=user_id, db=db))


@router.delete("/{class_id}", response_model=ApiResponse[None])
def delete_class(
    class_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c or not is_class_owner(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在或无权操作")
    from app.models.class_analysis import ClassAnalysisReport

    db.query(ClassAnalysisReport).filter(ClassAnalysisReport.class_id == class_id).delete(
        synchronize_session=False
    )
    db.delete(c)
    db.commit()
    try:
        from app.grading.router import cleanup_grading_data_for_class
        cleanup_grading_data_for_class(class_id, user_id)
    except Exception:
        pass
    try:
        from app.grading.wrong_question_db import cleanup_class_wrong_question_dir
        from app.grading.user_paths import reset_grading_user_id, set_grading_user_id

        token = set_grading_user_id(user_id)
        try:
            cleanup_class_wrong_question_dir(class_id)
        finally:
            reset_grading_user_id(token)
    except Exception:
        pass
    return ApiResponse(data=None)


@router.get("/{class_id}/teachers", response_model=ApiResponse[List[ClassTeacherRecord]])
def list_class_teachers(
    class_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    rows = (
        db.query(ClassTeacher, User)
        .join(User, User.id == ClassTeacher.user_id)
        .filter(ClassTeacher.class_id == class_id)
        .all()
    )
    out: List[ClassTeacherRecord] = []
    for r, u in rows:
        subject = getattr(u, "teaching_subject", None) or r.subject
        if subject == "__CLEAR__":
            subject = None
            
        out.append(
            ClassTeacherRecord(
                id=r.id,
                user_id=r.user_id,
                email=u.email,
                display_name=u.display_name,
                role=r.role,
                subject=subject,
            )
        )
    out.sort(key=lambda x: (x.role != "head", x.display_name or x.email))
    return ApiResponse(data=out)


@router.post("/{class_id}/teachers", response_model=ApiResponse[ClassTeacherRecord])
def add_class_teacher(
    class_id: str,
    body: AddClassTeacherRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_teachers(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="仅班主任可添加教师")
    role = (body.role or "").strip().lower()
    if role not in ("head", "deputy", "teacher"):
        raise HTTPException(status_code=400, detail="角色须为班主任(head)或副班主任(deputy)或教师(teacher)")
        
    if role == "head":
        if not _is_global_admin(db, user_id):
            raise HTTPException(status_code=403, detail="仅系统管理员/校级管理者/年级组长等可设置班主任")
        # 检查是否已存在班主任
        existing_head = db.query(ClassTeacher).filter(ClassTeacher.class_id == class_id, ClassTeacher.role == "head").first()
        if existing_head:
            raise HTTPException(status_code=400, detail="该班级已存在班主任，一个班只能设置一个班主任")
            
    email = (body.email or "").strip().lower()
    target = db.query(User).filter(User.email == email).first()
    if not target:
        raise HTTPException(status_code=400, detail="该账号不存在，请确认邮箱已注册")
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="班级不存在")
    exists = (
        db.query(ClassTeacher)
        .filter(ClassTeacher.class_id == class_id, ClassTeacher.user_id == target.id)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="该教师已在班级中")
    subj = getattr(target, "teaching_subject", None)
    if subj == "__CLEAR__":
        subj = None
        
    row = ClassTeacher(
        class_id=class_id,
        user_id=target.id,
        role=role,
        subject=subj,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiResponse(
        data=ClassTeacherRecord(
            id=row.id,
            user_id=target.id,
            email=target.email,
            display_name=target.display_name,
            role=row.role,
            subject=row.subject,
        )
    )


@router.patch("/{class_id}/teachers/{ct_id}", response_model=ApiResponse[ClassTeacherRecord])
def patch_class_teacher(
    class_id: str,
    ct_id: str,
    body: PatchClassTeacherRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_teachers(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="仅班主任可修改教师角色")
    r = db.query(ClassTeacher).filter(ClassTeacher.id == ct_id, ClassTeacher.class_id == class_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="教师记录不存在")
        
    new_role = (body.role or "").strip().lower()
    if new_role not in ("head", "deputy", "teacher"):
        raise HTTPException(status_code=400, detail="角色须为班主任、副班主任或教师")
        
    is_admin = _is_global_admin(db, user_id)
    
    # 逻辑调整：班主任可以转让班主任角色
    if new_role == "head" and r.role != "head":
        is_head = db.query(ClassTeacher).filter(
            ClassTeacher.class_id == class_id, 
            ClassTeacher.user_id == user_id, 
            ClassTeacher.role == "head"
        ).first() is not None

        if not (is_admin or is_head):
            raise HTTPException(status_code=403, detail="无权设置班主任")
        
        # 查找现有的班主任并降级
        existing_heads = db.query(ClassTeacher).filter(ClassTeacher.class_id == class_id, ClassTeacher.role == "head").all()
        for head in existing_heads:
            # 管理员可以直接修改，非管理员的现任班主任只能转让自己的班主任角色
            if not is_admin and head.user_id != user_id:
                raise HTTPException(status_code=403, detail="仅现任班主任或管理员可以转让班主任角色")
            head.role = "teacher"
            db.add(head)

    # 如果取消某人的班主任角色，但没有指定新班主任（比如直接把他改成普通教师）
    if r.role == "head" and new_role != "head":
        if not is_admin:
            raise HTTPException(status_code=400, detail="班主任必须转让给其他老师，不能直接取消自己的班主任角色")
            
    r.role = new_role
    db.commit()
    db.refresh(r)
    u = db.query(User).filter(User.id == r.user_id).first()
    
    subject = r.subject
    if subject == "__CLEAR__":
        subject = None
        
    return ApiResponse(
        data=ClassTeacherRecord(
            id=r.id,
            user_id=r.user_id,
            email=u.email if u else "",
            display_name=u.display_name if u else None,
            role=r.role,
            subject=subject,
        )
    )

@router.post("/{class_id}/leave", response_model=ApiResponse[None])
def leave_class(
    class_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ct = db.query(ClassTeacher).filter(ClassTeacher.class_id == class_id, ClassTeacher.user_id == user_id).first()
    if not ct:
        raise HTTPException(status_code=400, detail="您不在该班级中")
    if ct.role == "head":
        raise HTTPException(status_code=400, detail="班主任不能直接退出班级，请先将班主任角色转让给其他教师")
    
    c = db.query(Class).filter(Class.id == class_id).first()
    if c and c.user_id == user_id:
        raise HTTPException(status_code=400, detail="班级创建者不能直接退出班级，请转让班级或删除班级")
        
    db.delete(ct)
    db.commit()
    return ApiResponse(data=None)


@router.delete("/{class_id}/teachers/{ct_id}", response_model=ApiResponse[None])
def delete_class_teacher(
    class_id: str,
    ct_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_teachers(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="仅班主任可移除教师")
    r = db.query(ClassTeacher).filter(ClassTeacher.id == ct_id, ClassTeacher.class_id == class_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="记录不存在")
    if r.role == "head":
        if not _is_global_admin(db, user_id):
            raise HTTPException(status_code=400, detail="仅管理员可移除班主任")
    db.delete(r)
    db.commit()
    return ApiResponse(data=None)
