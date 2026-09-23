# -*- coding: utf-8 -*-
"""看课时资源条目的全部字段，找 unit_id / node / contentId 相关字段。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
NDRS = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/national_lesson"
TM_ID = "b7062df1-f929-458e-964c-d778f89ca255"


def main():
    res = requests.get(f"{NDRS}/teachingmaterials/{TM_ID}/resources/part_100.json",
                       headers=UA, timeout=20).json()
    l = res[0]
    print("顶层字段:", list(l.keys()))
    for k, v in l.items():
        if k in ("relations", "tag_list", "custom_properties", "ti_items"):
            continue
        print(f"  {k} = {json.dumps(v, ensure_ascii=False)[:120]}")
    # 看 custom_properties 里有没有 unit/node 相关
    cp = l.get("custom_properties", {})
    print("\ncustom_properties keys:", list(cp.keys()))
    for k, v in cp.items():
        if not isinstance(v, (list, dict)):
            print(f"  cp.{k} = {str(v)[:100]}")
    # 看有没有 chapter / unit 字段
    for k in ("chapter_ids", "teachmeterial_ids", "chapter_paths", "node_path", "unit_id", "parent_id"):
        if k in l:
            print(f"\n  {k} = {json.dumps(l[k], ensure_ascii=False)[:200]}")


if __name__ == "__main__":
    main()
