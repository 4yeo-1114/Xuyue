# -*- coding: utf-8 -*-
"""用无头浏览器验证详情页 URL：contentId 该用课时节点还是单元节点，以及 contentType/catalogType 取值。"""
import json
import sys
import time

import requests
from playwright.sync_api import sync_playwright

UA = {"User-Agent": "Mozilla/5.0"}
NDRS = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/national_lesson"
TM_ID = "b7062df1-f929-458e-964c-d778f89ca255"


def lesson_chapters():
    res = requests.get(f"{NDRS}/teachingmaterials/{TM_ID}/resources/part_100.json",
                       headers=UA, timeout=20).json()
    l = res[0]
    return l["title"], l.get("chapter_ids") or [], l.get("id")


def check(url, expect_title):
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(8000)
            txt = pg.inner_text("body")
            hit = expect_title in txt
            print(f"\n[{url}]")
            print(f"  期望标题「{expect_title}」出现: {hit}")
            print(f"  页面文本前 400 字: {txt[:400].strip()!r}")
            return hit
        finally:
            b.close()


title, ch, lid = lesson_chapters()
print(f"lesson title={title} chapter_ids={ch} resource id={lid}")
unit_id, lesson_id = ch[0], ch[-1]

# 候选 URL 形式
cands = []
for cid, label in [(lesson_id, "课时节点 chapter_ids[-1]"), (unit_id, "单元节点 chapter_ids[0]")]:
    cands.append((f"https://basic.smartedu.cn/syncClassroom/prepare/detail?contentId={cid}&catalogType=syncClassroom",
                  f"{label} + catalogType=syncClassroom"))
    cands.append((f"https://basic.smartedu.cn/syncClassroom/prepare/detail?contentType=national_lesson&contentId={cid}&catalogType=syncClassroom",
                  f"{label} + contentType=national_lesson"))

for url, label in cands:
    print("\n" + "=" * 80)
    print("测试:", label)
    try:
        check(url, title)
    except Exception as e:  # noqa: BLE001
        print("  异常:", type(e).__name__, str(e)[:200])
