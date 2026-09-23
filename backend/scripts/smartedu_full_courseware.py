# -*- coding: utf-8 -*-
"""打印课件/视频子资源完整 JSON，找 preview/transcode 直链。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/national_lesson"
TM_ID = "b7062df1-f929-458e-964c-d778f89ca255"


def main():
    res = requests.get(f"{BASE}/teachingmaterials/{TM_ID}/resources/part_100.json",
                       headers=UA, timeout=20).json()
    lesson = res[0]  # 我是中国人
    print("LESSON id:", lesson["id"], "title:", lesson["title"])
    for s in lesson["relations"]["national_course_resource"]:
        cp = s.get("custom_properties", {})
        if cp.get("format") in ("pptx", "mp4"):
            print("\n" + "=" * 70)
            print("SUB id:", s["id"], "| format:", cp.get("format"),
                  "| type:", s.get("resource_type_code"))
            print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
