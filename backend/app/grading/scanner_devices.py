# -*- coding: utf-8 -*-
"""本机扫描仪枚举（Windows WIA）。"""
from __future__ import annotations

import sys

# WIA DeviceType: Scanner = 1
_WIA_SCANNER_DEVICE_TYPE = 1


def list_scanners_with_status():
    """
    列出本机可用扫描仪。
    :return: (success: bool, result)
      成功时 result 为 list[dict]，每项 { "id", "name", "manufacturer", "available" }
      失败时 result 为错误信息 str。
    """
    if sys.platform != "win32":
        return False, "仅支持 Windows 系统"
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return False, "请安装 pywin32 以检测扫描仪"

    try:
        device_manager = win32com.client.Dispatch("WIA.DeviceManager")
    except Exception as e:
        return False, f"无法访问 WIA 设备管理器：{e}"

    scanners = []
    try:
        count = int(device_manager.DeviceInfos.Count)
    except Exception:
        count = 0

    for index in range(1, count + 1):
        try:
            info = device_manager.DeviceInfos.Item(index)
            device_type = int(info.Type)
            if device_type != _WIA_SCANNER_DEVICE_TYPE:
                continue
            device_id = str(info.DeviceID or "").strip()
            name = _read_wia_property(info, "Name") or device_id or f"扫描仪 {index}"
            manufacturer = _read_wia_property(info, "Manufacturer") or ""
            scanners.append(
                {
                    "id": device_id,
                    "name": name,
                    "manufacturer": manufacturer,
                    "available": bool(device_id),
                }
            )
        except Exception:
            continue

    return True, scanners


def _read_wia_property(info, prop_name: str) -> str:
    try:
        value = info.Properties(prop_name).Value
        return str(value or "").strip()
    except Exception:
        return ""
