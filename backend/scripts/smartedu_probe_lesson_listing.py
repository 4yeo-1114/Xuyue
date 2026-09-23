# -*- coding: utf-8 -*-
"""探测课程教学(national_lesson)的 listing 接口 + 视频 m3u8 结构 + 课件 pptx 源。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}

LISTING_CANDIDATES = [
    "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/national_lesson/version/data_version.json",
    "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/national_lesson_tag.json",
    "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/national_lesson/part_100.json",
]

M3U8 = "https://r1-ndr.ykt.cbern.com.cn/edu_product/esp/assets/65b57bf7-5414-11eb-96b8-fa20200c3759.t/zh-CN/1703757550158/videos/d56a625a-3c48-457e-8cac-445ccae9682d-1920x1080-true-6aa8655c01cdfca2ab88b8eb6bc29aeb-c1bc8a3f92a64184b908969a73c7fb81.m3u8"

LESSON = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/resources/details/f3154132-92c9-4ba2-b528-dc9b929694a0.json"


def main():
    print("===== listing 候选 =====")
    for u in LISTING_CANDIDATES:
        try:
            r = requests.get(u, headers=UA, timeout=20)
            print(f"[{r.status_code}] {u}  len={len(r.content)}")
            if r.status_code == 200:
                try:
                    j = r.json()
                    if isinstance(j, dict):
                        print("   keys:", list(j.keys())[:10])
                        if "urls" in j:
                            print("   urls:", j["urls"][:300])
                    elif isinstance(j, list):
                        print("   list len:", len(j), "first keys:", list(j[0].keys())[:12] if j else "-")
                except Exception as e:
                    print("   body:", r.text[:200])
        except Exception as e:
            print(f"[ERR] {u}: {type(e).__name__} {e}")

    print("\n===== m3u8 内容 =====")
    try:
        r = requests.get(M3U8, headers=UA, timeout=20)
        print("status:", r.status_code, "len:", len(r.content))
        print(r.text[:600])
    except Exception as e:
        print("ERR", e)

    print("\n===== coursewares 的 custom_properties 找 pptx 源 =====")
    d = requests.get(LESSON, headers=UA, timeout=20).json()
    for r in d["relations"]["national_course_resource"]:
        if r.get("resource_type_code") == "coursewares":
            cp = r.get("custom_properties") or {}
            print("keys:", list(cp.keys()))
            for k, v in cp.items():
                s = json.dumps(v, ensure_ascii=False)
                if len(s) > 140:
                    s = s[:140] + "..."
                print(f"  {k}: {s}")


if __name__ == "__main__":
    main()
