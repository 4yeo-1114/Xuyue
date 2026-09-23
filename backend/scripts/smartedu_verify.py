# -*- coding: utf-8 -*-
"""验证：不同 download_policy 的教材，details 接口能否解析出可下载的 PDF 直链。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
PREFIX = "https://cdncs.ykt.cbern.com.cn/v0.1/static"
REF = "cs_path:${ref-path}"

PARTS = [
    "https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/part_100.json",
    "https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/part_101.json",
    "https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/part_102.json",
    "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/part_103.json",
]


def details(rid: str) -> dict:
    u = f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{rid}.json"
    return requests.get(u, headers=UA, timeout=20).json()


def resolve(d: dict):
    cp = d.get("custom_properties") or {}
    fmt = cp.get("format")
    size = cp.get("size")
    for it in d.get("ti_items") or []:
        st = it.get("ti_storage") or ""
        flag = it.get("ti_file_flag")
        if flag in ("source", "href") or (it.get("ti_size") == size and fmt != "mp4"):
            if st.startswith(REF):
                return PREFIX + st[len(REF):]
            return st
    return None


def main() -> None:
    # 每种 download_policy 各取一本 PDF 教材
    samples = {}
    for u in PARTS:
        for e in requests.get(u, headers=UA, timeout=60).json():
            p = (e.get("resource_custom_properties") or {}).get("download_policy")
            if p not in samples and (e.get("custom_properties") or {}).get("format") == "pdf":
                tags = {t.get("tag_dimension_id"): t.get("tag_name") for t in e.get("tag_list") or []}
                samples[p] = (e.get("id"), e.get("title"), tags.get("zxxxk"), tags.get("zxxnj"))

    for p, (rid, title, subj, grade) in samples.items():
        try:
            d = details(rid)
            u = resolve(d)
            h = requests.head(u, headers=UA, timeout=15, allow_redirects=True) if u else None
            print(f"policy={p} [{subj}/{grade}] {title[:24]}")
            print(f"   ti_items={len(d.get('ti_items') or [])}")
            print(f"   直链={u[:88] if u else None}")
            print(f"   HEAD={h.status_code if h else '-'} len={h.headers.get('content-length') if h else '-'} type={h.headers.get('content-type') if h else '-'}")
        except Exception as ex:  # noqa: BLE001
            print(f"policy={p} [{subj}/{grade}] {title[:24]} ERR {type(ex).__name__}: {ex}")


if __name__ == "__main__":
    main()
