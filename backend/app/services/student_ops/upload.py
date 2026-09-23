"""实践佐证图片上传 + 文件直链（复用 download ticket 机制，C0 §3）。"""
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from app.services.student_ops.config import UPLOAD_ALLOWED_EXTS, UPLOAD_MAX_BYTES

# 项目根目录下 grading_data_all/student_ops（与批改文件同一存储根）
STUDENT_OPS_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "grading_data_all"
    / "student_ops"
)


def save_evidence_image(file_bytes: bytes, filename: str) -> dict:
    """校验并保存单张图片，生成缩略图。返回 {url, thumbUrl, fileName}。"""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in UPLOAD_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="仅支持 JPG/PNG/HEIC 格式图片")
    if len(file_bytes) > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="图片大小不能超过 10MB")

    month_dir = datetime.utcnow().strftime("%Y-%m")
    # 相对路径基于 STUDENT_OPS_ROOT（……/grading_data_all/student_ops），resolve 时不再重复前缀
    rel_dir = Path("practice") / "evidence" / month_dir
    abs_dir = STUDENT_OPS_ROOT / "practice" / "evidence" / month_dir
    thumb_dir = abs_dir / "thumb"
    abs_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    new_name = f"{uuid.uuid4().hex}{ext}"
    file_path = abs_dir / new_name
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # 生成缩略图（宽 400px）
    try:
        from PIL import Image

        img = Image.open(file_path)
        img.thumbnail((400, 400))
        img.save(thumb_dir / new_name, quality=80)
    except Exception:
        pass

    url = f"{rel_dir.as_posix()}/{new_name}"
    thumb_url = f"{rel_dir.as_posix()}/thumb/{new_name}"
    return {"url": url, "thumbUrl": thumb_url, "fileName": new_name}


def resolve_evidence_file(rel_path: str) -> Path:
    """将相对路径解析到绝对文件路径，防目录穿越。"""
    if not rel_path:
        raise HTTPException(status_code=400, detail="无效路径")
    safe_rel = rel_path.replace("\\", "/")
    if safe_rel.startswith("/") or ".." in safe_rel.split("/"):
        raise HTTPException(status_code=403, detail="无效路径")
    file_path = (STUDENT_OPS_ROOT / safe_rel).resolve()
    if not file_path.is_relative_to(STUDENT_OPS_ROOT.resolve()):
        raise HTTPException(status_code=403, detail="无效路径")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return file_path
