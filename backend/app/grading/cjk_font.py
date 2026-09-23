# -*- coding: utf-8 -*-
"""中文字体：优先用项目 assets/fonts，缺失时自动下载（Linux 服务器免装 dnf 字体包）。"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

_download_lock = threading.Lock()
# 下载失败冷却：失败后 _DOWNLOAD_RETRY_COOLDOWN_SECONDS 内不重复尝试，
# 避免每张 PDF 都打网络；冷却过后允许重试，网络恢复后自动恢复嵌入字体。
_download_failed_at: Optional[float] = None
_DOWNLOAD_RETRY_COOLDOWN_SECONDS = 600.0

CJK_FONT_FILENAME = "wqy-zenhei.ttc"
# 直接下载 .ttc（不要用浏览器打开 anthonyfok 等已失效的旧链接）
_DEFAULT_CJK_FONT_URLS = (
    "https://cdn.jsdelivr.net/gh/ITboy/font@master/wqy-zenhei/debian/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
    "https://raw.githubusercontent.com/ITboy/font/master/wqy-zenhei/debian/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
)


def _cjk_font_download_urls() -> tuple[str, ...]:
    custom = str(os.environ.get("GRADING_FONT_DOWNLOAD_URL", "") or "").strip()
    if custom:
        return (custom,) + _DEFAULT_CJK_FONT_URLS
    return _DEFAULT_CJK_FONT_URLS


def bundled_cjk_font_path() -> Path:
    from app.grading.user_paths import project_root

    return project_root() / "assets" / "fonts" / CJK_FONT_FILENAME


def _auto_download_enabled() -> bool:
    return os.environ.get("GRADING_FONT_AUTO_DOWNLOAD", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _log(msg: str) -> None:
    """安全日志：stdout 关闭时静默，不让打印影响字体流程。"""
    try:
        print(msg)
    except Exception:
        pass


def _download_url(url: str, dest: Path) -> None:
    req = Request(url, headers={"User-Agent": "grade-buddy-scan/1.0"})
    with urlopen(req, timeout=180) as resp, dest.open("wb") as f:
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)


def ensure_cjk_font_file() -> Optional[str]:
    """
    确保项目内有可用的中文字体文件。
    返回字体绝对路径；失败返回 None（不抛异常，由调用方走 fallback）。
    """
    global _download_failed_at

    target = bundled_cjk_font_path()
    if target.is_file() and target.stat().st_size > 1_000_000:
        return str(target)

    if not _auto_download_enabled():
        return None

    with _download_lock:
        if target.is_file() and target.stat().st_size > 1_000_000:
            return str(target)
        # 下载失败冷却期内不重复尝试（防抖）
        if _download_failed_at is not None and (
            time.monotonic() - _download_failed_at < _DOWNLOAD_RETRY_COOLDOWN_SECONDS
        ):
            return None

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".download")
        for url in _cjk_font_download_urls():
            try:
                _log("正在下载中文字体（作文留痕，约 16MB，请稍候）…")
                _download_url(url, tmp)
                if tmp.stat().st_size > 1_000_000:
                    tmp.replace(target)
                    _log(f"中文字体已就绪: {target}")
                    return str(target)
                _log(f"下载文件过小，可能不完整: {tmp.stat().st_size} bytes")
            except Exception as e:
                _log(f"中文字体下载失败: {e}")
            finally:
                try:
                    if tmp.is_file():
                        tmp.unlink()
                except Exception:
                    pass
        _download_failed_at = time.monotonic()
        return None
