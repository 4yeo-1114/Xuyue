import logging
import threading
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user_id
from app.grading.user_paths import ensure_user_grading_layout
from app.models.class_model import Class
from app.models.class_teacher import ClassTeacher
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LocaleUpdateRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.schemas.common import ApiResponse
from app.services.multi_project_settings import is_multi_project_admin_email
from app.utils.security import create_access_token, decode_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# M4：登录限流/锁定（内存实现，不引外部依赖）
_LOGIN_LOCK = threading.Lock()
# key -> [失败时间戳]；key = email 或 ip
_LOGIN_FAILURES: dict[str, list[float]] = {}
_LOGIN_WINDOW_SECONDS = 15 * 60        # 15 分钟窗口
_LOGIN_MAX_FAILURES = 5                 # 窗口内最多失败次数
_LOGIN_IP_MAX_PER_MINUTE = 20           # 单 IP 每分钟尝试上限（防分布式爆破）


def _prune_login_failures(key: str) -> None:
    now = time.time()
    _LOGIN_FAILURES[key] = [t for t in _LOGIN_FAILURES.get(key, []) if now - t < _LOGIN_WINDOW_SECONDS]
    if not _LOGIN_FAILURES[key]:
        _LOGIN_FAILURES.pop(key, None)


def _is_login_locked(email: str, ip: str) -> bool:
    with _LOGIN_LOCK:
        for key in (email.lower(), ip):
            _prune_login_failures(key)
            if len(_LOGIN_FAILURES.get(key, [])) >= _LOGIN_MAX_FAILURES:
                return True
    return False


def _record_login_failure(email: str, ip: str) -> None:
    now = time.time()
    with _LOGIN_LOCK:
        for key in (email.lower(), ip):
            _prune_login_failures(key)
            _LOGIN_FAILURES.setdefault(key, []).append(now)


def _clear_login_failures(email: str, ip: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.pop(email.lower(), None)
        _LOGIN_FAILURES.pop(ip, None)


def _client_ip(request: Request) -> str:
    try:
        return (request.client.host or "") if request.client else ""
    except Exception:
        return ""


def _validate_loose_email(raw: str) -> str:
    """宽松邮箱校验：演示环境允许保留域（如 @grade.local），仅要求非空且含 @。"""
    email = (raw or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    return email


# ── 免审核自助注册（演示环境）──────────────────────────────
REGISTER_ROLE_WHITELIST = ("任课教师", "班主任", "年级组长", "校级管理者", "系统管理员")
DEMO_SUBJECTS = ("语文", "数学", "英语", "科学")
DEMO_CLASS_PREFIX = "演示-"

# 注册限流（内存实现，独立于登录锁定）
_REGISTER_LOCK = threading.Lock()
# ip -> [成功注册时间戳]
_REGISTER_COUNTS: dict[str, list[float]] = {}
_REGISTER_WINDOW_SECONDS = 60 * 60          # 1 小时窗口
_REGISTER_MAX_PER_IP = 5                     # 单 IP 每小时最多注册次数


def _prune_register_counts(ip: str) -> None:
    now = time.time()
    _REGISTER_COUNTS[ip] = [
        t for t in _REGISTER_COUNTS.get(ip, []) if now - t < _REGISTER_WINDOW_SECONDS
    ]
    if not _REGISTER_COUNTS[ip]:
        _REGISTER_COUNTS.pop(ip, None)


def _register_locked(ip: str) -> bool:
    with _REGISTER_LOCK:
        _prune_register_counts(ip)
        return len(_REGISTER_COUNTS.get(ip, [])) >= _REGISTER_MAX_PER_IP


def _record_register(ip: str) -> None:
    now = time.time()
    with _REGISTER_LOCK:
        _prune_register_counts(ip)
        _REGISTER_COUNTS.setdefault(ip, []).append(now)


def _pick_demo_class(db: Session) -> Class:
    """从演示班中挑选 class_teachers 绑定数最少的班（负载均衡），池空抛 503。"""
    cls = (
        db.query(Class)
        .outerjoin(ClassTeacher, ClassTeacher.class_id == Class.id)
        .filter(Class.name.like(f"{DEMO_CLASS_PREFIX}%"))
        .group_by(Class.id)
        .order_by(func.count(ClassTeacher.id).asc(), Class.name.asc())
        .first()
    )
    if cls is None:
        raise HTTPException(status_code=503, detail="演示数据未初始化")
    return cls


@router.api_route("/login", methods=["OPTIONS"])
def auth_options():
    return {}


def _normalize_ui_locale(raw: Optional[str]) -> str:
    v = str(raw or "zh").strip().lower()
    return "en" if v == "en" else "zh"


def user_to_response(user: User) -> UserResponse:
    roles_str = getattr(user, "roles", None)
    roles_list = [r.strip() for r in roles_str.split(",") if r.strip()] if roles_str else ["任课教师"]

    subject = getattr(user, "teaching_subject", None)
    if subject == "__CLEAR__":
        subject = None

    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        phone=getattr(user, "phone", None),
        teaching_subject=subject,
        roles=roles_list,
        job_title=getattr(user, "job_title", None),
        personal_email=getattr(user, "personal_email", None),
        multi_project_admin=is_multi_project_admin_email(user.email or ""),
        ui_locale=_normalize_ui_locale(getattr(user, "ui_locale", None)),
    )


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """M4：登录限流 + 失败锁定 + 失败审计日志。"""
    ip = _client_ip(request)
    email = _validate_loose_email(data.email)
    if _is_login_locked(email, ip):
        logging.warning("登录被锁定: email=%s ip=%s（失败次数过多）", email, ip)
        raise HTTPException(status_code=429, detail="尝试次数过多，请 15 分钟后再试")
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(data.password, user.password_hash):
        _record_login_failure(email, ip)
        logging.warning("登录失败: email=%s ip=%s", email, ip)
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    _clear_login_failures(email, ip)
    ensure_user_grading_layout(user.id)
    token = create_access_token(subject=user.id)
    logging.info("登录成功: user_id=%s ip=%s", user.id, ip)
    return TokenResponse(access_token=token, user=user_to_response(user))


@router.post("/register", response_model=TokenResponse)
def register(data: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """免审核自助注册测试账号：注册成功即返回 token（自动登录），并自动获得对应层级演示数据权限。"""
    if not getattr(settings, "ALLOW_PUBLIC_REGISTRATION", True):
        raise HTTPException(status_code=403, detail="暂未开放自助注册")

    ip = _client_ip(request)
    if _register_locked(ip):
        raise HTTPException(status_code=429, detail="注册过于频繁，请 1 小时后再试")

    email = _validate_loose_email(data.email)

    # 邮箱去重（大小写不敏感）
    exists = (
        db.query(User)
        .filter(func.lower(User.email) == email.lower())
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="该邮箱已被注册")

    # 科目校验：任课教师必填且须在演示科目内；其他角色不得带科目
    if data.role == "任课教师":
        subject = (data.teaching_subject or "").strip()
        if not subject:
            raise HTTPException(status_code=400, detail="任课教师必须选择科目")
        if subject not in DEMO_SUBJECTS:
            raise HTTPException(status_code=400, detail=f"科目仅支持：{'、'.join(DEMO_SUBJECTS)}")
    else:
        if data.teaching_subject:
            raise HTTPException(status_code=400, detail="该角色无需绑定科目")
        subject = None

    display_name = (data.display_name or "").strip() or None
    new_user = User(
        email=email,
        password_hash=hash_password(data.password),
        display_name=display_name,
        roles=data.role,
        teaching_subject=subject,
    )
    db.add(new_user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该邮箱已被注册")

    # 任课教师/班主任自动绑定演示班（年级组长/校级管理者/系统管理员全局可见，不绑班）
    if data.role in ("任课教师", "班主任"):
        demo_class = _pick_demo_class(db)
        db.add(
            ClassTeacher(
                class_id=demo_class.id,
                user_id=new_user.id,
                role="head" if data.role == "班主任" else "teacher",
                subject=subject if data.role == "任课教师" else None,
            )
        )

    db.commit()
    _record_register(ip)
    ensure_user_grading_layout(new_user.id)
    token = create_access_token(subject=new_user.id)
    logging.info("自助注册成功: user_id=%s role=%s ip=%s", new_user.id, data.role, ip)
    return TokenResponse(access_token=token, token_type="bearer", user=user_to_response(new_user))


@router.get("/me", response_model=UserResponse)
def get_me(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.replace("Bearer ", "").strip()
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="登录已过期或无效")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    ensure_user_grading_layout(user.id)
    return user_to_response(user)


def _minimal_user_to_response(user: User) -> UserResponse:
    """H1：最小化字段——不暴露 personal_email/phone/job_title 等敏感信息。"""
    roles_str = getattr(user, "roles", None)
    roles_list = [r.strip() for r in roles_str.split(",") if r.strip()] if roles_str else ["任课教师"]
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        teaching_subject=getattr(user, "teaching_subject", None),
        roles=roles_list,
        multi_project_admin=is_multi_project_admin_email(user.email or ""),
        ui_locale=_normalize_ui_locale(getattr(user, "ui_locale", None)),
    )


@router.get("/users/all", response_model=ApiResponse[List[UserResponse]])
def get_all_users(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """H1：仅系统管理员/子系统管理员可列出全部用户，且返回最小化字段。"""
    me = db.query(User).filter(User.id == user_id).first()
    if not me:
        raise HTTPException(status_code=401, detail="用户不存在")
    roles = [r.strip() for r in (me.roles or "").split(",") if r.strip()]
    if "系统管理员" not in roles and "子系统管理员" not in roles:
        raise HTTPException(status_code=403, detail="仅系统管理员和子系统管理员可访问")
    users = db.query(User).all()
    return ApiResponse(data=[_minimal_user_to_response(u) for u in users])


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UpdateProfileRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.replace("Bearer ", "").strip()
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="登录已过期或无效")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or None
    if body.phone is not None:
        user.phone = body.phone.strip() or None
    if body.teaching_subject is not None:
        if body.teaching_subject == "__CLEAR__":
            user.teaching_subject = None
        else:
            user.teaching_subject = body.teaching_subject.strip() or None
    if body.job_title is not None:
        user.job_title = body.job_title.strip() or None
    if body.personal_email is not None:
        user.personal_email = body.personal_email.strip() if body.personal_email.strip() else None
    db.commit()
    db.refresh(user)
    return user_to_response(user)


@router.patch("/locale", response_model=UserResponse)
def update_locale(
    body: LocaleUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    locale = _normalize_ui_locale(body.locale)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    user.ui_locale = locale
    db.commit()
    db.refresh(user)
    return user_to_response(user)


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.replace("Bearer ", "").strip()
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="登录已过期或无效")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len((body.new_password or "").strip()) < 6:
        raise HTTPException(status_code=400, detail="新密码至少6位")
    # C4：只存密码哈希，不再写入 plain_password 明文列
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
