import hashlib
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from app.config import settings

# bcrypt 只支持最多 72 字节，先做 SHA256 再 bcrypt，支持任意长度密码；且直接用 bcrypt 库避免 passlib 与新版 bcrypt 不兼容
def _to_bcrypt_input(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_input(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_to_bcrypt_input(plain), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# ---- H2：短时文件下载票（不把长期 JWT 放进 URL）----
_DOWNLOAD_TICKET_SCOPE = "download"


def create_download_ticket(user_id: str, resource: str) -> str:
    """为指定资源签发一次性短时下载票（默认 10 分钟过期，绑定 user+resource）。"""
    expire = datetime.utcnow() + timedelta(minutes=settings.DOWNLOAD_TICKET_EXPIRE_MINUTES)
    to_encode = {"sub": user_id, "scope": _DOWNLOAD_TICKET_SCOPE, "res": resource, "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_download_ticket(token: str, resource: str) -> Optional[str]:
    """校验下载票；仅在 scope 正确、资源路径匹配且未过期时返回 user_id，否则 None。"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("scope") != _DOWNLOAD_TICKET_SCOPE:
        return None
    if payload.get("res") != resource:
        return None
    return payload.get("sub")


def build_download_url(resource: str, user_id: str) -> str:
    """生成带短时下载票的文件直链（H2：不再依赖 URL 携带长期 JWT）。"""
    ticket = create_download_ticket(user_id, resource)
    return f"/api/v1/{resource}?ticket={ticket}"
