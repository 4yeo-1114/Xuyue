# -*- coding: utf-8 -*-
"""按机器内存自适应并发旋钮（安装包发给客户，机器配置各异）。

调参键一律 os.environ 直读（同 BAIDU_CREATE_QPS 一族）——不进 Settings、
不进 .env（exe 的 Settings extra=forbidden，.env 多键即崩，见安装包毒键教训）。
env 显式配置永远优先于这里的自动值。
"""
from __future__ import annotations

import os
import sys

_ram_gb_cache: float | None = None


def machine_ram_gb() -> float:
    """物理内存 GB（拿不到按 8 算=保守档）。"""
    global _ram_gb_cache
    if _ram_gb_cache is not None:
        return _ram_gb_cache
    gb = 8.0
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                gb = stat.ullTotalPhys / (1024**3)
        else:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            gb = pages * page_size / (1024**3)
    except Exception:
        gb = 8.0
    _ram_gb_cache = float(gb)
    return _ram_gb_cache


def auto_workers(low: int, high: int, threshold_gb: float = 15.0) -> int:
    """内存 >= threshold_gb 用 high，否则用 low（8G 事故机保守档）。

    阈值 15 而非 16：16G 机型硬件保留后 ullTotalPhys ≈ 15.7，卡 16 会误判。
    """
    return high if machine_ram_gb() >= threshold_gb else low


def env_workers(name: str, low: int, high: int) -> int:
    """env 显式值优先；否则按内存自动。"""
    raw = str(os.environ.get(name) or "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return auto_workers(low, high)
