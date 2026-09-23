# -*- coding: utf-8 -*-
"""验证 coursewares(pptx) 与 micro_lesson_video(mp4) 的 details 直链结构。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
D = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/resources/details"

PPX = "f1352581-9a9f-af34-9657-a94e247c44a2"   # 我是中国人 pptx
MP4 = "21660482-8dd9-5607-3b22-20f9fac1ea11"   # 我是中国人 mp4


def get(rid):
    r = requests.get(f"{D}/{rid}.json", headers=UA, timeout=20)
    return r.status_code, r.json()


def dump(rid, label):
    s, d = get(rid)
    print("=" * 70)
    print(label, rid, "status", s)
    cp = d.get("custom_properties", {})
    print("format:", cp.get("format"), "| size:", cp.get("size"))
    print("title:", d.get("title") or (d.get("global_title", {}) or {}).get("zh-CN"))
    print("-- custom_properties keys:", list(cp.keys()))
    for k, v in cp.items():
        if isinstance(v, str) and ("http" in v or "pdf" in v or "transcode" in v or "m3u8" in v):
            print(f"   cp.{k} = {v[:200]}")
        elif isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, str) and ("http" in vv or "pdf" in vv or "m3u8" in vv):
                    print(f"   cp.{k}.{kk} = {vv[:200]}")
    print("-- ti_items:", len(d.get("ti_items", [])))
    for it in d.get("ti_items", []):
        print(f"   flag={it.get('ti_file_flag')} fmt={it.get('ti_file_format')} "
              f"size={it.get('ti_size')} storage={str(it.get('ti_storage'))[:160]}")


dump(PPX, "PPTX 课件")
dump(MP4, "MP4 视频")
