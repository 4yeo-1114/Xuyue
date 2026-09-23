# -*- coding: utf-8 -*-
"""抓课程教学 syncClassroom 页面真实调用的 API，记录 json 响应体片段。"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

_here = Path(__file__).resolve().parent
USER_DATA = _here / ".smartedu_profile"

KEYS = ("ykt.cbern.com.cn", "smartedu.cn", "eduyun.cn")

CANDIDATES = [
    "https://basic.smartedu.cn/syncClassroom/auto",
    "https://basic.smartedu.cn/syncClassroom/prepare",
]


def main():
    hits = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(USER_DATA), channel="msedge", headless=True,
            viewport={"width": 1400, "height": 900},
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
            low = url.lower()
            if "json" in ct or "api" in low or "list" in low or "course" in low or "lesson" in low or "chapter" in low or "catalog" in low or "resource" in low:
                body = ""
                if "json" in ct:
                    try:
                        body = resp.text()[:260]
                    except Exception:
                        body = ""
                hits.append((resp.status, url, body))

        page.on("response", on_response)
        for u in CANDIDATES:
            try:
                page.goto(u, wait_until="networkidle", timeout=40000)
            except Exception as e:  # noqa: BLE001
                print("goto", u, "->", type(e).__name__)
            page.wait_for_timeout(4000)

        seen = set()
        for status, url, body in hits:
            if url in seen:
                continue
            seen.add(url)
            print(f"[{status}] {url[:150]}")
            if body:
                print(f"    BODY: {body[:220]}")

        # 页面上跟教材/课程选择器相关的元素文本
        try:
            txt = page.eval_on_selector_all(
                "body *", "els => els.filter(e=>e.children.length===0).map(e=>(e.innerText||'').trim()).filter(t=>t.length>0&&t.length<12)"
            )
            print("\n短文本元素(可能含学段/学科/册次):", list(dict.fromkeys(txt))[:60])
        except Exception as e:  # noqa: BLE001
            print("dump err", e)
        ctx.close()


if __name__ == "__main__":
    main()
