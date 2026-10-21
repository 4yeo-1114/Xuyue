# -*- coding: utf-8 -*-
"""1015 根治：全局重活预算——所有内存/IO 大户「排队等着」，绝不并发硬扛。

背景：1013 磁盘打满、1015 内存打满，根因相同——批改批次 / AI 报告 / 打印
各链路各有各的闸，但没有任何东西限制「所有重活加起来」的总量；功能越加越多，
资源打满只是换条链路再来一次。本模块是总闸：重活开工前先拿槽位，拿不到就
排队等待（不拒绝、不超卖），从结构上封死「N 个重活同时压垮 8G 机器」。

用法（一行接入，任何新的重活链路都该包上）：

    from app.services.heavy_budget import heavy_slot
    with heavy_slot("ref-grade") as waited_s:
        ...重活...

槽位数 HEAVY_TASK_SLOTS（默认 2，8G 机器经验值：一个批改批次 + 一个报告/打印）。
升配 16G 后可在服务环境变量里调到 3~4。兜底还有 gradebuddy cgroup MemoryMax，
最坏也只是服务自己被杀重启，整机不冻。
"""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional


def _slots_from_env() -> int:
    try:
        return max(1, int(os.environ.get("HEAVY_TASK_SLOTS", "2") or "2"))
    except ValueError:
        return 2


_N = _slots_from_env()
_semaphore = threading.BoundedSemaphore(_N)
_lock = threading.Lock()
_running: dict[str, int] = {}   # 任务名 -> 个数（同名并发）
_waiting = 0                    # 排队中的任务数


@contextmanager
def heavy_slot(name: str) -> Iterator[float]:
    """排队拿槽位；拿不到就阻塞等待。yield 本次排队等待的秒数。"""
    global _waiting
    with _lock:
        _waiting += 1
    t0 = time.monotonic()
    _semaphore.acquire()
    waited = time.monotonic() - t0
    with _lock:
        _waiting -= 1
        _running[name] = _running.get(name, 0) + 1
    try:
        yield waited
    finally:
        with _lock:
            left = _running.get(name, 1) - 1
            if left <= 0:
                _running.pop(name, None)
            else:
                _running[name] = left
        _semaphore.release()


def budget_status() -> dict:
    """当前预算占用（观测用；排队语义见 heavy_slot）。"""
    with _lock:
        return {
            "slots": _N,
            "running": dict(_running),
            "waiting": _waiting,
        }


def set_slots_for_test(n: Optional[int] = None) -> None:
    """仅供单测重置槽位数（生产代码不要调）。"""
    global _N, _semaphore, _running, _waiting
    _N = n if n is not None else _slots_from_env()
    _semaphore = threading.BoundedSemaphore(_N)
    with _lock:
        _running = {}
        _waiting = 0
