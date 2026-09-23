# -*- coding: utf-8 -*-
"""国家中小学智慧教育平台「登录抓取」：弹出 Edge 让用户登录，自动读 localStorage/cookie 存盘。

用途：拿到 access_token + mac_key，供后续课件 PDF 下载器做 MAC 签名鉴权。
本脚本不碰用户名密码，用户自己在弹出的浏览器窗口里完成登录（扫码/短信/验证码都行）。

产物：scripts/smartedu_session.json（含 localStorage 全量 + cookies）。
运行：python scripts/smartedu_login.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = "https://basic.smartedu.cn/"
_here = Path(__file__).resolve().parent
OUT = _here / "smartedu_session.json"
USER_DATA = _here / ".smartedu_profile"
TIMEOUT_SECONDS = 8 * 60


def _read_localstorage(page) -> dict:
    return page.evaluate(
        "() => { const o = {}; for (let i = 0; i < localStorage.length; i++) {"
        " const k = localStorage.key(i); o[k] = localStorage.getItem(k); } return o; }"
    )


def _looks_logged_in(ls: dict) -> bool:
    for k, v in (ls or {}).items():
        kl = k.lower()
        if ("token" in kl or "auth" in kl) and v and len(v) > 20:
            return True
    return False


def main() -> None:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(USER_DATA),
            channel="msedge",
            headless=False,
            viewport={"width": 1280, "height": 820},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(SITE)
        print("已打开 Edge 窗口，请在浏览器里登录智慧教育平台……")

        ls: dict = {}
        start = time.time()
        while time.time() - start < TIMEOUT_SECONDS:
            try:
                ls = _read_localstorage(page)
            except Exception:
                ls = {}
            if _looks_logged_in(ls):
                break
            time.sleep(2)

        if not _looks_logged_in(ls):
            # 超时也尽量落盘，方便排查当前到底有哪些键
            try:
                ls = _read_localstorage(page)
            except Exception:
                ls = {}
            OUT.write_text(
                json.dumps({"localStorage": ls, "cookies": ctx.cookies(), "timeout": True}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"超时未检测到登录态（已把现有 localStorage 写入 {OUT}，可能未登录）")
            ctx.close()
            return

        data = {"localStorage": ls, "cookies": ctx.cookies(), "timeout": False}
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 已检测到登录态，写入 {OUT}")
        print("localStorage 键概览：")
        for k, v in ls.items():
            print(f"  {k}  (len={len(v or '')})")
        ctx.close()


if __name__ == "__main__":
    main()
