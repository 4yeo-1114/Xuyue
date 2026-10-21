import logging
import secrets
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
from app.models.user import User
from app.schemas.auth import (
    BindPhoneRequest,
    ChangePasswordRequest,
    LocaleUpdateRequest,
    LoginRequest,
    PhoneLoginRequest,
    RegisterRequest,
    SendCodeRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.services import verification
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


def _bearer_user_id(request: Request) -> Optional[str]:
    """从 Authorization: Bearer <token> 解析 user_id；无效/缺失返回 None（不抛异常）。"""
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "").strip()
    return decode_access_token(token)


def _validate_loose_email(raw: str) -> str:
    """宽松邮箱校验：演示环境允许保留域（如 @grade.local），仅要求非空且含 @。"""
    email = (raw or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    return email


def _normalize_phone(raw: str) -> str:
    """手机号规范化：去空格/横线；要求为 11 位大陆手机号（1 开头）。"""
    phone = (raw or "").strip().replace(" ", "").replace("-", "")
    if len(phone) != 11 or not phone.isdigit() or not phone.startswith("1"):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    return phone


# ── 免审核自助注册（演示环境）──────────────────────────────
# 可注册角色白名单的闸门在 app/schemas/auth.py 的 RegisterRole（Literal，Pydantic 校验阶段拦截）。
# 此处不再保留第二份角色清单：两个事实源必然分叉。
#
# 独立老师（不挂靠学校的个体老师）经此注册进来后**不绑定任何班级**：注册完就是一个没有班的
# 老师，自己去建班加学生。故此处不再挑选演示班（原 _pick_demo_class / DEMO_CLASS_PREFIX 已删）。
#
# 科目自由填写：长度上限取两条相关列定义中**较小**者 ——
# users.teaching_subject = String(32)、class_teachers.subject = String(32) ⇒ 32。
MAX_TEACHING_SUBJECT_LEN = 32
MAX_TEACHING_GRADE_LEN = 32

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


def _create_phone_user(db: Session, phone: str, ip: str) -> User:
    """手机号未注册时自动注册（任课教师）：合成唯一邮箱 + 随机密码（用户不持有）。

    与邮箱自助注册同受 ALLOW_PUBLIC_REGISTRATION 开关与注册限频约束。
    """
    if not getattr(settings, "ALLOW_PUBLIC_REGISTRATION", True):
        raise HTTPException(status_code=403, detail="暂未开放自助注册")
    if _register_locked(ip):
        raise HTTPException(status_code=429, detail="注册过于频繁，请 1 小时后再试")

    email = f"{phone}@phone.local"
    new_user = User(
        email=email,
        password_hash=hash_password(secrets.token_hex(16)),
        display_name=f"手机用户{phone[-4:]}",
        phone=phone,
        roles="任课教师",
    )
    db.add(new_user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该手机号已注册")
    db.commit()
    db.refresh(new_user)
    _record_register(ip)
    logging.info("手机号自助注册成功: user_id=%s phone=%s ip=%s", new_user.id, phone, ip)
    return new_user


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
        teaching_grade=getattr(user, "teaching_grade", None),
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
    """免审核自助注册（独立老师入口）：注册成功即返回 token（自动登录）。

    不绑定任何班级、不预置演示数据 —— 注册者自己建班、自己加学生。
    """
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

    # 合规：注册前必须校验邮箱验证码（真实邮箱验证）。老账号不追溯，仅影响新注册。
    if not verification.verify_code(db, email, "email", "register", data.email_code):
        raise HTTPException(status_code=400, detail="邮箱验证码错误或已过期")

    # 科目：可选、自由填写（独立老师可能教任意科目，不做白名单）；只保留 strip 与长度上限
    subject = (data.teaching_subject or "").strip() or None
    if subject and len(subject) > MAX_TEACHING_SUBJECT_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"科目名称过长（最多 {MAX_TEACHING_SUBJECT_LEN} 个字符）",
        )

    # 年级：可选、自由填写（与科目同口径）；只保留 strip 与长度上限
    grade = (data.teaching_grade or "").strip() or None
    if grade and len(grade) > MAX_TEACHING_GRADE_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"年级名称过长（最多 {MAX_TEACHING_GRADE_LEN} 个字符）",
        )

    display_name = (data.display_name or "").strip() or None
    new_user = User(
        email=email,
        password_hash=hash_password(data.password),
        display_name=display_name,
        roles=data.role,
        teaching_subject=subject,
        teaching_grade=grade,
    )
    db.add(new_user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该邮箱已被注册")

    # 不绑定任何班级：独立老师注册完就是一个没有班的老师，自己去建班加学生。
    db.commit()
    _record_register(ip)
    ensure_user_grading_layout(new_user.id)
    token = create_access_token(subject=new_user.id)
    logging.info("自助注册成功: user_id=%s role=%s ip=%s", new_user.id, data.role, ip)
    return TokenResponse(access_token=token, token_type="bearer", user=user_to_response(new_user))


@router.post("/send-code")
def send_code(data: SendCodeRequest, request: Request, db: Session = Depends(get_db)):
    """签发验证码（免登录，但限频）。

    支持的组合（其它组合 400）：
    - email + register：注册前邮箱验证（先查未注册，409 已注册）。
    - sms + login：手机号验证码登录/注册（未注册也能发码，登录时自动注册）。
    - sms + bind：登录态绑定手机号（需授权头，先查未被他人占用，409 已占用）。

    fail-closed：SMTP / 阿里云短信任一未配置时返回 501「通道未配置」。
    """
    if data.channel == "email":
        if data.purpose != "register":
            raise HTTPException(status_code=400, detail="不支持的邮箱验证码用途")
        email = _validate_loose_email(data.target)
        exists = db.query(User).filter(func.lower(User.email) == email.lower()).first()
        if exists:
            raise HTTPException(status_code=409, detail="该邮箱已被注册")
        target = email
    elif data.channel == "sms":
        phone = _normalize_phone(data.target)
        if data.purpose == "bind":
            auth = _bearer_user_id(request)
            if not auth:
                raise HTTPException(status_code=401, detail="未登录")
            occupied = db.query(User).filter(User.phone == phone, User.id != auth).first()
            if occupied:
                raise HTTPException(status_code=409, detail="该手机号已被其他账号绑定")
        elif data.purpose != "login":
            raise HTTPException(status_code=400, detail="不支持的短信验证码用途")
        # purpose == "login"：手机号登录/注册合一，未注册也能发码（登录时自动注册）
        target = phone
    else:
        raise HTTPException(status_code=400, detail="未知发送渠道")

    try:
        verification.issue_code(db, target, data.channel, data.purpose)
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except RuntimeError as e:
        # fail-closed：通道未配置 / 发送失败，明确报错，不静默
        raise HTTPException(status_code=501, detail=str(e))
    return {"ok": True}


@router.post("/phone-login", response_model=TokenResponse)
def phone_login(data: PhoneLoginRequest, request: Request, db: Session = Depends(get_db)):
    """手机号 + 短信验证码登录/注册：未注册的手机号验证通过后自动创建账号并登录。"""
    phone = _normalize_phone(data.phone)
    ip = _client_ip(request)
    if _is_login_locked(phone, ip):
        raise HTTPException(status_code=429, detail="尝试次数过多，请 15 分钟后再试")

    if not verification.verify_code(db, phone, "sms", "login", data.code):
        _record_login_failure(phone, ip)
        raise HTTPException(status_code=401, detail="验证码错误或已过期")

    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = _create_phone_user(db, phone, ip)

    _clear_login_failures(phone, ip)
    ensure_user_grading_layout(user.id)
    token = create_access_token(subject=user.id)
    logging.info("手机号登录成功: user_id=%s ip=%s", user.id, ip)
    return TokenResponse(access_token=token, token_type="bearer", user=user_to_response(user))


@router.post("/bind-phone", response_model=UserResponse)
def bind_phone(data: BindPhoneRequest, request: Request, db: Session = Depends(get_db)):
    """登录态绑定手机号（先验证码，再应用层查重，防重复绑定）。"""
    user_id = _bearer_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    phone = _normalize_phone(data.phone)

    occupied = db.query(User).filter(User.phone == phone, User.id != user_id).first()
    if occupied:
        raise HTTPException(status_code=409, detail="该手机号已被其他账号绑定")

    if not verification.verify_code(db, phone, "sms", "bind", data.code):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    user.phone = phone
    db.commit()
    db.refresh(user)
    return user_to_response(user)


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
        teaching_grade=getattr(user, "teaching_grade", None),
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
    if body.teaching_grade is not None:
        user.teaching_grade = body.teaching_grade.strip() or None
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
