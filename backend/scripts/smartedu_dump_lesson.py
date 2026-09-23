# -*- coding: utf-8 -*-
"""dump 一个课程教学课时的子资源结构（类型/格式/直链/封面），用于反推课件+视频抓取。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
PREFIX_MP4 = "https://r1-ndr.ykt.cbern.com.cn"
PREFIX_STATIC = "https://cdncs.ykt.cbern.com.cn/v0.1/static"
REF = "cs_path:${ref-path}"


def resolve(it, fmt):
    st = it.get("ti_storage") or ""
    prefix = PREFIX_MP4 if fmt == "mp4" else PREFIX_STATIC
    if st.startswith(REF):
        return prefix + st[len(REF):]
    if st.startswith("http"):
        return st
    ss = it.get("ti_storages") or []
    for s in ss:
        if s.startswith("http"):
            return s
    return None


def main():
    u = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/resources/details/f3154132-92c9-4ba2-b528-dc9b929694a0.json"
    d = requests.get(u, headers=UA, timeout=20).json()
    for i, r in enumerate(d["relations"]["national_course_resource"]):
        cp = r.get("custom_properties") or {}
        title = (r.get("global_title") or {}).get("zh-CN", "") or r.get("title", "")
        print(f"--- [{i}] {r.get('resource_type_code')} / {title} ---")
        print(f"  id={r.get('id')}")
        print(f"  format={cp.get('format')} size={cp.get('size')} duration={cp.get('duration')}")
        th = cp.get("thumbnails") or []
        print(f"  thumbnails={th[:1]}")
        for it in (r.get("ti_items") or [])[:3]:
            print(f"  ti_item flag={it.get('ti_file_flag')} size={it.get('ti_size')}")
            print(f"    direct={resolve(it, cp.get('format'))}")


if __name__ == "__main__":
    main()
