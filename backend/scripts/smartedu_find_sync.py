# -*- coding: utf-8 -*-
"""找「课程教学」真实页面 URL，并 dump 筛选控件 + 抓 listing 接口。"""
from pathlib import Path

from playwright.sync_api import sync_playwright

_here = Path(__file__).resolve().parent
USER_DATA = _here / ".smartedu_profile"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(USER_DATA), channel="msedge", headless=True,
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 1) 首页拿「课程教学」链接
        try:
            page.goto("https://basic.smartedu.cn/", wait_until="domcontentloaded", timeout=40000)
        except Exception as e:  # noqa: BLE001
            print("home goto", type(e).__name__)
        page.wait_for_timeout(5000)
        links = page.eval_on_selector_all(
            "a", "els => els.map(e => ({t:(e.innerText||'').trim(), h:e.href}))"
        )
        target = None
        for l in links:
            if "课程教学" in l["t"]:
                print("课程教学 ->", l["h"])
                target = l["h"]
        print("首页 URL:", page.url)

        # 2) 进课程教学页
        if target:
            try:
                page.goto(target, wait_until="domcontentloaded", timeout=40000)
            except Exception as e:  # noqa: BLE001
                print("goto sync", type(e).__name__)
            page.wait_for_timeout(8000)
            print("\n课程教学页 URL:", page.url)

            # 抓响应
            hits = []

            def on_response(resp):
                url = resp.url
                if not any(k in url for k in ("ykt", "eduyun", "smartedu", "cbern")):
                    return
                low = url.lower()
                if any(k in low for k in ("lesson", "chapter", "course", "catalog", "list", "resource", "teach", "unit", "tree", "tag")):
                    try:
                        ct = resp.headers.get("content-type", "") or ""
                    except Exception:
                        ct = ""
                    body = ""
                    if "json" in ct:
                        try:
                            body = resp.text()[:350]
                        except Exception:
                            body = ""
                    hits.append((resp.status, url, body))

            page.on("response", on_response)

            # 3) dump 所有可点筛选控件文本
            print("\n==== 可点控件 ====")
            for sel in ("[class*='select']", "[class*='filter']", "[class*='tab']", "button", "[role='tab']"):
                try:
                    els = page.eval_on_selector_all(
                        sel,
                        "els => els.map(e => (e.innerText||'').trim()).filter(t => t.length>=1 && t.length<=16)"
                    )
                    uniq = list(dict.fromkeys(els))
                    if uniq:
                        print(f"{sel}: {uniq[:60]}")
                except Exception:
                    pass

            print("\n==== 页面文本(leaf) ====")
            try:
                txt = page.eval_on_selector_all(
                    "body *",
                    "els => els.filter(e=>e.children.length===0).map(e=>(e.innerText||'').trim()).filter(t=>t.length>0&&t.length<8)"
                )
                print(list(dict.fromkeys(txt))[:120])
            except Exception as e:  # noqa: BLE001
                print("txt err", e)

            print("\n==== 捕获接口 ====")
            seen = set()
            for status, url, body in hits:
                if url in seen:
                    continue
                seen.add(url)
                print(f"[{status}] {url[:150]}")
                if body:
                    print(f"    {body[:200]}")

        ctx.close()


if __name__ == "__main__":
    main()
