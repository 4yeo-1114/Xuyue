# -*- coding: utf-8 -*-
"""完整标签树(带名字) + teachingmaterials/lessons 列表接口探测。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
TAG_URL = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/national_lesson_tag.json"
API = "https://x-api.ykt.eduyun.cn/proxy/cloud/v1"

# 已知的 春夏秋冬 课的 teachingmaterial_id
TM_ID = "2fbcdb5d-0682-4cca-b979-076d0119e3d3"


def walk(node, depth=0, maxd=5):
    if depth > maxd or node is None:
        return
    if isinstance(node, list):
        for it in node:
            walk(it, depth, maxd)
        return
    if isinstance(node, dict):
        name = node.get("tag_name") or node.get("name") or ""
        dim = node.get("tag_dimension_id", "")
        tid = node.get("tag_id", "")
        ext = node.get("ext") or {}
        marker = " *HASRES*" if ext.get("has_res") else ""
        print("  " * depth + f"[{dim}] {name}  ({tid}){marker}")
        for k in ("children", "hierarchies"):
            if isinstance(node.get(k), list):
                walk(node[k], depth + 1, maxd)


def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=15)
        return r.status_code, r.text
    except Exception as e:  # noqa: BLE001
        return "ERR", str(e)


def main():
    d = requests.get(TAG_URL, headers=UA, timeout=20).json()
    print("ext:", d.get("ext"), "tenant_id:", d.get("tenant_id"))
    print("===== 完整标签树 =====")
    walk(d.get("hierarchies"), 0, 6)

    print("\n===== teachingmaterials 接口(用真实学段tag_id) =====")
    for area in ["e7bbb2de-0590-11ed-9c79-92fc3b3249d5",  # 学段1
                 "e7bbce2c-0590-11ed-9c79-92fc3b3249d5",  # 学段2
                 "44beb9aa-54e6-11ed-9c34-850ba61fa9f4",  # 学段3
                 "44beb932-54e6-11ed-9c34-850ba61fa9f4",  # 学段4
                 ]:
        s, t = get(f"{API}/areas/{area}/teachingmaterials")
        print(f"[{s}] areas/{area}/teachingmaterials -> {t[:400]}")

    print("\n===== lessons 列表接口(用已知 teachingmaterial_id) =====")
    for u in [
        f"{API}/teachingmaterials/{TM_ID}/lessons",
        f"{API}/teachingmaterials/{TM_ID}/chapters",
        f"{API}/lessons?teachingmaterial_id={TM_ID}",
        f"{API}/teachingmaterials/{TM_ID}",
    ]:
        s, t = get(u)
        print(f"[{s}] {u}")
        print("    ", t[:400])


if __name__ == "__main__":
    main()
