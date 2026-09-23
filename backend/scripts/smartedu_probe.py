# -*- coding: utf-8 -*-
"""智慧平台资源结构探针：验证「公开元数据 JSON → 直链」是否可通，不落库不下载。"""
import json
import sys
from pathlib import Path

import requests

_here = Path(__file__).resolve().parent

SAMPLES = {
    "教材-课本PDF": "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/1c73b348-e8b6-47d6-84b0-6dbacbe28268.json",
    "课程教学-课件(activity)": "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/resources/details/f3154132-92c9-4ba2-b528-dc9b929694a0.json",
}


def resolve_static_url(ti_items, file_format, file_size):
    prefixes = {
        "mp4": "https://r1-ndr.ykt.cbern.com.cn",
        "default": "https://cdncs.ykt.cbern.com.cn/v0.1/static",
    }
    prefix = prefixes["mp4"] if file_format == "mp4" else prefixes["default"]
    for item in ti_items or []:
        storage = item.get("ti_storage", "")
        flag = item.get("ti_file_flag")
        if flag == "href" or (item.get("ti_size") == file_size and file_format != "mp4"):
            if storage.startswith("cs_path:${ref-path}"):
                return prefix + storage[len("cs_path:${ref-path}"):]
            return storage
    return None


def main() -> None:
    for name, url in SAMPLES.items():
        print("=" * 60)
        print(name, "\n ", url)
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            print("  status:", r.status_code, "len:", len(r.content))
            if r.status_code != 200:
                print("  body:", r.text[:200])
                continue
            data = r.json()
            print("  title:", data.get("title"))
            cp = data.get("custom_properties", {})
            fmt = cp.get("format")
            size = cp.get("size")
            print("  format:", fmt, " size:", size)
            ti = data.get("ti_items", [])
            print("  ti_items:", len(ti))
            for it in ti[:3]:
                print("    - flag=", it.get("ti_file_flag"), "size=", it.get("ti_size"),
                      "storage=", str(it.get("ti_storage"))[:90])
            u = resolve_static_url(ti, fmt, size)
            print("  → 直链:", u)
            if u:
                h = requests.head(u, timeout=15, allow_redirects=True,
                                  headers={"User-Agent": "Mozilla/5.0"})
                print("  → HEAD:", h.status_code, "content-length:", h.headers.get("content-length"),
                      "type:", h.headers.get("content-type"))
        except Exception as e:  # noqa: BLE001
            print("  ERROR:", type(e).__name__, e)


if __name__ == "__main__":
    main()
