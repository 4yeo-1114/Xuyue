# -*- coding: utf-8 -*-
"""抓取智慧平台「教材」目录页真实调用的 API（用于反推教材列表接口）。

只监听网络请求并打印 URL，不下载、不落库。
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

_here = Path(__file__).resolve().parent
USER_DATA = _here / ".smartedu_profile"

KEYS = ("ykt.cbern.com.cn", "smartedu.cn", "eduyun.cn")

# 教材页候选 URL（依次尝试）
URLS = [
    "https://basic.smartedu.cn/tchMaterial",
    "https://basic.smartedu.cn/",
]


def main() -> None:
    hits = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(USER_DATA),
            channel="msedge",
            headless=True,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            url = resp.url
            if any(k in url for k in KEYS):
                try:
                    ct = resp.headers.get("content-type", "")
                except Exception:
                    ct = ""
                # 只关注 json/api 类请求，过滤静态资源
                if "json" in ct or "api" in url.lower() or "list" in url.lower() or "search" in url.lower() or "catalog" in url.lower() or "tag" in url.lower():
                    hits.append((resp.status, url))

        page.on("response", on_response)

        for u in URLS:
            try:
                page.goto(u, wait_until="networkidle", timeout=30000)
            except Exception as e:  # noqa: BLE001
                print("goto", u, "->", type(e).__name__, e)
            page.wait_for_timeout(2500)

        print("==== 捕获到的 API 请求 ====")
        seen = set()
        for status, url in hits:
            if url in seen:
                continue
            seen.add(url)
            print(f"  [{status}] {url}")
        ctx.close()


if __name__ == "__main__":
    main()
