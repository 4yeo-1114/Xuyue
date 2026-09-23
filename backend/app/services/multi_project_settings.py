# -*- coding: utf-8 -*-
"""多项目设置：项目名称与数据库配置档案（本地 JSON + .env 切换）。"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import create_engine, text

from app.config import Settings, _get_env_file, settings

DEFAULT_PROJECT_NAME = "叙阅"


def is_multi_project_admin_email(email: str) -> bool:
    """H5：多项目超管邮箱从环境变量 MULTI_PROJECT_ADMIN_EMAILS 注入（逗号分隔），不再硬编码。"""
    return (email or "").strip().lower() in settings.multi_project_admin_emails


def _resolve_db_password(profile: dict) -> str:
    """C3：支持从环境变量读取数据库密码。
    若 password 为空或形如 env:VAR_NAME，则从对应环境变量取值；
    否则返回配置里保存的密码（历史兼容）。
    """
    raw = str(profile.get("password") or "").strip()
    if raw.startswith("env:"):
        var_name = raw[len("env:"):].strip()
        val = os.environ.get(var_name, "")
        if not val:
            raise ValueError(f"环境变量 {var_name} 未配置，无法解析数据库密码")
        return val
    return raw


_DB_ENV_KEYS = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")


def _settings_json_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parents[2]
    return base / "multi_project_settings.json"


def _env_file_path() -> Path:
    return Path(_get_env_file())


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_payload() -> dict[str, Any]:
    settings = Settings()
    profile_id = str(uuid.uuid4())
    return {
        "project_name": DEFAULT_PROJECT_NAME,
        "active_db_profile_id": profile_id,
        "db_profiles": [
            {
                "id": profile_id,
                "name": "当前环境",
                "host": settings.DB_HOST,
                "port": settings.DB_PORT,
                "user": settings.DB_USER,
                "password": settings.DB_PASSWORD,
                "database": settings.DB_NAME,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        ],
        "updated_at": _now_iso(),
    }


def load_settings() -> dict[str, Any]:
    path = _settings_json_path()
    if not path.is_file():
        data = _default_payload()
        save_settings(data)
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    data = _default_payload()
    data.update({k: v for k, v in raw.items() if k in ("project_name", "active_db_profile_id", "updated_at")})
    profiles = raw.get("db_profiles")
    if isinstance(profiles, list) and profiles:
        data["db_profiles"] = profiles
    if raw.get("active_db_profile_id"):
        data["active_db_profile_id"] = raw["active_db_profile_id"]
    if not data.get("project_name"):
        data["project_name"] = DEFAULT_PROJECT_NAME
    return data


def save_settings(data: dict[str, Any]) -> None:
    path = _settings_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_project_name() -> str:
    name = str(load_settings().get("project_name") or "").strip()
    return name or DEFAULT_PROJECT_NAME


def set_project_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("项目名称不能为空")
    if len(cleaned) > 32:
        raise ValueError("项目名称不能超过 32 个字符")
    data = load_settings()
    data["project_name"] = cleaned
    save_settings(data)
    return cleaned


def _find_profile(data: dict[str, Any], profile_id: str) -> Optional[dict[str, Any]]:
    for item in data.get("db_profiles") or []:
        if isinstance(item, dict) and str(item.get("id")) == profile_id:
            return item
    return None


def mask_password(password: str) -> str:
    if not password:
        return ""
    if len(password) <= 2:
        return "*" * len(password)
    return password[:1] + "*" * (len(password) - 2) + password[-1]


def serialize_db_profile(profile: dict[str, Any], *, mask_secret: bool = True) -> dict[str, Any]:
    pwd = str(profile.get("password") or "")
    return {
        "id": str(profile.get("id") or ""),
        "name": str(profile.get("name") or ""),
        "host": str(profile.get("host") or ""),
        "port": int(profile.get("port") or 3306),
        "user": str(profile.get("user") or ""),
        "password": mask_password(pwd) if mask_secret else pwd,
        "database": str(profile.get("database") or ""),
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
    }


def list_db_profiles(*, mask_secret: bool = True) -> list[dict[str, Any]]:
    data = load_settings()
    active_id = str(data.get("active_db_profile_id") or "")
    items: list[dict[str, Any]] = []
    for raw in data.get("db_profiles") or []:
        if not isinstance(raw, dict):
            continue
        item = serialize_db_profile(raw, mask_secret=mask_secret)
        item["is_active"] = item["id"] == active_id
        items.append(item)
    return items


def upsert_db_profile(
    *,
    profile_id: Optional[str],
    name: str,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> dict[str, Any]:
    cleaned_name = (name or "").strip()
    cleaned_host = (host or "").strip()
    cleaned_user = (user or "").strip()
    cleaned_db = (database or "").strip()
    if not cleaned_name:
        raise ValueError("配置名称不能为空")
    if not cleaned_host:
        raise ValueError("数据库地址不能为空")
    if not cleaned_user:
        raise ValueError("数据库账号不能为空")
    if not cleaned_db:
        raise ValueError("数据库名称不能为空")
    if port <= 0 or port > 65535:
        raise ValueError("端口无效")

    data = load_settings()
    profiles: list[dict] = list(data.get("db_profiles") or [])
    now = _now_iso()

    if profile_id:
        target = _find_profile(data, profile_id)
        if not target:
            raise ValueError("配置项不存在")
        target["name"] = cleaned_name
        target["host"] = cleaned_host
        target["port"] = int(port)
        target["user"] = cleaned_user
        if (password or "").strip():
            target["password"] = password.strip()
        target["database"] = cleaned_db
        target["updated_at"] = now
        saved = target
    else:
        saved = {
            "id": str(uuid.uuid4()),
            "name": cleaned_name,
            "host": cleaned_host,
            "port": int(port),
            "user": cleaned_user,
            "password": (password or "").strip(),
            "database": cleaned_db,
            "created_at": now,
            "updated_at": now,
        }
        if not saved["password"]:
            raise ValueError("数据库密码不能为空")
        profiles.append(saved)

    data["db_profiles"] = profiles
    if not data.get("active_db_profile_id") and profiles:
        data["active_db_profile_id"] = profiles[0]["id"]
    save_settings(data)
    return serialize_db_profile(saved, mask_secret=True)


def delete_db_profile(profile_id: str) -> None:
    data = load_settings()
    profiles = [p for p in (data.get("db_profiles") or []) if str(p.get("id")) != profile_id]
    if len(profiles) == len(data.get("db_profiles") or []):
        raise ValueError("配置项不存在")
    if not profiles:
        raise ValueError("至少保留一个数据库配置")
    data["db_profiles"] = profiles
    if str(data.get("active_db_profile_id") or "") == profile_id:
        data["active_db_profile_id"] = profiles[0]["id"]
    save_settings(data)


def test_db_connection(host: str, port: int, user: str, password: str, database: str) -> tuple[bool, str]:
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 8})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "数据库连接成功"
    except Exception as e:
        return False, f"连接失败：{e}"
    finally:
        engine.dispose()


def verify_db_schema_ready(host: str, port: int, user: str, password: str, database: str) -> tuple[bool, str]:
    """切换前探测目标库是否具备 users 表（切换后会自动补列）。"""
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 8})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            row = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = :db AND table_name = 'users'"
                ),
                {"db": database},
            ).scalar()
            if not row:
                return False, "目标库缺少 users 表，请先初始化数据库或确认库名正确"
        return True, "数据库结构检查通过"
    except Exception as e:
        return False, f"结构检查失败：{e}"
    finally:
        engine.dispose()


def _update_env_file(host: str, port: int, user: str, password: str, database: str) -> None:
    env_path = _env_file_path()
    values = {
        "DB_HOST": host,
        "DB_PORT": str(port),
        "DB_USER": user,
        "DB_PASSWORD": password,
        "DB_NAME": database,
    }
    lines: list[str] = []
    seen: set[str] = set()
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    out: list[str] = []
    for line in lines:
        matched = False
        for key, val in values.items():
            if re.match(rf"^\s*{re.escape(key)}\s*=", line):
                out.append(f"{key}={val}")
                seen.add(key)
                matched = True
                break
        if not matched:
            out.append(line)

    for key, val in values.items():
        if key not in seen:
            out.append(f"{key}={val}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def apply_db_profile(profile_id: str) -> dict[str, Any]:
    data = load_settings()
    profile = _find_profile(data, profile_id)
    if not profile:
        raise ValueError("配置项不存在")

    host = str(profile.get("host") or "").strip()
    port = int(profile.get("port") or 3306)
    user = str(profile.get("user") or "").strip()
    password = _resolve_db_password(profile)  # C3: 支持 env:VAR_NAME 注入
    database = str(profile.get("database") or "").strip()

    ok, msg = test_db_connection(host, port, user, password, database)
    if not ok:
        raise ValueError(msg)
    schema_ok, schema_msg = verify_db_schema_ready(host, port, user, password, database)
    if not schema_ok:
        raise ValueError(schema_msg)

    _update_env_file(host, port, user, password, database)

    import app.config as config_module
    import app.database as database_module

    config_module.settings = Settings()
    database_module.reload_database_engine(config_module.settings)

    # 切换后再次探测，确保 ORM 可正常访问 users 表
    probe_db = database_module.SessionLocal()
    try:
        probe_db.execute(text("SELECT email FROM users LIMIT 1"))
    except Exception as e:
        raise ValueError(f"数据库切换后结构同步失败：{e}") from e
    finally:
        probe_db.close()

    data["active_db_profile_id"] = profile_id
    save_settings(data)

    active = serialize_db_profile(profile, mask_secret=True)
    active["is_active"] = True
    return {
        "message": "数据库已切换，后续请求将使用新连接",
        "active_profile": active,
    }


def get_active_db_profile_summary() -> Optional[dict[str, Any]]:
    data = load_settings()
    active_id = str(data.get("active_db_profile_id") or "")
    if not active_id:
        return None
    profile = _find_profile(data, active_id)
    if not profile:
        return None
    item = serialize_db_profile(profile, mask_secret=True)
    item["is_active"] = True
    return item
