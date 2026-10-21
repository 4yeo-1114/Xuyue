import os
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.system_settings import SystemSettings


DEFAULT_QWEN_MODEL = "qwen3.7-plus"

# 视觉模型：旧 qwen-vl-* 系列 2026-10 已在 DashScope 下线（404 Model not exist；
# qwen-vl-max-latest/qwen2.5-vl-* 对当前 key 403），统一走 qwen3-vl 系。
DEFAULT_VL_MODEL = "qwen3-vl-plus"

# 旧部署/误填模型名统一映射到当前默认模型
_LEGACY_MODEL_ALIASES = {
    "qwen-max-latest": DEFAULT_QWEN_MODEL,
    "qwen3.6-plus": DEFAULT_QWEN_MODEL,
    "qwen-3.6plus": DEFAULT_QWEN_MODEL,
    "qwen-plus": DEFAULT_QWEN_MODEL,
    "qwen-vl-plus": DEFAULT_QWEN_MODEL,
    "qwen-vl-max": DEFAULT_QWEN_MODEL,
    "qwen-vl-max-latest": DEFAULT_QWEN_MODEL,
}

# DashScope OpenAI 兼容接口：关闭 thinking，避免 JSON/结构化输出变慢或格式异常
QWEN_CHAT_EXTRA_BODY = {"enable_thinking": False}

# DashScope OpenAI 兼容接口 base_url（视觉/ASR 仍走这里；文本 LLM 默认也回退到这里）
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# E05 · AI 内容统一标识（GB 45438 隐式标识）：生成器标识（写进 ai_meta.generator）
AI_GENERATOR = "qwen"


def normalize_qwen_model(model: str, *, default: str = DEFAULT_QWEN_MODEL) -> str:
    name = (model or "").strip() or default
    return _LEGACY_MODEL_ALIASES.get(name, name)


def get_vl_model() -> str:
    """视觉 VL 模型名（env QWEN_VL_MODEL 可现场覆盖，缺省 DEFAULT_VL_MODEL）。

    ⛔ 不走 normalize_qwen_model：别名表把旧视觉名映射到文本模型，视觉调用会用错。"""
    return (os.environ.get("QWEN_VL_MODEL") or "").strip() or DEFAULT_VL_MODEL


def mask_secret(value: str) -> str:
    token = (value or "").strip()
    if not token:
        return ""
    if len(token) <= 10:
        return f"{token[:2]}****{token[-2:]}"
    return f"{token[:6]}****{token[-6:]}"


def _looks_like_dashscope_key(value: str) -> bool:
    return (value or "").strip().startswith("sk-")


def _read_db_qwen_config(db: Session) -> tuple[str, str]:
    row = db.query(SystemSettings).first()
    if not row:
        return "", ""
    api_key = (getattr(row, "dashscope_api_key", None) or "").strip()
    model = (getattr(row, "qwen_model", None) or "").strip()

    # Some older deployments used the only visible token box to store a Qwen key.
    # Keep this as a compatibility fallback, but prefer the dedicated Qwen field.
    legacy_token = (getattr(row, "baidu_access_token", None) or "").strip()
    if not api_key and _looks_like_dashscope_key(legacy_token):
        api_key = legacy_token
    return api_key, model


def get_qwen_config(
    db: Optional[Session] = None,
    *,
    default_model: str = DEFAULT_QWEN_MODEL,
) -> tuple[str, str]:
    api_key = ""
    model = ""

    if db is not None:
        api_key, model = _read_db_qwen_config(db)
    else:
        local_db = SessionLocal()
        try:
            api_key, model = _read_db_qwen_config(local_db)
        except Exception:
            api_key, model = "", ""
        finally:
            local_db.close()

    if not api_key:
        api_key = (os.environ.get("DASHSCOPE_API_KEY") or getattr(settings, "DASHSCOPE_API_KEY", "") or "").strip()
    if not model:
        model = (os.environ.get("QWEN_MODEL") or getattr(settings, "QWEN_MODEL", "") or default_model).strip()

    final_model = normalize_qwen_model(model or default_model, default=default_model)
    return api_key, final_model


def resolve_qwen_model(
    *,
    env_var: str = "",
    db: Optional[Session] = None,
    default_model: str = DEFAULT_QWEN_MODEL,
) -> str:
    """优先读专用环境变量，否则回退到系统/全局千问配置。"""
    env_model = (os.environ.get(env_var) or "").strip() if env_var else ""
    if env_model:
        return normalize_qwen_model(env_model, default=default_model)
    _, model = get_qwen_config(db, default_model=default_model)
    return model


def _env_or_setting(name: str, default: str = "") -> str:
    return (os.environ.get(name) or getattr(settings, name, "") or default).strip()


def get_llm_base_url() -> str:
    """文本 LLM 的 OpenAI 兼容 base_url（默认 DashScope，可通过 LLM_BASE_URL 切换供应商）。"""
    return _env_or_setting("LLM_BASE_URL", DASHSCOPE_BASE_URL).rstrip("/")


def get_llm_config(
    db: Optional[Session] = None,
    *,
    default_model: str = DEFAULT_QWEN_MODEL,
) -> tuple[str, str, str]:
    """返回文本 LLM 的 (base_url, api_key, model)。

    供应商可切换：LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 环境变量优先；
    未配置时回退到原有 DashScope 配置（向后兼容）。
    视觉/ASR 仍走 get_qwen_config（DashScope），与本函数解耦。
    """
    base_url = get_llm_base_url()
    api_key = _env_or_setting("LLM_API_KEY") or _env_or_setting("DASHSCOPE_API_KEY")
    model = _env_or_setting("LLM_MODEL") or _env_or_setting("QWEN_MODEL")
    if db is not None:
        row = db.query(SystemSettings).first()
        if row:
            if not api_key:
                api_key = (getattr(row, "dashscope_api_key", None) or "").strip()
            if not model:
                model = (getattr(row, "qwen_model", None) or "").strip()
    final_model = normalize_qwen_model(model or default_model, default=default_model)
    return base_url, api_key, final_model


def get_llm_thinking_extra(base_url: str) -> dict:
    """返回关闭文本 LLM 思考模式的额外请求字段（按供应商区分）。

    DeepSeek 系网关不识别 DashScope 的 enable_thinking 参数，传 enable_thinking=False 反而会
    触发大量 reasoning_content、把 max_tokens 挤爆，导致 choices[0].message.content 被截断，
    结构化 JSON 输出解析失败（前端表现为「AI 返回内容格式异常」）。
    DeepSeek 用 thinking={"type": "disabled"} 彻底关闭思考；DashScope 用 enable_thinking=False。
    """
    if "dashscope" in (base_url or "").lower():
        return {"enable_thinking": False}
    return {"thinking": {"type": "disabled"}}
