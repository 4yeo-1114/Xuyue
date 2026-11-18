# -*- coding: utf-8 -*-
"""重活期间阻止系统睡眠（客户机批改几小时机器睡眠=白等，20261110 实测 21:51 睡→03:00 醒）。

挂在 heavy_slot 总闸上：任一重活在跑就保持系统清醒，全部结束自动恢复。
Windows 用 SetThreadExecutionState（ES_CONTINUOUS|ES_SYSTEM_REQUIRED）；其他
平台静默不做事（生产是常开服务器，无所谓睡眠）。

⚠️ SetThreadExecutionState 按线程生效、线程退出即失效，所以用一条常驻
daemon 线程持有执行状态，按引用计数开关。
"""
from __future__ import annotations

import sys
import threading

# ES_CONTINUOUS=0x80000000 ES_SYSTEM_REQUIRED=0x00000001
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001

_lock = threading.Lock()
_depth = 0
_keeper: threading.Thread | None = None
_state_changed = threading.Event()


def _set_state(keep_awake: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        flags = _ES_CONTINUOUS | (_ES_SYSTEM_REQUIRED if keep_awake else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass  # 保命功能失败不拖垮批改


def _keeper_loop() -> None:
    current = False
    while True:
        _state_changed.wait()
        _state_changed.clear()
        with _lock:
            want = _depth > 0
        if want != current:
            _set_state(want)
            current = want


def acquire() -> None:
    """进入重活：保持系统清醒（引用计数）。"""
    global _depth, _keeper
    with _lock:
        _depth += 1
        if _keeper is None:
            _keeper = threading.Thread(
                target=_keeper_loop, daemon=True, name="keep-awake"
            )
            _keeper.start()
    _state_changed.set()


def release() -> None:
    """退出重活：计数归零后允许系统睡眠。"""
    global _depth
    with _lock:
        _depth = max(0, _depth - 1)
    _state_changed.set()
