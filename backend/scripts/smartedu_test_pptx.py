# -*- coding: utf-8 -*-
"""智慧平台课件 PPTX 鉴权下载链路测试（单资源验证）。"""
import base64
import hashlib
import hmac
import json
import random
import re
import string
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

_here = Path(__file__).resolve().parent
SESSION = json.loads((_here / "smartedu_session.json").read_text(encoding="utf-8"))

# ---- 从 session 解析 token ----
def _token_field(name: str) -> str:
    for k, v in SESSION["localStorage"].items():
        if "token" in k.lower() and v and len(v) > 20:
            inner = json.loads(v)          # {"value": "...", "expire": ...}
            core = json.loads(inner["value"])
            return core.get(name, "")
    return ""

ACCESS_TOKEN = _token_field("access_token")
MAC_KEY = _token_field("mac_key")
DIFF = _token_field("diff") or "379"


def auth_encrypt(url: str, method_type: str) -> str:
    ms = int(time.time() * 1000)
    rnd = "".join(random.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(8))
    nonce = f"{ms + int(DIFF)}:{rnd}"
    p = urlparse(url)
    rel = p.path + (f"?{p.query}" if p.query else "")
    sig_str = f"{nonce}\n{method_type}\n{rel}\n{p.netloc}\n"
    mac = base64.b64encode(hmac.new(MAC_KEY.encode(), sig_str.encode(), hashlib.sha256).digest()).decode()
    return f'MAC id="{ACCESS_TOKEN}",nonce="{nonce}",mac="{mac}"'


def get_app_id() -> str:
    r = requests.get("https://auth.smartedu.cn/uias/login", timeout=15)
    m = re.search(r'sdpAppId:\s*"([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12})"', r.text)
    return m.group(1) if m else ""


def main() -> None:
    print("access_token 前16:", ACCESS_TOKEN[:16], "len", len(ACCESS_TOKEN))
    print("mac_key:", MAC_KEY, "diff:", DIFF)
    app_id = get_app_id()
    print("app_id:", app_id)
    if not app_id:
        print("!! 未提取到 app_id")
        return

    rid = "4cde9a8a-84a8-ce61-10d5-4036358b9ae2"
    url = f"https://doc-center.ykt.eduyun.cn/v1.0/c/document/{rid}?path=&_r={int(time.time()*1000)}"
    auth = auth_encrypt(url, "GET")
    headers = {"Authorization": auth, "sdp-app-id": app_id, "User-Agent": "Mozilla/5.0"}
    print("\nGET", url)
    print("  Authorization:", auth[:80], "...")
    r = requests.get(url, headers=headers, timeout=15)
    print("  status:", r.status_code)
    print("  body:", r.text[:400])
    if r.status_code == 200:
        data = r.json()
        cp = data.get("custom_properties", {})
        fmt, size = cp.get("format"), cp.get("size")
        print("  format/size:", fmt, size)
        for it in data.get("ti_items", []):
            print("    flag=", it.get("ti_file_flag"), "size=", it.get("ti_size"),
                  "storage=", str(it.get("ti_storage"))[:100])


if __name__ == "__main__":
    main()
