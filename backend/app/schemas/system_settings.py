from typing import Optional

from pydantic import BaseModel


class SystemSettingsOut(BaseModel):
    can_edit_access_token: bool = False
    access_token_masked: Optional[str] = None
    baidu_api_key_masked: Optional[str] = None
    baidu_secret_key_masked: Optional[str] = None
    baidu_auto_refresh_configured: bool = False
    qwen_api_key_masked: Optional[str] = None
    qwen_model: Optional[str] = None


class UpdateBaiduAccessTokenRequest(BaseModel):
    access_token: str


class UpdateBaiduCredentialsRequest(BaseModel):
    api_key: Optional[str] = None
    secret_key: Optional[str] = None


class UpdateQwenSettingsRequest(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None
