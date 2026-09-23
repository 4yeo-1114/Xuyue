# -*- coding: utf-8 -*-
"""探 national_lesson_tag.json 全貌 + areas/teachingmaterials 接口。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/national_lesson_tag.json"
API = "https://x-api.ykt.eduyun.cn/proxy/cloud/v1"


def show_tag(o, depth=0, maxd=3):
    """递归打印标签树，只打印结构骨架。"""
    if depth > maxd:
        return
    if isinstance(o, dict):
        keys = [k for k in o.keys() if k in ("name", "tag_id", "tag_dimension_id", "code", "title", "id", "children", "hierarchies")]
        brief = {k: (o[k] if not isinstance(o[k], (list, dict)) else f"<{type(o[k]).__name__}>") for k in keys if k in o}
        print("  " * depth, brief)
        for k in ("children", "hierarchies"):
            if isinstance(o.get(k), list):
                show_tag(o[k], depth + 1, maxd)
    elif isinstance(o, list):
        for it in o[:20]:
            show_tag(it, depth, maxd)
        if len(o) > 20:
            print("  " * depth, f"... {len(o)-20} more")


def main():
    print("===== national_lesson_tag.json =====")
    d = requests.get(BASE, headers=UA, timeout=20).json()
    print("TOP KEYS:", list(d.keys()))
    print("tag_path:", d.get("tag_path"))
    print("完整 JSON 前 1500 字符:")
    print(json.dumps(d, ensure_ascii=False, indent=1)[:1500])
    print("\n===== 结构树 =====")
    show_tag(d.get("hierarchies"), 0, 3)

    print("\n===== areas 接口 =====")
    for u in [
        f"{API}/areas",
        f"{API}/areas/zxxx/teachingmaterials",
        f"{API}/areas/zxxxd/teachingmaterials",
    ]:
        try:
            r = requests.get(u, headers=UA, timeout=15)
            print(f"[{r.status_code}] {u}")
            print("   ", r.text[:300])
        except Exception as e:
            print(f"[ERR] {u}: {e}")


if __name__ == "__main__":
    main()
