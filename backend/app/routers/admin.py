from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File, Form
import pandas as pd
import random
import string
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.user import User
from app.schemas.common import ApiResponse
from app.utils.school_access import (
    get_school_user_ids,
    get_user_school_id,
    is_school_admin,
)
from app.utils.security import hash_password, verify_password

router = APIRouter(prefix="/admin/users", tags=["admin"])


class AdminUserRecord(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    phone: Optional[str] = None
    teaching_subject: Optional[str] = None
    roles: List[str]
    job_title: Optional[str] = None
    personal_email: Optional[str] = None
    created_at: str


class AdminCreateUserRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None
    teaching_subject: Optional[str] = None
    roles: List[str]
    job_title: Optional[str] = None
    caller_password: str


class AdminUpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    teaching_subject: Optional[str] = None
    roles: Optional[List[str]] = None
    job_title: Optional[str] = None
    password: Optional[str] = None
    personal_email: Optional[str] = None
    caller_password: str


class AdminBatchDeleteRequest(BaseModel):
    user_ids: List[str]
    caller_password: str


def _check_admin_permission(db: Session, user_id: str) -> User:
    u = db.query(User).filter(User.id == user_id).first()
    if not u or not u.roles:
        raise HTTPException(status_code=403, detail="无权访问此接口")
    # D9：校级视野（系统管理员/子系统管理员/校级管理者/年级组长）可访问全局接口；
    # 数据按调用者 school scope 收敛（见 get_user_school_id / school_scope_class_ids）。
    if not is_school_admin(u):
        raise HTTPException(status_code=403, detail="仅系统管理员/子系统管理员/校级管理者/年级组长可操作")
    return u


def _to_record(u: User) -> AdminUserRecord:
    roles_str = getattr(u, "roles", None)
    roles_list = [r.strip() for r in roles_str.split(",") if r.strip()] if roles_str else ["任课教师"]
    return AdminUserRecord(
        id=str(u.id),
        email=u.email,
        display_name=u.display_name,
        phone=getattr(u, "phone", None),
        teaching_subject=getattr(u, "teaching_subject", None),
        roles=roles_list,
        job_title=getattr(u, "job_title", None),
        personal_email=getattr(u, "personal_email", None),
        created_at=str(getattr(u, "created_at", "")) if getattr(u, "created_at", None) else "",
    )


@router.get("", response_model=ApiResponse[List[AdminUserRecord]])
def list_users(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    caller = _check_admin_permission(db, user_id)
    users_q = db.query(User)
    # D9：school scope——调用者有 school_id 时只返回本校用户（school_id 空则全量，兼容现状）
    school_id = get_user_school_id(db, caller)
    if school_id:
        users_q = users_q.filter(User.id.in_(get_school_user_ids(db, school_id)))
    users = users_q.all()
    return ApiResponse(data=[_to_record(u) for u in users])


@router.post("", response_model=ApiResponse[AdminUserRecord])
def create_user(
    body: AdminCreateUserRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    caller = _check_admin_permission(db, user_id)
    if not verify_password(body.caller_password, caller.password_hash):
        raise HTTPException(status_code=403, detail="当前账户密码错误")
    
    caller_roles = [r.strip() for r in (caller.roles or "").split(",") if r.strip()]

    # 权限限制：子系统管理员不能创建系统管理员
    if "系统管理员" not in caller_roles and "系统管理员" in body.roles:
        raise HTTPException(status_code=403, detail="子系统管理员无权创建系统管理员账号")

    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="该账号/邮箱已存在")

    roles_str = ",".join(body.roles) if body.roles else "任课教师"
    new_user = User(
        email=body.email,
        password_hash=hash_password(body.password),  # C4: 只存哈希，不存明文
        display_name=body.display_name,
        teaching_subject=body.teaching_subject,
        roles=roles_str,
        job_title=body.job_title,
        personal_email=None,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return ApiResponse(data=_to_record(new_user))


@router.post("/batch-import", response_model=ApiResponse[dict])
async def batch_create_users(
    file: UploadFile = File(...),
    caller_password: str = Form(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    caller = _check_admin_permission(db, user_id)
    if not verify_password(caller_password, caller.password_hash):
        raise HTTPException(status_code=403, detail="当前账户密码错误")
    
    caller_roles = [r.strip() for r in (caller.roles or "").split(",") if r.strip()]

    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持上传 Excel 文件")

    try:
        contents = file.file.read()
        import io
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法解析 Excel 文件: {str(e)}")

    # 规范化表头（去除空格）
    df.columns = [str(c).strip() for c in df.columns]

    if "姓名" not in df.columns or "系统角色" not in df.columns:
        raise HTTPException(status_code=400, detail="Excel 中缺少必填表头：'姓名' 或 '系统角色'")

    # 缓存已存在的姓名，用于快速去重
    existing_names = {u.display_name for u in db.query(User.display_name).filter(User.display_name != None).all()}

    success_count = 0
    errors = []

    for index, row in df.iterrows():
        name = str(row.get("姓名", "")).strip()
        role_str = str(row.get("系统角色", "")).strip()
        job_title = str(row.get("岗位职责", "")).strip()
        account = str(row.get("账号", "")).strip()
        password = str(row.get("密码", "")).strip()

        if name in ("nan", "None", "") or role_str in ("nan", "None", ""):
            errors.append(f"第 {index + 2} 行：姓名或系统角色为空")
            continue

        # 检查姓名是否已存在，重复则直接跳过
        if name in existing_names:
            errors.append(f"第 {index + 2} 行：姓名 '{name}' 已存在，跳过导入")
            continue

        if job_title in ("nan", "None", ""):
            job_title = None

        if password in ("nan", "None", ""):
            password = "123456"

        if account in ("nan", "None", ""):
            # 随机生成账号，并确保数据库中唯一
            while True:
                random_str = "".join(random.choices(string.ascii_lowercase, k=5))
                account = f"{random_str}@pgj.com"
                if not db.query(User).filter(User.email == account).first():
                    break
        else:
            # 检查用户提供的账号是否已存在
            existing_user = db.query(User).filter(User.email == account).first()
            if existing_user:
                errors.append(f"第 {index + 2} 行：账号 '{account}' 已存在")
                continue

        # 角色解析
        roles_list = [r.strip() for r in role_str.split(",") if r.strip()]
        if not roles_list:
            roles_list = ["任课教师"]

        if "系统管理员" not in caller_roles and "系统管理员" in roles_list:
            errors.append(f"第 {index + 2} 行：子系统管理员无权创建系统管理员")
            continue

        try:
            new_user = User(
                email=account,
                password_hash=hash_password(password),  # C4: 只存哈希，不存明文
                display_name=name,
                roles=",".join(roles_list),
                job_title=job_title,
                personal_email=None,
            )
            db.add(new_user)
            db.commit()
            existing_names.add(name)  # 成功导入后更新姓名缓存
            success_count += 1
        except Exception as e:
            db.rollback()
            errors.append(f"第 {index + 2} 行：保存失败 ({str(e)})")

    msg = f"成功导入 {success_count} 个账号。"
    if errors:
        msg += f" 失败 {len(errors)} 个（请检查数据是否重复或格式错误）。"

    return ApiResponse(data={"success_count": success_count, "errors": errors}, message=msg)

@router.patch("/{target_id}", response_model=ApiResponse[AdminUserRecord])
def update_user(
    target_id: str,
    body: AdminUpdateUserRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    caller = _check_admin_permission(db, user_id)
    if not verify_password(body.caller_password, caller.password_hash):
        raise HTTPException(status_code=403, detail="当前账户密码错误")
    caller_roles = [r.strip() for r in (caller.roles or "").split(",") if r.strip()]

    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标账号不存在")

    target_roles = [r.strip() for r in (target.roles or "").split(",") if r.strip()]

    if "系统管理员" in target_roles:
        raise HTTPException(status_code=403, detail="系统管理员账号不允许被修改")

    if "系统管理员" not in caller_roles:
        # 子系统管理员操作
        if "系统管理员" in target_roles:
            raise HTTPException(status_code=403, detail="子系统管理员无权修改系统管理员的账号信息")
        if body.roles and "系统管理员" in body.roles:
            raise HTTPException(status_code=403, detail="无权将账号角色修改为系统管理员")

    if body.display_name is not None:
        target.display_name = body.display_name
    if body.teaching_subject is not None:
        target.teaching_subject = body.teaching_subject
    if body.job_title is not None:
        target.job_title = body.job_title
    if body.roles is not None:
        target.roles = ",".join(body.roles)
    if body.password:
        target.password_hash = hash_password(body.password)  # C4: 只存哈希，不存明文
    if body.personal_email is not None:
        target.personal_email = body.personal_email.strip() if body.personal_email.strip() else None

    db.commit()
    db.refresh(target)
    return ApiResponse(data=_to_record(target))


class AdminPasswordVerifyRequest(BaseModel):
    caller_password: str


@router.delete("/{target_id}", response_model=ApiResponse[None])
def delete_user(
    target_id: str,
    body: AdminPasswordVerifyRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    caller = _check_admin_permission(db, user_id)
    if not verify_password(body.caller_password, caller.password_hash):
        raise HTTPException(status_code=403, detail="当前账户密码错误")
    caller_roles = [r.strip() for r in (caller.roles or "").split(",") if r.strip()]

    if target_id == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标账号不存在")

    target_roles = [r.strip() for r in (target.roles or "").split(",") if r.strip()]
    if "系统管理员" in target_roles:
        raise HTTPException(status_code=403, detail="系统管理员账号不允许被删除")
    if "系统管理员" not in caller_roles and "系统管理员" in target_roles:
        raise HTTPException(status_code=403, detail="子系统管理员无权删除系统管理员账号")

    db.delete(target)
    db.commit()
    return ApiResponse(data=None)


@router.post("/batch-delete", response_model=ApiResponse[dict])
def batch_delete_users(
    body: AdminBatchDeleteRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    caller = _check_admin_permission(db, user_id)
    if not verify_password(body.caller_password, caller.password_hash):
        raise HTTPException(status_code=403, detail="当前账户密码错误")

    target_ids = list(dict.fromkeys(str(value).strip() for value in body.user_ids if str(value).strip()))
    if not target_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个要删除的账号")
    if len(target_ids) > 500:
        raise HTTPException(status_code=400, detail="单次最多删除 500 个账号")
    if user_id in target_ids:
        raise HTTPException(status_code=400, detail="不能删除自己")

    targets = db.query(User).filter(User.id.in_(target_ids)).all()
    targets_by_id = {str(target.id): target for target in targets}
    missing_ids = [target_id for target_id in target_ids if target_id not in targets_by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"有 {len(missing_ids)} 个目标账号不存在，请刷新列表后重试")

    protected_names = []
    for target in targets:
        target_roles = [r.strip() for r in (target.roles or "").split(",") if r.strip()]
        if "系统管理员" in target_roles:
            protected_names.append(target.display_name or target.email)
    if protected_names:
        raise HTTPException(
            status_code=403,
            detail=f"系统管理员账号不允许被删除：{'、'.join(protected_names)}",
        )

    try:
        for target_id in target_ids:
            db.delete(targets_by_id[target_id])
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="批量删除账号失败，请稍后重试")

    return ApiResponse(data={"deleted_count": len(target_ids), "deleted_ids": target_ids})


# C4：已删除 view-password 明文密码查看接口（明文密码不再存储）
