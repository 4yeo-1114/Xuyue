# -*- coding: utf-8 -*-
"""用 MAC 鉴权试课程教学 listing 接口（version manifest / part 分片）。"""
import json
import requests
from smartedu_test_pptx import auth_encrypt, ACCESS_TOKEN, get_app_id

UA = {"User-Agent": "Mozilla/5.0"}
APP_ID = get_app_id()

CANDIDATES = [
    "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/national_lesson/version/data_version.json",
    "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/national_lesson/part_0.json",
    "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/national_lesson/part_1.json",
]


def signed_get(url):
    auth = auth_encrypt(url, "GET")
    headers = {"Authorization": auth, "sdp-app-id": APP_ID, "User-Agent": "Mozilla/5.0"}
    return requests.get(url, headers=headers, timeout=20)


def main():
    print("app_id:", APP_ID)
    for u in CANDIDATES:
        try:
            r = signed_get(u)
            print(f"[{r.status_code}] {u}  len={len(r.content)}")
            if r.status_code == 200:
                try:
                    j = r.json()
                    if isinstance(j, dict):
                        print("   keys:", list(j.keys())[:10])
                        if "urls" in j:
                            print("   urls:", str(j["urls"])[:400])
                    elif isinstance(j, list):
                        print("   list len:", len(j), "first keys:", list(j[0].keys())[:14] if j else "-")
                except Exception:
                    print("   body:", r.text[:200])
            else:
                print("   body:", r.text[:160])
        except Exception as e:
            print(f"[ERR] {u}: {type(e).__name__} {e}")


if __name__ == "__main__":
    main()
