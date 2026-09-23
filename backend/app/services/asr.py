"""DashScope 语音转写服务（教师语音录入 P0）。

浏览器 MediaRecorder 录音 → 上传 → 本服务将音频 base64 后调用 DashScope
同步语音识别（Qwen-ASR / qwen3-asr-flash,multimodal-generation 接口）返回中文文字。

为什么不用 paraformer-v2 / paraformer-realtime-v2：
- `paraformer-v2` 的 POST /api/v1/services/audio/asr/transcription 仅支持公网
  file_url 输入，不支持 base64/文件上传，且为异步 submit-poll 模式，不适合教师即时录入。
- `paraformer-realtime-v2` 走 WebSocket 流式识别，同样不是一次 HTTP base64 上传。
故选用同属 DashScope 体系的 Qwen-ASR 同步接口：请求体含 model 与 base64(data URI) 音频，
单次请求同步返回识别文字，兼容 wav/mp3/webm/opus/ogg/m4a/aac。

鉴权复用 qwen_settings.get_qwen_config(db)（与 AI 评语/备课共用同一把 DashScope key）。
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

import requests
from sqlalchemy.orm import Session

from app.utils.qwen_settings import get_qwen_config

logger = logging.getLogger(__name__)

# DashScope Qwen-ASR 同步识别接口（国内站）
ASR_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
DEFAULT_ASR_MODEL = "qwen3-asr-flash"

# 上传文件扩展名 → data URI MIME（浏览器 MediaRecorder 常见容器）
_MIME_HINTS: dict[str, str] = {
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
    "wav": "audio/wav",
    "wave": "audio/wav",
    "mp3": "audio/mpeg",
    "mpeg": "audio/mpeg",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "mp4": "audio/mp4",
}


def _mime_for(filename: str) -> str:
    name = (filename or "").lower()
    for ext, mime in _MIME_HINTS.items():
        if name.endswith("." + ext):
            return mime
    return "audio/webm"


def transcribe_audio(db: Session, audio_bytes: bytes, filename: str = "") -> dict:
    """转写一段音频为中文文字。

    返回 {ok, text, error}：
      - ok=False 表示网关失败（含未配置 DashScope key）或转写失败，error 为明确原因，
        调用方按错误兜底（不崩溃）。
    """
    api_key, _ = get_qwen_config(db)
    if not api_key:
        logger.warning("[asr] 未配置 DashScope API Key，语音转写不可用")
        return {"ok": False, "text": "", "error": "DASHSCOPE_API_KEY 未配置，请在系统设置中配置后使用"}

    if not audio_bytes:
        return {"ok": False, "text": "", "error": "音频内容为空"}

    mime = _mime_for(filename)
    data_uri = f"data:{mime};base64,{base64.b64encode(audio_bytes).decode('ascii')}"
    body: dict = {
        "model": DEFAULT_ASR_MODEL,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "input_audio", "input_audio": data_uri}],
                }
            ]
        },
        "parameters": {
            "asr_options": {
                "enable_itn": False,
                "language": "zh",
            }
        },
    }

    try:
        resp = requests.post(
            ASR_URL,
            json=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[asr] 调用 DashScope 语音识别失败: %s", exc)
        return {"ok": False, "text": "", "error": f"语音转写服务调用失败: {exc}"}

    if resp.status_code != 200:
        logger.warning("[asr] DashScope 语音识别返回非 200: %s %s", resp.status_code, resp.text[:300])
        return {"ok": False, "text": "", "error": f"语音转写失败: HTTP {resp.status_code}"}

    try:
        data = resp.json()
        choices = (data.get("output") or {}).get("choices") or []
        content = choices[0].get("message", {}).get("content") if choices else None
        if isinstance(content, list):
            text = "".join(
                item.get("text", "") for item in content
                if isinstance(item, dict) and item.get("text")
            )
        else:
            text = (content or "").strip() if isinstance(content, str) else ""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "text": "", "error": "未识别到语音内容"}
        return {"ok": True, "text": text, "error": ""}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[asr] 解析 DashScope 语音识别响应失败: %s", exc)
        return {"ok": False, "text": "", "error": "语音转写响应解析失败"}
