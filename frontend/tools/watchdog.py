#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""叙阅演示三服务守护脚本（零依赖，供 Windows 计划任务调用）

职责：幂等「检查端口 → 掉了则拉起」，按依赖顺序 mysqld(3306) → 后端(6888) → preview_proxy(6891)。
由两个 Windows 计划任务驱动：
  - GBWatchdog-Start : ONSTART 开机自启（/ru SYSTEM /rl highest）
  - GBWatchdog-Tick  : 每 3 分钟兜底重跑（幂等，重复执行无副作用）

用法：
  python tools/watchdog.py            单次检查 + 拉起（供计划任务调用）
  python tools/watchdog.py --check    只输出三服务 running/stopped，不拉起（供手动验收）
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

# .../叙阅  <-- PROJECT  ;  .../grade-buddy-scan-main  <-- ROOT
PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(PROJECT, "docs")
BACKEND_DIR = os.path.join(PROJECT, "grade-buddy-scan-back_end")
WATCHDOG_LOG = os.path.join(DOCS, "watchdog.log")

MYSQLD_EXE = r"C:/Users/Admin/Downloads/mysql-8.0.46-winx64/mysql-8.0.46-winx64/bin/mysqld.exe"
MYSQLD_DATA = r"C:/Users/Admin/Downloads/mysql-8.0.46-winx64/mysql-8.0.46-winx64/data"

# 用当前解释器的绝对路径，避免 SYSTEM 计划任务里 PATH 解析差异
PY = sys.executable or "python"

SERVICES = [
    {
        "name": "mysqld",
        "port": 3306,
        "cwd": None,  # mysqld 用绝对路径，无需 cd
        "cmd": [MYSQLD_EXE, "--no-defaults", "--datadir=" + MYSQLD_DATA, "--port=3306"],
        "log": os.path.join(DOCS, "mysqld-3306.log"),
    },
    {
        "name": "backend",
        "port": 6888,
        "cwd": BACKEND_DIR,
        "cmd": [PY, "run.py"],
        "log": os.path.join(DOCS, "backend-6888.log"),
    },
    {
        "name": "proxy",
        "port": 6891,
        "cwd": ROOT,
        "cmd": [PY, os.path.join("tools", "preview_proxy.py")],
        "env": {"PREVIEW_PORT": "6891"},
        "log": os.path.join(DOCS, "preview_proxy-6891.log"),
    },
]


def self_log(msg: str) -> None:
    """守护自身日志 -> docs/watchdog.log（UTF-8）。"""
    try:
        os.makedirs(DOCS, exist_ok=True)
        with open(WATCHDOG_LOG, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:  # noqa: BLE001
        pass


def is_listening(port: int) -> bool:
    """netstat 判断端口是否 LISTENING（与验收命令一致）。"""
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=15
        ).stdout or ""
    except Exception:  # noqa: BLE001
        return False
    target = str(port)
    for line in out.splitlines():
        parts = line.split()
        # TCP 行：本地地址 / 远程地址 / LISTENING / PID
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
            if parts[1].rsplit(":", 1)[-1] == target:
                return True
    return False


def launch(svc) -> bool:
    """端口已在监听则跳过；否则后台拉起，返回是否实际拉起。"""
    if is_listening(svc["port"]):
        return False
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    env = dict(os.environ)
    env.update(svc.get("env", {}))
    log_path = svc["log"]
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "ab") as logf:
            proc = subprocess.Popen(
                svc["cmd"],
                cwd=svc.get("cwd"),
                env=env,
                stdout=logf,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
        self_log("已拉起 %s:%s pid=%s -> %s" % (svc["name"], svc["port"], proc.pid, log_path))
        print("[watchdog] %s:%s 未监听，已拉起 pid=%s" % (svc["name"], svc["port"], proc.pid), flush=True)
        return True
    except Exception as e:  # noqa: BLE001
        self_log("拉起 %s 失败: %r" % (svc["name"], e))
        print("[watchdog] %s 拉起失败: %s" % (svc["name"], e), flush=True)
        return False


def main() -> int:
    check_only = "--check" in sys.argv
    self_log("watchdog 启动 mode=%s" % ("check" if check_only else "run"))
    for svc in SERVICES:
        up = is_listening(svc["port"])
        if check_only:
            state = "running" if up else "stopped"
            print("%s:%s %s" % (svc["name"], svc["port"], state), flush=True)
            self_log("check %s:%s -> %s" % (svc["name"], svc["port"], state))
        elif not up:
            launch(svc)
        else:
            self_log("%s:%s 已在监听，跳过" % (svc["name"], svc["port"]))
    self_log("watchdog 结束 mode=%s" % ("check" if check_only else "run"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
