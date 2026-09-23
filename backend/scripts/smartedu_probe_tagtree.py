# -*- coding: utf-8 -*-
"""探测 national_lesson 标签树结构：是否含课时 ID，能否公开枚举全部课时。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
TAG = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/national_lesson_tag.json"


def main():
    d = requests.get(TAG, headers=UA, timeout=30).json()
    print("顶层 keys:", list(d.keys()))
    print("tag_path:", json.dumps(d.get("tag_path"), ensure_ascii=False)[:400])
    ext = d.get("ext") or {}
    print("ext:", json.dumps(ext, ensure_ascii=False)[:400])
    hier = d.get("hierarchies") or []
    print("hierarchies 顶层条数:", len(hier))

    # 递归统计层级 + 找带 resource id 的节点
    dims = {}

    def walk(node, depth, path):
        name = node.get("tag_name") or node.get("title") or ""
        dim = node.get("tag_dimension_id") or ""
        dims.setdefault((dim, name), 0)
        dims[(dim, name)] += 1
        keys = set(node.keys())
        # 若节点带资源相关字段，打印样例
        if depth <= 3 and any(k in keys for k in ("resource_id", "id", "custom_properties", "res", "url")):
            print(f"[depth {depth}] {path}/{name}  keys={sorted(keys)}")
        children = node.get("children") or node.get("hierarchies") or []
        for c in children[:3]:
            walk(c, depth + 1, f"{path}/{name}")

    for h in hier[:3]:
        walk(h, 0, "")

    print("\n=== 维度分布（tag_dimension_id / tag_name 计数）===")
    for (dim, name), cnt in sorted(dims.items()):
        print(f"  {dim} / {name}: {cnt}")


if __name__ == "__main__":
    main()
