# -*- coding: utf-8 -*-
"""dump 单个课时的 relations.national_course_resource 子资源结构（PPT/视频）。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/national_lesson"
TM_ID = "b7062df1-f929-458e-964c-d778f89ca255"


def get(url):
    r = requests.get(url, headers=UA, timeout=20)
    return r.json()


def summarize(res):
    """递归挑出能识别子资源类型/URL 的字段。"""
    out = {}
    for k, v in res.items():
        if k in ("id", "title", "global_title", "format", "type", "resource_type_code",
                 "resource_type_code_name", "custom_properties", "ti_items", "relations"):
            out[k] = v
    return out


def main():
    res = get(f"{BASE}/teachingmaterials/{TM_ID}/resources/part_100.json")
    print("lessons count:", len(res))
    for lesson in res[:6]:
        print("\n" + "=" * 70)
        print("LESSON id:", lesson.get("id"), "| title:", lesson.get("title"),
              "| format:", lesson.get("custom_properties", {}).get("format"),
              "| type:", lesson.get("custom_properties", {}).get("prom_resouce_type"))
        sub = lesson.get("relations", {}).get("national_course_resource", [])
        print(f"  sub-resources: {len(sub)}")
        for s in sub:
            cp = s.get("custom_properties", {})
            fmt = cp.get("format")
            print(f"  - id={s.get('id')} title={s.get('global_title',{}).get('zh-CN')} "
                  f"type={cp.get('resource_type') or s.get('resource_type_code')} format={fmt}")
            if fmt in ("pptx", "ppt", "pdf"):
                for k, v in cp.items():
                    if isinstance(v, str) and ("http" in v or "transcode" in v or "pdf" in v):
                        print(f"      cp.{k} = {v[:160]}")
                for it in s.get("ti_items", []):
                    print(f"      ti flag={it.get('ti_file_flag')} fmt={it.get('ti_file_format')} "
                          f"storage={str(it.get('ti_storage'))[:120]}")
            if fmt == "mp4":
                for k, v in cp.items():
                    if isinstance(v, str) and "http" in v:
                        print(f"      cp.{k} = {v[:160]}")
                for it in s.get("ti_items", []):
                    print(f"      ti flag={it.get('ti_file_flag')} storage={str(it.get('ti_storage'))[:120]}")


if __name__ == "__main__":
    main()
