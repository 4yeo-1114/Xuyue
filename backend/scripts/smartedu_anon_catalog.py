# -*- coding: utf-8 -*-
"""匿名上下文进 /syncClassroom/auto，抓课程目录 listing 接口 + 点筛选。"""
from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        hits = []

        def on_response(resp):
            url = resp.url
            if not any(k in url for k in ("ykt", "eduyun", "smartedu", "cbern")):
                return
            try:
                ct = resp.headers.get("content-type", "") or ""
            except Exception:
                ct = ""
            low = url.lower()
            if "json" in ct or any(k in low for k in ("lesson", "chapter", "catalog", "list", "resource", "teach", "unit", "tag", "course")):
                body = ""
                if "json" in ct:
                    try:
                        body = resp.text()[:300]
                    except Exception:
                        body = ""
                hits.append((resp.status, url, body))

        page.on("response", on_response)
        try:
            page.goto("https://basic.smartedu.cn/syncClassroom/auto",
                      wait_until="domcontentloaded", timeout=45000)
        except Exception as e:  # noqa: BLE001
            print("goto", type(e).__name__)
        page.wait_for_timeout(10000)

        print("FINAL URL:", page.url)
        print("TITLE:", page.title())

        # 抓接口
        print("\n==== 接口 ====")
        seen = set()
        for status, url, body in hits:
            if url in seen:
                continue
            seen.add(url)
            print(f"[{status}] {url[:150]}")
            if body:
                print(f"    {body[:200]}")

        # 点筛选：尝试点「小学」「语文」「统编版」等文本
        def click_text(txt):
            try:
                el = page.get_by_text(txt, exact=True).first
                if el:
                    el.click(timeout=3000)
                    page.wait_for_timeout(2500)
                    print(f"\n[clicked] {txt} -> URL {page.url}")
                    return True
            except Exception as e:  # noqa: BLE001
                print(f"[click fail] {txt}: {type(e).__name__}")
            return False

        for t in ("小学", "一年级", "语文", "统编版", "上册"):
            click_text(t)

        print("\n==== 点击后新增接口 ====")
        for status, url, body in hits:
            if url in seen:
                continue
            seen.add(url)
            print(f"[{status}] {url[:150]}")
            if body:
                print(f"    {body[:250]}")

        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
