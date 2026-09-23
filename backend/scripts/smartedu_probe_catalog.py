# -*- coding: utf-8 -*-
"""看教材 data_version.json 全貌 + 试课时 catalog 类型码。"""
import json
import requests

UA = {"User-Agent": "Mozilla/5.0"}

TV = "https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json"

TYPE_CODES = [
    "national_lesson", "tch_course", "course", "lesson", "sync_classroom",
    "micro_lesson", "courseware", "national_course", "tch_lesson",
]


def main():
    print("===== 教材 data_version.json =====")
    try:
        d = requests.get(TV, headers=UA, timeout=20).json()
        print(json.dumps(d, ensure_ascii=False, indent=1)[:800])
    except Exception as e:
        print("ERR", e)

    print("\n===== 试课时 catalog 类型码 (version/data_version.json) =====")
    for code in TYPE_CODES:
        u = f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/{code}/version/data_version.json"
        try:
            r = requests.get(u, headers=UA, timeout=15)
            ok = r.status_code == 200
            print(f"[{r.status_code}] {code}  {'OK' if ok else ''}")
            if ok:
                print("   ", r.text[:300])
        except Exception as e:
            print(f"[ERR] {code}: {type(e).__name__}")


if __name__ == "__main__":
    main()
