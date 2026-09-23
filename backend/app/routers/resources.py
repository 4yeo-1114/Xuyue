import logging
import shutil
import threading
import time
import zipfile
import io
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.grading.user_paths import (
    ensure_user_grading_layout,
    set_grading_user_id,
    shared_zyk_dir,
)
from app.models.user import User
from app.schemas.common import ApiResponse
from app.utils.security import decode_access_token, verify_download_ticket, build_download_url
from app.schemas.resources import (
    FolderInfo,
    FileInfo,
    CreateFolderRequest,
    RenameFileRequest,
    SendEmailRequest,
)
from pydantic import BaseModel

router = APIRouter(
    prefix="/resources",
    tags=["resources"],
)


def _resource_user(request: Request, resource: str = "") -> str:
    """H2：先尝试 Authorization Header，再尝试短时下载票（resource 绑定的文件直链）。"""
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        user_id = decode_access_token(auth[7:].strip())
        if user_id:
            ensure_user_grading_layout(user_id)
            set_grading_user_id(user_id)
            return user_id
    ticket = request.query_params.get("ticket")
    if ticket:
        user_id = verify_download_ticket(ticket, resource) if resource else None
        if user_id:
            ensure_user_grading_layout(user_id)
            set_grading_user_id(user_id)
            return user_id
    raise HTTPException(status_code=401, detail="未登录")


# H4：邮件发送限流（内存实现）
_EMAIL_LOCK = threading.Lock()
# key = user_id -> [发送时间戳]
_EMAIL_SENT: dict[str, list[float]] = {}
_EMAIL_WINDOW_SECONDS = 24 * 3600
_EMAIL_MAX_PER_DAY = 20


def _check_email_rate_limit(user_id: str) -> None:
    now = time.time()
    with _EMAIL_LOCK:
        ts_list = [t for t in _EMAIL_SENT.get(user_id, []) if now - t < _EMAIL_WINDOW_SECONDS]
        if len(ts_list) >= _EMAIL_MAX_PER_DAY:
            raise HTTPException(status_code=429, detail="今日邮件发送次数已达上限")
        ts_list.append(now)
        _EMAIL_SENT[user_id] = ts_list


def _allowed_email_target(user: Optional[User], to_email: str) -> bool:
    """H4：只允许发送到本人个人邮箱，或与账号同域名的地址（防开放转发）。"""
    email = (to_email or "").strip()
    if not email:
        return False
    if user and (getattr(user, "personal_email", "") or "").strip().lower() == email.lower():
        return True
    account_domain = ((user.email or "").split("@", 1)[-1] or "").lower() if user else ""
    target_domain = (email.split("@", 1)[-1] or "").lower() if "@" in email else ""
    return bool(account_domain and target_domain == account_domain)


def get_folder_path(folder_name: str) -> Path:
    root = shared_zyk_dir().resolve()
    p = (root / folder_name).resolve()
    if not p.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Invalid folder name")
    return p


def _safe_child_path(base: Path, name: str) -> Path:
    """文件名防穿越：拒绝路径分隔符/回溯，解析后必须仍在 base 目录内（同 download 端点模式）。"""
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    p = (base / name).resolve()
    if not p.is_relative_to(base):
        raise HTTPException(status_code=400, detail="Invalid file name")
    return p


@router.get("/folders", response_model=ApiResponse[List[FolderInfo]])
def list_folders(request: Request, path: str = ""):
    _resource_user(request)
    base = get_folder_path(path) if path else shared_zyk_dir()
    if not base.exists() or not base.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    folders = []
    for item in base.iterdir():
        if item.is_dir():
            stat = item.stat()
            created_at = datetime.fromtimestamp(stat.st_ctime).isoformat()
            folders.append(FolderInfo(name=item.name, created_at=created_at))
    folders.sort(key=lambda x: x.created_at, reverse=True)
    return ApiResponse(data=folders)


@router.post("/folders", response_model=ApiResponse[FolderInfo])
def create_folder(body: CreateFolderRequest, request: Request):
    _resource_user(request)
    if not body.name:
        raise HTTPException(status_code=400, detail="Folder name cannot be empty")
    if "/" in body.name or "\\" in body.name:
        raise HTTPException(status_code=400, detail="Folder name cannot contain path separator")
    parent = (body.path or "").strip().strip("/")
    rel = f"{parent}/{body.name}" if parent else body.name
    p = get_folder_path(rel)
    if p.exists():
        raise HTTPException(status_code=400, detail="Folder already exists")
    p.mkdir(parents=True)
    created_at = datetime.fromtimestamp(p.stat().st_ctime).isoformat()
    return ApiResponse(data=FolderInfo(name=body.name, created_at=created_at))


@router.delete("/folders/{folder_name:path}", response_model=ApiResponse[None])
def delete_folder(folder_name: str, request: Request):
    _resource_user(request)
    p = get_folder_path(folder_name)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")
    shutil.rmtree(p)
    return ApiResponse(data=None)


@router.get("/folders/{folder_name:path}/files", response_model=ApiResponse[List[FileInfo]])
def list_files(folder_name: str, request: Request):
    user_id = _resource_user(request)
    p = get_folder_path(folder_name)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    items = [it for it in p.iterdir() if it.is_file()]
    items.sort(key=lambda it: it.stat().st_mtime, reverse=True)

    # 封面约定：与某个「非图片文件」同 stem 的图片（jpg/jpeg/png/webp）视为该文件的封面，
    # 不作为独立文件列出，改作为 cover_url 挂在对应文件上（教材 PDF / 课件 PPT 显示真封面）。
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    covered_stems = {it.stem for it in items if it.suffix.lower() not in image_exts}

    files = []
    for item in items:
        stat = item.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
        is_image = item.suffix.lower() in image_exts
        if is_image and item.stem in covered_stems:
            continue  # 封面图，不单独列出
        # H2：返回短时下载票直链，不再让前端把长期 JWT 拼进 URL
        url = build_download_url(f"zyk_data/{folder_name}/{item.name}", user_id)
        cover_url = None
        if not is_image:
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                c = p / (item.stem + ext)
                if c.is_file():
                    cover_url = build_download_url(f"zyk_data/{folder_name}/{c.name}", user_id)
                    break
        files.append(FileInfo(name=item.name, size=stat.st_size, modified_at=modified_at, url=url, cover_url=cover_url))
    return ApiResponse(data=files)

@router.post("/folders/{folder_name:path}/files", response_model=ApiResponse[None])
def upload_files(
    folder_name: str,
    request: Request,
    files: List[UploadFile] = File(...),
):
    _resource_user(request)
    p = get_folder_path(folder_name)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    for file in files:
        if file.filename:
            # 防路径穿越：文件名解析后必须仍在目标目录内
            file_path = _safe_child_path(p, file.filename)
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
    return ApiResponse(data=None)


@router.delete("/folders/{folder_name:path}/files/{file_name}", response_model=ApiResponse[None])
def delete_file(folder_name: str, file_name: str, request: Request):
    _resource_user(request)
    # 防路径穿越：文件名解析后必须仍在目标目录内
    p = _safe_child_path(get_folder_path(folder_name), file_name)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    p.unlink()
    return ApiResponse(data=None)


@router.put("/folders/{folder_name:path}/files/{file_name}/rename", response_model=ApiResponse[None])
def rename_file(folder_name: str, file_name: str, body: RenameFileRequest, request: Request):
    _resource_user(request)
    # 防路径穿越：旧名与新名解析后都必须仍在目标目录内
    folder = get_folder_path(folder_name)
    p = _safe_child_path(folder, file_name)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if not body.new_name:
        raise HTTPException(status_code=400, detail="New name cannot be empty")
    new_p = _safe_child_path(folder, body.new_name)
    if new_p.exists():
        raise HTTPException(status_code=400, detail="File with new name already exists")
    p.rename(new_p)
    return ApiResponse(data=None)


@router.get("/folders/{folder_name:path}/files/{file_name}/download")
def download_file(folder_name: str, file_name: str, request: Request):
    """H2：下载走短时下载票或 Authorization Header，不再接受长期 JWT query token。"""
    folder_name = urllib.parse.unquote(folder_name)
    file_name = urllib.parse.unquote(file_name)
    _resource_user(request, resource=f"zyk_data/{folder_name}/{file_name}")

    root = shared_zyk_dir().resolve()
    p = (root / folder_name / file_name).resolve()
    if not p.is_relative_to(root) or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    encoded_filename_header = urllib.parse.quote(file_name)
    return FileResponse(
        path=p,
        filename=file_name,
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename_header}"}
    )


@router.get("/folders/{folder_name:path}/download-zip")
def download_folder_zip(folder_name: str, request: Request):
    """H2：下载走短时下载票或 Authorization Header，不再接受长期 JWT query token。"""
    folder_name = urllib.parse.unquote(folder_name)
    _resource_user(request, resource=f"zyk_data/{folder_name}")

    root = shared_zyk_dir().resolve()
    p = (root / folder_name).resolve()
    if not p.is_relative_to(root) or not p.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zipf:
        for item in p.iterdir():
            if item.is_file():
                zipf.write(str(item), arcname=item.name)

    memory_file.seek(0)
    encoded_filename = f"{folder_name}.zip"
    encoded_filename_header = urllib.parse.quote(encoded_filename)

    return StreamingResponse(
        memory_file,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename_header}"}
    )

class DownloadZipRequest(BaseModel):
    files: List[str]


@router.post("/folders/{folder_name:path}/download-zip")
def download_folder_zip_post(
    folder_name: str,
    request: Request,
    body: DownloadZipRequest,
):
    _resource_user(request)
    folder_name = urllib.parse.unquote(folder_name)
    p = get_folder_path(folder_name)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zipf:
        for fname in body.files:
            # 防路径穿越：清单内文件名解析后必须仍在目标目录内
            file_path = _safe_child_path(p, fname)
            if file_path.exists() and file_path.is_file():
                zipf.write(str(file_path), arcname=fname)

    memory_file.seek(0)
    encoded_filename = f"{folder_name}.zip"
    encoded_filename_header = urllib.parse.quote(encoded_filename)

    return StreamingResponse(
        memory_file,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename_header}"}
    )


@router.post("/send-email", response_model=ApiResponse[dict])
def send_resources_email(
    body: SendEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """H4：收件人限定为本人个人邮箱或同域名地址；加限流与审计日志，防止开放邮件转发。"""
    user_id = _resource_user(request)
    user = db.query(User).filter(User.id == user_id).first()
    _check_email_rate_limit(user_id)

    target_email = ""
    if body.to_email and body.to_email.strip():
        target_email = body.to_email.strip()
    else:
        target_email = (getattr(user, "personal_email", "") or "").strip() if user else ""

    if not target_email:
        raise HTTPException(status_code=400, detail="未指定接收邮箱，且个人设置中未配置个人邮箱")
    if not _allowed_email_target(user, target_email):
        logging.warning("资源库邮件发送被拒绝（非本人/非同域名收件人）: user_id=%s to_email=%s", user_id, target_email)
        raise HTTPException(status_code=403, detail="仅允许发送到本人个人邮箱或本账号同域名的邮箱")

    if not body.files:
        raise HTTPException(status_code=400, detail="未选择要发送的文件")

    p = get_folder_path(body.folder_name)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    attachments = []
    for fname in body.files:
        # 防路径穿越：清单内文件名解析后必须仍在目标目录内
        fpath = _safe_child_path(p, fname)
        if fpath.exists() and fpath.is_file():
            with open(fpath, "rb") as f:
                content = f.read()
            attachments.append({
                "filename": fname,
                "content": content,
                "maintype": "application",
                "subtype": "octet-stream",
            })

    if not attachments:
        raise HTTPException(status_code=400, detail="所选文件均不存在")

    try:
        from app.email_utils import send_email
        send_email(
            to_email=target_email,
            subject=f"资源库文件分享：{body.folder_name}",
            body=f"附件中包含了您在资源库选择的 {len(attachments)} 个文件。",
            attachments=attachments
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {str(e)}")

    logging.info("资源库邮件发送成功: user_id=%s to_email=%s", user_id, target_email)
    return ApiResponse(data={"ok": True, "to_email": target_email})
