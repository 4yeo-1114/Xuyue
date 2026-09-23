"""学生 CRUD：按班级列出、添加学生；协作教师按角色授权"""
from typing import List
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import asc
import pandas as pd
import io

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.class_model import Class
from app.models.student import Student
from app.schemas.students import StudentRecord, CreateStudentRequest, UpdateStudentRequest
from app.schemas.common import ApiResponse
from app.services.field_masking import mask_address, mask_name, mask_phone, mask_student_number
from app.utils.class_access import can_manage_students, can_view_class, can_view_student_pii

router = APIRouter(prefix="/students", tags=["students"])


def _mask_keep_none(value, mask_fn):
    """对 PII 字段掩码，保留 None 语义（None → None；空串/其他交给 mask_fn）。"""
    if value is None:
        return None
    return mask_fn(value)


def _orm_to_record(s: Student, include_pii: bool = True) -> StudentRecord:
    """Student ORM → StudentRecord。

    include_pii=False（副班主任/协作教师）时对 PII 字段做掩码：
    student_number → mask_student_number、phone/parent_phone → mask_phone、
    parent_name → mask_name、address → mask_address、birthday → None。
    姓名/性别/状态/tier 等非 PII 字段保持原样。
    """
    if include_pii:
        student_number = s.student_number
        phone = getattr(s, "phone", None)
        parent_name = getattr(s, "parent_name", None)
        parent_phone = getattr(s, "parent_phone", None)
        address = getattr(s, "address", None)
        birthday = getattr(s, "birthday", None)
    else:
        student_number = mask_student_number(s.student_number) if s.student_number is not None else ""
        phone = _mask_keep_none(getattr(s, "phone", None), mask_phone)
        parent_name = _mask_keep_none(getattr(s, "parent_name", None), mask_name)
        parent_phone = _mask_keep_none(getattr(s, "parent_phone", None), mask_phone)
        address = _mask_keep_none(getattr(s, "address", None), mask_address)
        birthday = None
    return StudentRecord(
        id=s.id,
        class_id=s.class_id,
        user_id=s.user_id,
        name=s.name,
        student_number=student_number,
        gender=getattr(s, "gender", None),
        tier=getattr(s, "tier", None),
        status=getattr(s, "status", None),
        birthday=birthday,
        phone=phone,
        parent_name=parent_name,
        parent_phone=parent_phone,
        address=address,
        enroll_date=getattr(s, "enroll_date", None),
        seat_row=getattr(s, "seat_row", None),
        seat_col=getattr(s, "seat_col", None),
        cadre_role=getattr(s, "cadre_role", None),
        notes=getattr(s, "notes", None),
        created_at=s.created_at.isoformat() if s.created_at else "",
        updated_at=s.updated_at.isoformat() if s.updated_at else "",
    )


@router.get("", response_model=ApiResponse[List[StudentRecord]])
def list_students(
    class_id: str = Query(..., description="班级 ID"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    include_pii = can_view_student_pii(db, user_id, class_id)
    rows = db.query(Student).filter(Student.class_id == class_id).order_by(asc(Student.student_number)).all()
    return ApiResponse(data=[_orm_to_record(s, include_pii=include_pii) for s in rows])


@router.post("", response_model=ApiResponse[StudentRecord])
def create_student(
    body: CreateStudentRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_students(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="无权限管理该班级学生")
    c = db.query(Class).filter(Class.id == body.class_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="班级不存在")
    name = (body.name or "").strip()
    student_number = (body.student_number or "").strip()
    gender = (body.gender or "").strip() or "未知"
    if not name:
        raise HTTPException(status_code=400, detail="请输入学生姓名")

    if student_number:
        exists = db.query(Student).filter(Student.class_id == body.class_id, Student.student_number == student_number).first()
        if exists:
            raise HTTPException(status_code=400, detail="该学号在本班已存在")

    s = Student(
        class_id=body.class_id,
        user_id=user_id,
        school_id=c.school_id,
        name=name,
        student_number=student_number,
        gender=gender,
        tier="B",
        status="正常",
    )
    db.add(s)
    c.student_count = (c.student_count or 0) + 1
    db.commit()
    db.refresh(s)
    return ApiResponse(data=_orm_to_record(s))


@router.post("/batch", response_model=ApiResponse[int])
def batch_create_students(
    body: dict,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    class_id = (body.get("class_id") or "").strip()
    students = body.get("students") or []
    if not class_id:
        raise HTTPException(status_code=400, detail="缺少 class_id")
    if not isinstance(students, list) or len(students) == 0:
        raise HTTPException(status_code=400, detail="缺少 students")
    if not can_manage_students(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="无权限管理该班级学生")
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="班级不存在")

    created = 0
    for item in students:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        student_number = (item.get("student_number") or "").strip()
        gender = (item.get("gender") or "").strip() or "未知"
        if not name:
            continue
        if student_number:
            exists = db.query(Student).filter(Student.class_id == class_id, Student.student_number == student_number).first()
            if exists:
                continue
        s = Student(
            class_id=class_id,
            user_id=user_id,
            school_id=c.school_id,
            name=name,
            student_number=student_number,
            gender=gender,
            tier="B",
            status="正常",
        )
        db.add(s)
        created += 1

    c.student_count = (c.student_count or 0) + created
    db.commit()
    return ApiResponse(data=created)


@router.post("/import", response_model=ApiResponse[int])
def import_students(
    class_id: str = Form(...),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_students(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="无权限管理该班级学生")
    
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="班级不存在")

    try:
        contents = file.file.read()
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件解析失败: {str(e)}")

    mapping = {
        'student_number': ['学籍号', '学号', '编号', '序号'],
        'name': ['姓名', '名字', '学生姓名'],
        'gender': ['性别', '男/女'],
        'cadre_role': ['班干部', '职务', '角色'],
        'enroll_date': ['入学时间', '入学日期'],
        'phone': ['学生手机', '手机号', '联系电话'],
        'parent_name': ['家长姓名', '联系人'],
        'parent_phone': ['家长电话', '家长联系方式'],
        'address': ['家庭地址', '地址', '居住地'],
        'notes': ['备注', '说明']
    }
    
    found_cols = {}
    for attr, keywords in mapping.items():
        for col in df.columns:
            if any(k in str(col) for k in keywords):
                found_cols[attr] = col
                break
    
    if 'name' not in found_cols:
        raise HTTPException(status_code=400, detail="未找到'姓名'列，请检查文件格式")

    created = 0
    updated = 0
    # Fetch existing students for this class to check by name
    existing_students = db.query(Student).filter(Student.class_id == class_id).all()
    # 建立以名字为 key 的映射，由于可能存在同名，取第一个遇到的或者业务需要唯一姓名
    # 这里的逻辑：以班级内“姓名”作为唯一标识进行更新
    student_name_map = {s.name: s for s in existing_students}

    students_to_add = []

    for _, row in df.iterrows():
        name = str(row.get(found_cols.get('name', ''), "")).strip()
        if not name or name == "nan":
            continue
            
        student_number = ""
        if 'student_number' in found_cols:
            student_number = str(row.get(found_cols['student_number'], "")).strip()
            if student_number == "nan":
                student_number = ""

        gender = str(row.get(found_cols.get('gender', ''), "")).strip() if found_cols.get('gender') else "未知"
        cadre_role = str(row.get(found_cols.get('cadre_role', ''), "")).strip() if found_cols.get('cadre_role') else None
        enroll_date = str(row.get(found_cols.get('enroll_date', ''), "")).strip() if found_cols.get('enroll_date') else None
        phone = str(row.get(found_cols.get('phone', ''), "")).strip() if found_cols.get('phone') else None
        parent_name = str(row.get(found_cols.get('parent_name', ''), "")).strip() if found_cols.get('parent_name') else None
        parent_phone = str(row.get(found_cols.get('parent_phone', ''), "")).strip() if found_cols.get('parent_phone') else None
        address = str(row.get(found_cols.get('address', ''), "")).strip() if found_cols.get('address') else None
        notes = str(row.get(found_cols.get('notes', ''), "")).strip() if found_cols.get('notes') else None

        # Handle "nan" string conversion
        gender = None if gender == "nan" else gender
        cadre_role = None if cadre_role == "nan" else cadre_role
        enroll_date = None if enroll_date == "nan" else enroll_date
        phone = None if phone == "nan" else phone
        parent_name = None if parent_name == "nan" else parent_name
        parent_phone = None if parent_phone == "nan" else parent_phone
        address = None if address == "nan" else address
        notes = None if notes == "nan" else notes

        if name in student_name_map:
            # 更新已有学生
            s = student_name_map[name]
            # 只有当 Excel 中该字段有值（且不为空）时才更新，为空则保留原值
            if student_number:
                s.student_number = student_number
            if gender and gender != "未知":
                s.gender = gender
            if cadre_role:
                s.cadre_role = cadre_role
            if enroll_date:
                s.enroll_date = enroll_date
            if phone:
                s.phone = phone
            if parent_name:
                s.parent_name = parent_name
            if parent_phone:
                s.parent_phone = parent_phone
            if address:
                s.address = address
            if notes:
                s.notes = notes
            updated += 1
        else:
            # 插入新学生
            s = Student(
                class_id=class_id,
                user_id=c.user_id, # Do NOT assign the admin user_id who is doing the import, assign it to the actual class owner
                school_id=c.school_id,
                name=name,
                student_number=student_number,
                gender=gender,
                cadre_role=cadre_role,
                enroll_date=enroll_date,
                phone=phone,
                parent_name=parent_name,
                parent_phone=parent_phone,
                address=address,
                notes=notes,
                tier="B",
                status="正常",
            )
            students_to_add.append(s)
            # 添加到映射中，防止 Excel 内有重复姓名导致多次创建
            student_name_map[name] = s
            created += 1

    if students_to_add:
        db.bulk_save_objects(students_to_add)
        c = db.query(Class).filter(Class.id == class_id).first()
        if c:
            c.student_count = (c.student_count or 0) + created
            
    # 因为有可能进行了更新操作，需要调用 commit
    db.commit()

    # 原接口返回的是 created 数量，这里为了兼容可以返回创建数量
    # 或者返回一个提示总数，但这里保持与前端兼容只返回数量
    return ApiResponse(data=created + updated)


@router.post("/import/global", response_model=ApiResponse[int])
def import_students_global(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        contents = file.file.read()
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件解析失败: {str(e)}")

    mapping = {
        'grade': ['年级'],
        'class_name': ['班级'],
        'student_number': ['学籍号', '学号', '编号', '序号'],
        'name': ['姓名', '名字', '学生姓名'],
        'gender': ['性别', '男/女'],
        'cadre_role': ['班干部', '职务', '角色'],
        'enroll_date': ['入学时间', '入学日期'],
        'phone': ['学生手机', '手机号', '联系电话'],
        'parent_name': ['家长姓名', '联系人'],
        'parent_phone': ['家长电话', '家长联系方式'],
        'address': ['家庭地址', '地址', '居住地'],
        'notes': ['备注', '说明']
    }
    
    found_cols = {}
    for attr, keywords in mapping.items():
        for col in df.columns:
            if any(k in str(col) for k in keywords):
                found_cols[attr] = col
                break
    
    if 'name' not in found_cols or 'grade' not in found_cols or 'class_name' not in found_cols:
        raise HTTPException(status_code=400, detail="未找到'年级'、'班级'或'姓名'列，请检查文件格式")

    # Group by grade and class name to batch insert
    created = 0
    
    # We will bulk query existing classes and students to avoid N+1 queries
    # First, collect all unique grade/class_name pairs
    class_keys = set()
    for _, row in df.iterrows():
        raw_grade = str(row.get(found_cols.get('grade', ''), "")).strip()
        class_name = str(row.get(found_cols.get('class_name', ''), "")).strip()
        if class_name.endswith('.0'):
            class_name = class_name[:-2]
        if raw_grade and raw_grade != "nan" and class_name and class_name != "nan":
            # Clean up grade
            grade = raw_grade
            if grade.startswith("小学"):
                pass
            elif grade in ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级"]:
                grade = "小学" + grade
            elif grade.startswith("初中"):
                grade = grade.replace("初中", "初")
                grade = grade.replace("一年级", "一").replace("二年级", "二").replace("三年级", "三")
            elif grade.startswith("高中"):
                grade = grade.replace("高中", "高")
                grade = grade.replace("一年级", "一").replace("二年级", "二").replace("三年级", "三")
            elif grade in ["初一", "初二", "初三", "高一", "高二", "高三"]:
                pass
            class_keys.add((grade, class_name))

    # Fetch all relevant classes in one go
    from sqlalchemy import or_, and_
    if not class_keys:
        return ApiResponse(data=0)

    class_conditions = [and_(Class.grade == g, Class.name == n) for g, n in class_keys]
    existing_classes = db.query(Class).filter(or_(*class_conditions)).all()
    class_map = {(c.grade, c.name): c for c in existing_classes}

    existing_students = db.query(Student).filter(
        Student.class_id.in_([c.id for c in existing_classes])
    ).all()
    student_name_map = {(s.class_id, s.name): s for s in existing_students}

    # We also need to check permissions, let's just do it in memory or skip it if user is admin
    # Assuming can_manage_students might be heavy, we can cache it per class
    permission_cache = {}

    students_to_add = []
    class_counts = {c.id: 0 for c in existing_classes}
    updated = 0
    created = 0

    for _, row in df.iterrows():
        raw_grade = str(row.get(found_cols.get('grade', ''), "")).strip()
        class_name = str(row.get(found_cols.get('class_name', ''), "")).strip()
        if class_name.endswith('.0'):
            class_name = class_name[:-2]
        name = str(row.get(found_cols.get('name', ''), "")).strip()
        
        if not name or name == "nan" or not raw_grade or raw_grade == "nan" or not class_name or class_name == "nan":
            continue
            
        grade = raw_grade
        if grade.startswith("小学"):
            pass
        elif grade in ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级"]:
            grade = "小学" + grade
        elif grade.startswith("初中"):
            grade = grade.replace("初中", "初")
            grade = grade.replace("一年级", "一").replace("二年级", "二").replace("三年级", "三")
        elif grade.startswith("高中"):
            grade = grade.replace("高中", "高")
            grade = grade.replace("一年级", "一").replace("二年级", "二").replace("三年级", "三")
        elif grade in ["初一", "初二", "初三", "高一", "高二", "高三"]:
            pass
            
        # Find the class from map
        c = class_map.get((grade, class_name))
        if not c:
            continue
            
        if c.id not in permission_cache:
            permission_cache[c.id] = can_manage_students(db, user_id, c.id)
            
        if not permission_cache[c.id]:
            continue

        student_number = ""
        if 'student_number' in found_cols:
            student_number = str(row.get(found_cols['student_number'], "")).strip()
            if student_number == "nan":
                student_number = ""

        gender = str(row.get(found_cols.get('gender', ''), "")).strip() if found_cols.get('gender') else "未知"
        cadre_role = str(row.get(found_cols.get('cadre_role', ''), "")).strip() if found_cols.get('cadre_role') else None
        enroll_date = str(row.get(found_cols.get('enroll_date', ''), "")).strip() if found_cols.get('enroll_date') else None
        phone = str(row.get(found_cols.get('phone', ''), "")).strip() if found_cols.get('phone') else None
        parent_name = str(row.get(found_cols.get('parent_name', ''), "")).strip() if found_cols.get('parent_name') else None
        parent_phone = str(row.get(found_cols.get('parent_phone', ''), "")).strip() if found_cols.get('parent_phone') else None
        address = str(row.get(found_cols.get('address', ''), "")).strip() if found_cols.get('address') else None
        notes = str(row.get(found_cols.get('notes', ''), "")).strip() if found_cols.get('notes') else None

        # Handle "nan" string conversion
        gender = None if gender == "nan" else gender
        cadre_role = None if cadre_role == "nan" else cadre_role
        enroll_date = None if enroll_date == "nan" else enroll_date
        phone = None if phone == "nan" else phone
        parent_name = None if parent_name == "nan" else parent_name
        parent_phone = None if parent_phone == "nan" else parent_phone
        address = None if address == "nan" else address
        notes = None if notes == "nan" else notes

        if (c.id, name) in student_name_map:
            s = student_name_map[(c.id, name)]
            if student_number:
                s.student_number = student_number
            if gender and gender != "未知":
                s.gender = gender
            if cadre_role:
                s.cadre_role = cadre_role
            if enroll_date:
                s.enroll_date = enroll_date
            if phone:
                s.phone = phone
            if parent_name:
                s.parent_name = parent_name
            if parent_phone:
                s.parent_phone = parent_phone
            if address:
                s.address = address
            if notes:
                s.notes = notes
            updated += 1
        else:
            s = Student(
                class_id=c.id,
                # Do NOT assign user_id from the admin who is importing to avoid making them the teacher/owner of this student's class automatically
                user_id="",
                school_id=c.school_id,
                name=name,
                student_number=student_number,
                gender=gender,
                cadre_role=cadre_role,
                enroll_date=enroll_date,
                phone=phone,
                parent_name=parent_name,
                parent_phone=parent_phone,
                address=address,
                notes=notes,
                tier="B",
                status="正常",
            )
            # Find the actual class owner/teacher to assign as user_id if needed, or leave it empty if your schema allows
            # For this project, if user_id is required, we should assign it to the class owner
            s.user_id = c.user_id
            
            students_to_add.append(s)
            student_name_map[(c.id, name)] = s
            class_counts[c.id] += 1
            created += 1

    if students_to_add:
        db.bulk_save_objects(students_to_add)
        for c in existing_classes:
            if class_counts[c.id] > 0:
                c.student_count = (c.student_count or 0) + class_counts[c.id]
                
    db.commit()

    return ApiResponse(data=created + updated)


@router.patch("/{student_id}", response_model=ApiResponse[StudentRecord])
def update_student(
    student_id: str,
    body: UpdateStudentRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="学生不存在")
    if not can_manage_students(db, user_id, s.class_id):
        raise HTTPException(status_code=403, detail="无权限管理该班级学生")

    if body.student_number is not None:
        num = (body.student_number or "").strip()
        if num:
            exists = (
                db.query(Student)
                .filter(Student.class_id == s.class_id, Student.student_number == num, Student.id != s.id)
                .first()
            )
            if exists:
                raise HTTPException(status_code=400, detail="该学号在本班已存在")
        s.student_number = num
    if body.name is not None:
        s.name = (body.name or "").strip() or s.name
    if body.gender is not None:
        s.gender = (body.gender or "").strip() or None
    if body.tier is not None:
        s.tier = (body.tier or "").strip() or None
    if body.status is not None:
        s.status = (body.status or "").strip() or None
    if body.birthday is not None:
        s.birthday = (body.birthday or "").strip() or None
    if body.phone is not None:
        s.phone = (body.phone or "").strip() or None
    if body.parent_name is not None:
        s.parent_name = (body.parent_name or "").strip() or None
    if body.parent_phone is not None:
        s.parent_phone = (body.parent_phone or "").strip() or None
    if body.address is not None:
        s.address = (body.address or "").strip() or None
    if body.enroll_date is not None:
        s.enroll_date = (body.enroll_date or "").strip() or None
    if body.seat_row is not None:
        s.seat_row = body.seat_row
    if body.seat_col is not None:
        s.seat_col = body.seat_col
    if body.cadre_role is not None:
        s.cadre_role = (body.cadre_role or "").strip() or None
    if body.notes is not None:
        s.notes = (body.notes or "").strip() or None

    db.commit()
    db.refresh(s)
    return ApiResponse(data=_orm_to_record(s))


@router.delete("/{student_id}", response_model=ApiResponse[None])
def delete_student(
    student_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="学生不存在")
    if not can_manage_students(db, user_id, s.class_id):
        raise HTTPException(status_code=403, detail="无权限管理该班级学生")
    c = db.query(Class).filter(Class.id == s.class_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="班级不存在")
    db.delete(s)
    c.student_count = max(0, (c.student_count or 1) - 1)
    db.commit()
    return ApiResponse(data=None)

@router.delete("/clear/{class_id}", response_model=ApiResponse[None])
def clear_students(
    class_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not can_manage_students(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="无权限管理该班级学生")
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="班级不存在")
    
    db.query(Student).filter(Student.class_id == class_id).delete()
    c.student_count = 0
    db.commit()
    return ApiResponse(data=None)
