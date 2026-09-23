# -*- coding: utf-8 -*-
"""智慧平台「电子教材」目录抓取 + 直链解析。

数据源（公开，无需登录）：
  - 标签树：  https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json
  - 版本清单：https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json
  - 教材清单：zxx/ndrs/resources/tch_material/part_100~103.json（每册教材一条，含 ti_items 直链信息）

用法：
    python scripts/smartedu_catalog.py --summary        # 只打印分类统计
    python scripts/smartedu_catalog.py --dump catalog.json  # 落盘完整目录（含直链）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

TAG_TREE_URL = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json"
VERSION_URL = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json"

# tag_dimension_id -> 中文维度名
DIM_NAMES = {
    "zxxxd": "学段", "zxxxk": "学科", "zxxbb": "版本", "zxxnj": "年级", "zxxcc": "册次",
    "5036342742": "类型", "tagView": "类型",
}

STATIC_PREFIX = "https://cdncs.ykt.cbern.com.cn/v0.1/static"
MP4_PREFIX = "https://r1-ndr.ykt.cbern.com.cn"


def get(url: str, timeout: int = 60) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r


def load_tag_map() -> dict:
    """返回 tag_id -> {dimension_id, name}，遍历 tag 树。"""
    data = get(TAG_TREE_URL).json()
    m: dict = {}

    def walk(node):
        tag_id = node.get("tag_id")
        dim = node.get("tag_dimension_id")
        name = node.get("tag_name")
        if tag_id:
            m[tag_id] = {"dim": dim, "name": name}
        for child in node.get("children", []) or []:
            walk(child)
        for child in node.get("hierarchies", []) or []:
            walk(child)

    walk(data)
    return m


def load_parts() -> list:
    """下载所有 part_*.json，返回合并后的教材列表。"""
    urls = get(VERSION_URL).json()["urls"].split(",")
    out: list = []
    for url in urls:
        data = get(url).json()
        out.extend(data if isinstance(data, list) else data.get("items", []))
        time.sleep(0.3)
    return out


def resolve_direct(ti_items, fmt, size) -> str | None:
    """从 ti_items 解析文件直链（公开，无需鉴权）。"""
    prefix = MP4_PREFIX if fmt == "mp4" else STATIC_PREFIX
    for item in ti_items or []:
        storage = item.get("ti_storage") or ""
        flag = item.get("ti_file_flag")
        if flag == "href" or (item.get("ti_size") == size and fmt != "mp4"):
            if storage.startswith("cs_path:${ref-path}"):
                return prefix + storage[len("cs_path:${ref-path}"):]
            return storage
    return None


def parse_entry(e: dict, tag_map: dict) -> dict:
    dims = {}
    for t in e.get("tag_list") or []:
        dim = t.get("tag_dimension_id")
        name = t.get("tag_name")
        if dim and name:
            dims.setdefault(dim, name)
    cp = e.get("custom_properties") or {}
    fmt = cp.get("format")
    size = cp.get("size")
    return {
        "id": e.get("id"),
        "title": e.get("title") or (e.get("global_title") or {}).get("zh-CN", ""),
        "学段": dims.get("zxxxd", ""),
        "学科": dims.get("zxxxk", ""),
        "版本": dims.get("zxxbb", ""),
        "年级": dims.get("zxxnj", ""),
        "册次": dims.get("zxxcc", ""),
        "format": fmt,
        "size": size,
        "direct_url": resolve_direct(e.get("ti_items"), fmt, size),
        "tag_ids": {t.get("tag_dimension_id"): t.get("tag_id") for t in e.get("tag_list") or []},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true", help="只打印分类统计")
    ap.add_argument("--dump", metavar="FILE", help="落盘完整目录 JSON")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tag_map = load_tag_map()
    print(f"标签树 tag 数：{len(tag_map)}")
    parts = load_parts()
    print(f"教材总条数：{len(parts)}")

    rows = [parse_entry(e, tag_map) for e in parts]
    with_url = [r for r in rows if r["direct_url"]]
    pdfs = [r for r in rows if r["format"] == "pdf"]
    print(f"可解析直链：{len(with_url)} / {len(rows)}，PDF：{len(pdfs)}")

    if args.summary:
        for dim in ("学段", "学科", "年级", "册次", "版本"):
            counts: dict = {}
            for r in rows:
                counts[r[dim]] = counts.get(r[dim], 0) + 1
            print(f"\n=== {dim} 分布（{len(counts)} 类）===")
            for k, v in sorted(counts.items(), key=lambda x: -x[1]):
                print(f"  {k}: {v}")

    if args.dump:
        Path(args.dump).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已写目录：{args.dump}（{len(rows)} 条）")


if __name__ == "__main__":
    main()
