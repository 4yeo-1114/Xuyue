# -*- coding: utf-8 -*-
"""定位 coursewares(pptx)/micro_lesson_video(mp4) 的 details 端点。"""
import requests

UA = {"User-Agent": "Mozilla/5.0"}
S1 = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2"

PPX = "f1352581-9a9f-af34-9657-a94e247c44a2"   # 我是中国人 pptx
MP4 = "21660482-8dd9-5607-3b22-20f9fac1ea11"   # 我是中国人 mp4

CAND = [
    "resources/details/{id}.json",
    "resources/coursewares/details/{id}.json",
    "resources/courseware/details/{id}.json",
    "national_lesson/resources/details/{id}.json",
    "resources/micro_lesson_video/details/{id}.json",
]


def probe(rid, label):
    print("=" * 70)
    print(label, rid)
    for c in CAND:
        u = f"{S1}/{c.format(id=rid)}"
        try:
            r = requests.get(u, headers=UA, timeout=15)
            ct = r.headers.get("content-type", "")
            body = r.text
            ok = r.status_code == 200 and "json" in ct
            print(f"  [{r.status_code}] {c}")
            if ok:
                import json
                d = json.loads(body)
                cp = d.get("custom_properties", {})
                print(f"      title={d.get('title')} format={cp.get('format')} ti_items={len(d.get('ti_items',[]))}")
                for k, v in list(cp.items()):
                    if isinstance(v, str) and ("http" in v or "pdf" in v or "transcode" in v):
                        print(f"      cp.{k} = {v[:150]}")
                for it in d.get("ti_items", [])[:4]:
                    print(f"      ti flag={it.get('ti_file_flag')} storage={str(it.get('ti_storage'))[:130]}")
            else:
                print(f"      {body[:100]}")
        except Exception as e:  # noqa: BLE001
            print(f"  [ERR] {c}: {type(e).__name__}")


probe(PPX, "PPTX 课件")
probe(MP4, "MP4 视频")
