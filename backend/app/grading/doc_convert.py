# -*- coding: utf-8 -*-
"""PDF/Word 转图像，供 OCR 与批改使用。PDF 用 PyMuPDF，Word 先转 PDF 再转图。"""
import os
import sys
import uuid
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import fitz  # PyMuPDF
    _HAS_PYMUPDF = True
except ImportError:
    _HAS_PYMUPDF = False

_HAS_DOCX2PDF = False
try:
    import docx2pdf
    _HAS_DOCX2PDF = True
except ImportError:
    pass


def _get_grading_data_dir() -> Path:
    try:
        from app.grading.user_paths import grading_paths
        return grading_paths().root
    except Exception:
        from app.grading.user_paths import grading_data_all_root
        fallback = grading_data_all_root() / "_no_user_context"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def pdf_to_images(pdf_path: str, dpi: int = 150):
    """将 PDF 每一页转为 PIL Image。需要 PyMuPDF。"""
    if not _HAS_PYMUPDF or not Image:
        raise RuntimeError("需要安装 PyMuPDF 和 Pillow: pip install pymupdf Pillow")
    path = os.path.abspath(pdf_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"PDF 不存在: {path}")
    images = []
    doc = fitz.open(path)
    try:
        for i in range(len(doc)):
            page = doc[i]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
    finally:
        doc.close()
    return images


def _docx_to_pdf_libreoffice(docx_path: str, out_dir: str) -> str:
    """使用 LibreOffice 将 docx 转为 PDF。返回生成的 PDF 路径。"""
    import subprocess
    path = os.path.abspath(docx_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, path]
    if sys.platform == "win32":
        for prog in (
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ):
            if os.path.isfile(prog):
                cmd = [prog, "--headless", "--convert-to", "pdf", "--outdir", out_dir, path]
                break
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    base = Path(path).stem
    pdf_path = Path(out_dir) / f"{base}.pdf"
    if not pdf_path.is_file():
        raise RuntimeError("LibreOffice 未生成 PDF")
    return str(pdf_path)


def _docx_to_pdf_docx2pdf(docx_path: str, out_dir: str) -> str:
    """使用 docx2pdf (Windows Word COM) 将 docx 转为 PDF。"""
    import docx2pdf as d2p
    path = os.path.abspath(docx_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    base = Path(path).stem
    out_pdf = os.path.join(out_dir, f"{base}.pdf")
    d2p.convert(path, out_pdf)
    if not os.path.isfile(out_pdf):
        raise RuntimeError("docx2pdf 未生成 PDF")
    return out_pdf


def docx_to_images(docx_path: str, dpi: int = 150):
    """将 Word 文档转为 PIL Image 列表（先转 PDF 再转图）。需要 LibreOffice 或 docx2pdf (Windows)。"""
    if not Image:
        raise RuntimeError("需要安装 Pillow")
    path = os.path.abspath(docx_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".doc", ".docx"):
        raise ValueError("仅支持 .doc .docx")
    tmp_dir = _get_grading_data_dir() / "temp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = None
    try:
        if _HAS_DOCX2PDF and sys.platform == "win32":
            pdf_path = _docx_to_pdf_docx2pdf(path, str(tmp_dir))
        else:
            pdf_path = _docx_to_pdf_libreoffice(path, str(tmp_dir))
        return pdf_to_images(pdf_path, dpi=dpi)
    except Exception as e:
        raise RuntimeError(
            f"Word 转图像失败（请安装 LibreOffice 或 Windows 下 pip install docx2pdf）: {e}"
        )
    finally:
        if pdf_path and os.path.isfile(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception:
                pass


def enhance_for_ocr(img, mode="auto"):
    """OCR 前共享图像增强。同尺寸返回（不缩放不裁剪），保证 bbox 坐标不漂移。

    与 reference_vlm_grading._crop_to_data_url / _crop_regions_to_data_url 的裁图增强
    （ImageOps.autocontrast(cutoff=0.5) + Contrast.enhance(1.12) + Sharpness.enhance(1.25)
    + UnsharpMask(radius=1.0, percent=120, threshold=3)）同配方，B3 统一复用。

    mode:
      - "auto"（默认，最温和）：上述同配方。
      - "aggressive"：auto 基础上叠加基于灰度百分位的自适应对比度拉伸 + 更强锐化，
        用于手写浓淡差异大的场景。
      - "off"：原样返回（不复制）。

    mode 缺省（None 或 "auto"）时按环境变量 GRADING_OCR_ENHANCE 解析
    （off|auto|aggressive，默认 auto）。
    任何异常回退返回原图（增强是旁路，失败不影响 OCR）。
    """
    if Image is None or not isinstance(img, Image.Image):
        return img
    # mode 缺省 / auto 时按 env 决定最终档位
    if mode is None or (isinstance(mode, str) and mode.strip().lower() == "auto"):
        mode = os.environ.get("GRADING_OCR_ENHANCE", "auto").strip().lower()
    if not isinstance(mode, str):
        mode = "auto"
    mode = mode.strip().lower()
    if mode == "off":
        return img
    if mode not in ("auto", "aggressive"):
        return img
    try:
        import numpy as np
        from PIL import ImageEnhance, ImageFilter, ImageOps

        out = img.convert("RGB") if img.mode != "RGB" else img.copy()
        out = ImageOps.autocontrast(out, cutoff=0.5)
        out = ImageEnhance.Contrast(out).enhance(1.12)
        out = ImageEnhance.Sharpness(out).enhance(1.25)
        out = out.filter(ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=3))
        if mode == "aggressive":
            # 自适应对比度拉伸：按灰度直方图 2%~98% 百分位把像素范围映射到全动态范围，
            # 再叠加更强锐化，用于手写浓淡差异大的场景。
            arr = np.asarray(out).astype(np.float32)
            gray = arr.mean(axis=2) if arr.ndim == 3 else arr
            lo, hi = np.percentile(gray, (2, 98))
            if hi > lo:
                arr = (arr - lo) * (255.0 / (hi - lo))
                out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")
            out = out.filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=2))
        return out
    except Exception:
        return img


def ensure_image_path(file_path: str, temp_dir: Path = None) -> tuple:
    """
    若为图片则返回 (原路径, False)；若为 PDF/Word 则转成第一页图片并保存到 temp_dir，返回 (图片路径, True)。
    调用方可在批改完成后删除临时文件。
    """
    path = os.path.abspath(file_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    ext = os.path.splitext(path)[1].lower()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    if ext in image_exts:
        return path, False
    if ext == ".pdf":
        if not _HAS_PYMUPDF:
            raise RuntimeError("PDF 批改需要安装 PyMuPDF: pip install pymupdf")
        images = pdf_to_images(path)
        if not images:
            raise RuntimeError("PDF 无有效页面")
    elif ext in (".doc", ".docx"):
        images = docx_to_images(path)
        if not images:
            raise RuntimeError("Word 无有效页面")
    else:
        raise ValueError(f"不支持的文件类型: {ext}")
    if temp_dir is None:
        temp_dir = _get_grading_data_dir() / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(path).stem
    first_img_path = temp_dir / f"{stem}_{uuid.uuid4().hex[:8]}.jpg"
    images[0].convert("RGB").save(str(first_img_path), quality=95)
    return str(first_img_path), True


# 百度 OCR detect_direction 朝向码 -> 摆正需要顺时针旋转的度数。
# 1=图像逆时针偏 90°（摆正需顺转 90°），2=颠倒（顺转 180°），3=图像顺时针偏 90°（摆正需顺转 270°）。
_BAIDU_DIRECTION_TO_CW = {1: 90, 2: 180, 3: 270}


def detect_image_orientation(pil_img) -> int:
    """判断图片文字方向，返回摆正需要顺时针旋转的度数（0/90/180/270，0=无需旋转）。

    用百度 OCR accurate_basic 的 detect_direction 判定（确定性、权威），
    而不是多类 VL 判定（90°/180° 易混淆、同一张图两次结果可能不同，会误转已正的卷子）。
    任何异常（未配置百度、图内无文字、网络失败等）都返回 0，保证自动摆正是旁路能力，绝不阻断上传本身。
    可用环境变量 GRADING_UPLOAD_AUTO_ROTATE=off（或 0/false/no）关闭。
    """
    flag = os.environ.get("GRADING_UPLOAD_AUTO_ROTATE", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return 0
    if not Image or pil_img is None:
        return 0
    try:
        import base64
        import io

        import requests

        from app.grading.baidu_grading import _build_url, _create_rate_limiter
    except Exception:
        return 0
    try:
        # 缩小到长边 1600 以内再编码，降体积提速度（方向判定与缩放无关）
        im = pil_img
        w, h = im.size
        max_side = 1600
        if max(w, h) > max_side:
            scale = max_side / max(w, h)
            im = im.resize((int(w * scale), int(h * scale)))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=88)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        url = _build_url("https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic")
        # 批量上传摆正会突发打百度，先过全局滑动窗口限流（对齐批改君）
        _create_rate_limiter.acquire()
        resp = requests.post(
            url,
            data={"image": b64, "detect_direction": "true"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json() or {}
        try:
            direction = int(data.get("direction"))
        except (TypeError, ValueError):
            return 0
        return _BAIDU_DIRECTION_TO_CW.get(direction, 0)
    except Exception:
        return 0


# 进门压图（1016 不花钱项①）：小于该体积的上传图不做重编码（本来就不占磁盘）。
_UPLOAD_COMPRESS_MIN_BYTES = 300 * 1024


def _upload_jpeg_quality() -> int:
    try:
        q = int(os.environ.get("GRADING_UPLOAD_JPEG_QUALITY", "85") or "85")
    except ValueError:
        q = 85
    return max(60, min(95, q))


def _compress_normalized_image(rgb, ext: str) -> bytes:
    """同尺寸重编码压体积（绝不改像素尺寸——bbox 按磁盘图 size 归一化）。PNG 走无损 optimize。"""
    import io

    buf = io.BytesIO()
    if ext in (".jpg", ".jpeg"):
        rgb.save(buf, format="JPEG", quality=_upload_jpeg_quality(), optimize=True)
    elif ext == ".png":
        rgb.save(buf, format="PNG", optimize=True)
    elif ext == ".webp":
        rgb.save(buf, format="WEBP", quality=_upload_jpeg_quality())
    else:
        rgb.save(buf)
    return buf.getvalue()


def normalize_uploaded_image_orientation(path) -> bool:
    """
    手机/相机拍摄的 JPEG/PNG 常带 EXIF Orientation，未转正时像素仍是“横放”，浏览器与 Pillow 表现不一致，预览和批改留痕会横竖错乱。

    使用 Pillow ImageOps.exif_transpose 将 EXIF 方向落实到像素并写回文件。

    可选：设置环境变量 GRADING_UPLOAD_FORCE_PORTRAIT=1 时，在 EXIF 转正后若仍满足 宽>高，再逆时针旋转 90°，
    使整张图以竖向为主（适合竖版试卷被横拍、且 EXIF 仍显示为横向的情况；若确有横版文档请勿开启）。

    1016 进门压图：摆正后同尺寸重编码压缩（JPEG/WebP 质量由 GRADING_UPLOAD_JPEG_QUALITY 定，默认 85）。
    只在压缩真的变小时写回（压不小保留原文件字节，避免 JPEG 二次有损反而变大）；
    方向被修正过则无论大小必须写回。小于 300KB 的图不动（不值得重编码伤画质）。
    """
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        return False
    ext = p.suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        return False
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return False
    try:
        original_size = p.stat().st_size
        with Image.open(p) as im0:
            orientation_tag = 1
            try:
                orientation_tag = int(im0.getexif().get(0x0112, 1) or 1)
            except Exception:
                orientation_tag = 1
            im = ImageOps.exif_transpose(im0)
            # EXIF 方向被落实到像素 = 画面动过，必须写回（顺带清掉方向标签）
            rotated = orientation_tag != 1
            force = os.environ.get("GRADING_UPLOAD_FORCE_PORTRAIT", "").lower() in ("1", "true", "yes")
            if force:
                w, h = im.size
                if w > h:
                    im = im.rotate(-90, expand=True)
                    rotated = True
            # 倒置/侧放的扫描件（无 EXIF）自动摆正：按千问判定的方向旋转到正向
            deg = detect_image_orientation(im)
            if deg:
                im = im.rotate(-deg, expand=True)
                rotated = True
                print(f"[auto-rotate] 检测到图片方向偏差，已顺时针旋转 {deg}° 摆正: {p.name}")
            rgb = im.convert("RGB")
        if not rotated and original_size < _UPLOAD_COMPRESS_MIN_BYTES:
            return True
        data = _compress_normalized_image(rgb, ext)
        if rotated or len(data) < original_size:
            p.write_bytes(data)
        return True
    except Exception:
        return False
