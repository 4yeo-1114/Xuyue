# -*- coding: utf-8 -*-
"""自助文印：主动调用本机扫描仪（Windows WIA）扫描到 scan_dir()，由 watch_scan 自动导入。

端点：POST /api/v1/grading/scan/trigger
调用方应先启动 scan-import（设置目标 folder_name），再调用本端点触发一次真实扫描。
扫描文件统一写入 scan_dir() 顶层（watch_scan 轮询目录），由既有扫描监测链路完成导入。

无真机环境强容错：所有 COM/设备异常翻译为明确中文错误（400/404/409/500），
不把 pywin32 的 COM 异常直接抛给前端。
"""
from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import bind_grading_user_context
from app.grading.router import _require_local_admin, _safe_folder_name
from app.grading.scanner_devices import _WIA_SCANNER_DEVICE_TYPE, _read_wia_property
from app.grading.user_paths import scan_dir

router = APIRouter(
    prefix="/grading",
    tags=["grading-scan"],
    dependencies=[Depends(bind_grading_user_context)],
)

# ---- WIA 常量 ----
_JPEG_FORMAT = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
_PNG_FORMAT = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"
_BMP_FORMAT = "{B96B3CB1-0728-11D3-9D7B-0000F81EF32E}"

# 单设备并发锁：防止多个 trigger 同时操作同一扫描仪
_scan_trigger_lock = threading.Lock()

# 单次最多扫描页数（防止进纸器异常导致死循环）
_MAX_PAGES = 20
# 单次扫描整体超时（秒），防止 COM 调用挂死线程
_SCAN_TIMEOUT = 90.0


class ScanTriggerRequest(BaseModel):
    folder_name: Optional[str] = None
    scanner_id: Optional[str] = None


class _ScanError(Exception):
    """内部错误：携带 HTTP 状态码与中文提示，端点统一翻译为 HTTPException。"""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _short(e: Exception, limit: int = 160) -> str:
    text = str(e or "").strip()
    return text[:limit] if text else e.__class__.__name__


def _image_extension(image) -> str:
    """从 WIA ImageFile 读取真实扩展名并归一化；读取失败返回空串。"""
    try:
        ext = str(image.FileExtension or "").strip().lower().lstrip(".")
    except Exception:
        return ""
    if ext in ("jpeg", "jpe"):
        return "jpg"
    if ext in ("jpg", "png", "bmp", "tif", "tiff", "gif"):
        return ext
    return ""


def _transfer_image(item):
    """按 JPEG 传输；驱动不支持则降级 PNG/BMP/默认。返回 (ImageFile, 扩展名)。"""
    for fmt, fallback_ext in ((_JPEG_FORMAT, "jpg"), (_PNG_FORMAT, "png"), (_BMP_FORMAT, "bmp")):
        try:
            image = item.Transfer(fmt)
            return image, _image_extension(image) or fallback_ext
        except Exception:
            continue
    image = item.Transfer()
    return image, _image_extension(image) or "jpg"


def _find_scanner(device_manager, scanner_id: Optional[str]):
    """复用 scanner_devices 的枚举/设备类型逻辑定位扫描仪。

    返回 (info, device_id, name)。scanner_id 为空取第一个扫描仪；找不到抛 _ScanError。
    """
    try:
        count = int(device_manager.DeviceInfos.Count)
    except Exception:
        count = 0

    scanners = []  # (info, device_id, name)
    for index in range(1, count + 1):
        try:
            info = device_manager.DeviceInfos.Item(index)
            if int(info.Type) != _WIA_SCANNER_DEVICE_TYPE:
                continue
            device_id = str(info.DeviceID or "").strip()
            name = _read_wia_property(info, "Name") or device_id or f"扫描仪 {index}"
            scanners.append((info, device_id, name))
        except Exception:
            continue

    if not scanners:
        raise _ScanError(404, "未找到可用的扫描仪，请检查设备是否连接")

    if scanner_id:
        for info, device_id, name in scanners:
            if device_id == scanner_id:
                return info, device_id, name
        raise _ScanError(404, f"未找到指定的扫描仪（ID: {scanner_id}），请先调用 /grading/scanners 获取可用列表")

    return scanners[0]


def perform_scan(scanner_id: Optional[str] = None, target_dir: Optional[Path] = None) -> list[dict]:
    """执行一次真实扫描，保存到 target_dir（默认 scan_dir() 顶层）。

    返回 [{file_name, saved_path}, ...]。所有设备/COM 异常翻译为 _ScanError（明确中文）。
    供 selftest 直接调用（mock 掉 win32com 验证各错误分支）。
    """
    if target_dir is None:
        target_dir = scan_dir()

    def _run() -> list[dict]:
        return _perform_scan_inner(scanner_id, target_dir)

    try:
        return _run_with_timeout(_run, _SCAN_TIMEOUT, "扫描超时，请检查扫描仪状态与文件是否卡纸")
    except _ScanError:
        raise
    except Exception as e:  # noqa: BLE001
        raise _ScanError(500, f"扫描失败：{_short(e)}")


def _run_with_timeout(fn, timeout: float, timeout_msg: str):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scan-trigger")
    try:
        future = executor.submit(fn)
        return future.result(timeout=timeout)
    except _FutTimeoutError:
        raise _ScanError(500, timeout_msg)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _perform_scan_inner(scanner_id: Optional[str], target_dir: Path) -> list[dict]:
    if not _scan_trigger_lock.acquire(blocking=False):
        raise _ScanError(409, "已有扫描任务正在进行中，请稍后再试")
    try:
        if sys.platform != "win32":
            raise _ScanError(400, "仅支持 Windows 系统")

        try:
            import win32com.client  # type: ignore
        except ImportError:
            raise _ScanError(500, "请安装 pywin32 以使用扫描功能")

        try:
            device_manager = win32com.client.Dispatch("WIA.DeviceManager")
        except Exception as e:  # noqa: BLE001
            raise _ScanError(500, f"无法访问 WIA 设备管理器：{_short(e)}")

        info, _device_id, name = _find_scanner(device_manager, scanner_id)

        try:
            device = info.Connect()
        except Exception as e:  # noqa: BLE001
            raise _ScanError(409, f"扫描仪连接失败（{name}）：{_short(e)}")

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            raise _ScanError(500, f"扫描保存目录不可用：{_short(e)}")

        base_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        results: list[dict] = []
        for page_no in range(1, _MAX_PAGES + 1):
            # 取第 page_no 页 item：无更多页时 WIA 抛异常（平板扫描仪通常只有 1 页）
            try:
                item = device.Items(page_no)
            except Exception:
                break

            try:
                image, ext = _transfer_image(item)
            except Exception as e:  # noqa: BLE001
                if page_no == 1:
                    raise _ScanError(500, f"扫描图像传输失败（{name}）：{_short(e)}")
                break  # 后续页传输失败视为进纸器结束

            fname = f"self_scan_{base_ts}.jpg" if page_no == 1 else f"self_scan_{base_ts}_{page_no}.jpg"
            if ext and ext != "jpg":
                fname = fname[: -len(".jpg")] + f".{ext}"
            path = target_dir / fname
            try:
                image.SaveFile(str(path))
            except Exception as e:  # noqa: BLE001
                raise _ScanError(500, f"扫描图像保存失败：{_short(e)}")
            results.append({"file_name": fname, "saved_path": str(path)})

        if not results:
            raise _ScanError(409, "扫描仪未返回任何图像，请确认已放入试卷且设备就绪")
        return results
    finally:
        _scan_trigger_lock.release()


@router.post("/scan/trigger")
async def api_scan_trigger(request: Request, body: ScanTriggerRequest, db: Session = Depends(get_db)):
    """主动触发一次真实扫描到 scan_dir()，供自助文印一键扫描→批阅→打印链路使用。"""
    _require_local_admin(request, db)  # M5：仅本机来源 + 管理员/校级角色

    safe = _safe_folder_name(body.folder_name) if body.folder_name else ""
    if body.folder_name and not safe:
        raise HTTPException(status_code=400, detail="无效文件夹名")

    # 扫描文件统一写入 scan_dir() 顶层，watch_scan 监测线程会自动移动到 folder_name 目标目录
    target_dir = scan_dir()

    try:
        results = perform_scan(scanner_id=body.scanner_id, target_dir=target_dir)
    except _ScanError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    first = results[0]
    return {
        "ok": True,
        "file_name": first["file_name"],
        "saved_path": first["saved_path"],
        "files": results,
        "folder_name": safe or "",
        "page_count": len(results),
    }
