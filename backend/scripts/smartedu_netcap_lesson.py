# -*- coding: utf-8 -*-
"""抓课程教学(national_lesson)前端真实调用的 API（已登录 profile，headless）。

捕获所有 json/api 类响应，打印 URL+status+body 片段，用于反推课时 listing 接口。
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

_here = Path(__file__).resolve().parent
USER_DATA = _here / ".smartedu_profile"

KEYS = ("ykt.cbern.com.cn", "smartedu.cn", "eduyun.cn")

CANDIDATES = [
    "https://basic.smartedu.cn/tchCourse",
    "https://basic.smartedu.cn/tchMaterial",
    "https://basic.smartedu.cn/",
]


def main():
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
            if not any(k in url for k in KEYS):
                return
            try:
                ct = resp.headers.get("content-type", "") or ""
            except Exception:
                ct = ""
            # 只看 json/api，过滤图片/视频/css 静态
            if "json" in ct or "api" in url.lower() or "list" in url.lower() or "search" in url.lower() or "catalog" in url.lower():
                hits.append((resp.status, url, ct))

        page.on("response", on_response)

        for u in CANDIDATES:
            try:
                page.goto(u, wait_until="networkidle", timeout=30000)
            except Exception as e:  # noqa: BLE001
                print("goto", u, "->", type(e).__name__)
            page.wait_for_timeout(3000)

        # 顺便打印页面里跟「课程」相关的导航链接
        try:
            links = page.eval_on_selector_all(
                "a", "els => els.map(e => ({t: (e.innerText||'').trim(), h: e.href}))"
            )
            for l in links:
                if any(w in l["t"] for w in ("课程", "课件", "教学", "课")):
                    print("NAV:", l["t"][:20], l["h"])
        except Exception as e:  # noqa: BLE001
            print("nav dump err", e)

        print("\n==== 捕获到的 API 请求 ====")
        seen = set()
        for status, url, ct in hits:
            if url in seen:
                continue
            seen.add(url)
            print(f"  [{status}] {url[:160]}")
        ctx.close()


if __name__ == "__main__":
    main()
