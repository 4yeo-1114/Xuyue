# -*- coding: utf-8 -*-
"""dump national_lesson 目录链结构：教材列表 / 课时树 / 课时资源。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/national_lesson"
V2 = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson"

TM_ID = "b7062df1-f929-458e-964c-d778f89ca255"  # 新教材-小学语文统编版一年级上册


def get(url):
    r = requests.get(url, headers=UA, timeout=20)
    return r.status_code, r.json() if "json" in (r.headers.get("content-type") or "") else r.text


def main():
    print("===== 1) 教材列表 part_100.json (前2条全字段) =====")
    s, data = get(f"{BASE}/teachingmaterials/part_100.json")
    print("status", s, "count", len(data))
    for it in data[:2]:
        print(json.dumps(it, ensure_ascii=False, indent=1)[:1800])

    print("\n===== 2) 课时树 trees/{TM_ID}.json =====")
    s, tree = get(f"{V2}/trees/{TM_ID}.json")
    print("status", s, "top-level count", len(tree) if isinstance(tree, list) else "?")
    print(json.dumps(tree, ensure_ascii=False, indent=1)[:2500])

    print("\n===== 3) 教材课时资源 resources/part_100.json (前1条) =====")
    s, res = get(f"{BASE}/teachingmaterials/{TM_ID}/resources/part_100.json")
    print("status", s, "count", len(res) if isinstance(res, list) else "?")
    if isinstance(res, list) and res:
        print(json.dumps(res[0], ensure_ascii=False, indent=1)[:2200])


if __name__ == "__main__":
    main()
