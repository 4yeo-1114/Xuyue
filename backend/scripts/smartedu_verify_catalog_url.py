# -*- coding: utf-8 -*-
"""验证教材目录页 URL（syncClassroom?defaultTag=...）能否渲染出课时列表。"""
import requests
from playwright.sync_api import sync_playwright

UA = {"User-Agent": "Mozilla/5.0"}
NDRS = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/national_lesson"
TM_ID = "b7062df1-f929-458e-964c-d778f89ca255"


def main():
    res = requests.get(f"{NDRS}/teachingmaterials/{TM_ID}/resources/part_100.json",
                       headers=UA, timeout=20).json()
    l = res[0]
    tags = {t["tag_dimension_id"]: t["tag_name"] for t in l.get("tag_list", [])}
    print("课时条目 tag_list:", tags)
    print("期望标题:", l["title"])

    # defaultTag 顺序：学段/年级/学科/版本/册次/教材
    path = "/".join(tags.get(k, "") for k in ("zxxxd", "zxxnj", "zxxxk", "zxxbb", "zxxcc", "zxxxjjc"))
    url = f"https://basic.smartedu.cn/syncClassroom?defaultTag={path}"
    print("\n目录页 URL:", url)

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(9000)
        txt = pg.inner_text("body")
        print("标题出现:", l["title"] in txt)
        print("文本前 600 字:", txt[:600].strip().replace("\n", " ")[:600])
        b.close()


if __name__ == "__main__":
    main()
