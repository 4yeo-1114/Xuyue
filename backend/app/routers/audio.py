"""语音识别路由（教师语音录入 P0）。

POST /api/v1/audio/asr —— 上传音频文件 → ASR 转写 → 返回 {text}。
鉴权：get_current_user_id（与 student_ops 一致的 JWT Bearer Header 模式，见
app/dependencies.py / H2：不接受 URL query token）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.schemas.common import ApiResponse
from app.services.asr import transcribe_audio

router = APIRouter(prefix="/audio", tags=["audio"])

# 上传体积上限：ASR base64 输入约 10MB，留出编码余量（15MB 原始 ≈ 20MB base64）
MAX_AUDIO_BYTES = 15 * 1024 * 1024


@router.post("/asr", response_model=ApiResponse)
async def audio_asr(
    file: UploadFile = File(..., description="音频文件（wav/mp3/webm/opus/ogg/m4a/aac）"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    del user_id  # 仅做登录鉴权，转写本身不写库
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音频文件为空")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="音频文件过大（上限 15MB）")
    result = transcribe_audio(db, audio_bytes, filename=file.filename or "")
    if not result.get("ok"):
        # 未配置 key 或转写失败：统一 500，detail 为明确原因，前端 toast 兜底文案
        raise HTTPException(status_code=500, detail=result.get("error") or "语音转写失败")
    return ApiResponse(data={"text": result["text"]})
