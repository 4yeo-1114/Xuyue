# -*- coding: utf-8 -*-
"""syncClassroom 页面 UI 结构 + 抓 listing 接口：导航、等待、点筛选、捕获。"""
from pathlib import Path

from playwright.sync_api import sync_playwright

_here = Path(__file__).resolve().parent
USER_DATA = _here / ".smartedu_profile"

URL = "https://basic.smartedu.cn/syncClassroom/auto"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(USER_DATA), channel="msedge", headless=True,
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        captured = []

        def on_response(resp):
            url = resp.url
            if not any(k in url for k in ("ykt", "eduyun", "smartedu")):
                return
            low = url.lower()
            if any(k in low for k in ("lesson", "chapter", "course", "resource", "catalog", "list", "tree", "teach")):
                try:
                    ct = resp.headers.get("content-type", "") or ""
                except Exception:
                    ct = ""
                body = ""
                if "json" in ct:
                    try:
                        body = resp.text()[:400]
                    except Exception:
                        body = ""
                captured.append((resp.status, url, body))

        page.on("response", on_response)
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=40000)
        except Exception as e:  # noqa: BLE001
            print("goto", type(e).__name__)
        page.wait_for_timeout(9000)

        # 打印当前 URL 与所有可点元素文本
        print("FINAL URL:", page.url)
        for tag in ("button", "[role='tab']", "[role='radio']", "a", "li", "span"):
            try:
                els = page.eval_on_selector_all(
                    tag,
                    "els => els.map(e => (e.innerText||'').trim()).filter(t => t.length>=1 && t.length<=10)"
                )
                uniq = list(dict.fromkeys(els))
                if uniq:
                    print(f"{tag}: {uniq[:80]}")
            except Exception:
                pass

        print("\n==== 捕获接口 ====")
        seen = set()
        for status, url, body in captured:
            if url in seen:
                continue
            seen.add(url)
            print(f"[{status}] {url[:140]}")
            if body:
                print(f"    {body[:200]}")

        ctx.close()


if __name__ == "__main__":
    main()
