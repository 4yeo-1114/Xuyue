# -*- coding: utf-8 -*-
"""验证钉钉「工作通知」发送权限 + getbymobile 手机号反查（一次性探测脚本，不进常驻代码）。

只做两件无副作用的事（都发到管理员自己）：
  1) asyncsend_v2 给管理员自己发一条测试工作通知（测「工作通知」发送权限 + agent_id 是否正确）；
  2) getbymobile 用管理员手机号反查 userid（测「通讯录成员手机号」读取权限，手机号匹配路径依赖它）。
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.dingtalk import _ding_token, _DING_BASE

# demo@grade.local 演示管理员：已绑定的钉钉 userid + 手机号
ADMIN_USERID = "08255256291939912825"
ADMIN_MOBILE = "13635811545"

tok = _ding_token()

print("=== 1) asyncsend_v2 发测试工作通知（测发送权限）===")
try:
    agent_id = int(settings.DINGTALK_AGENT_ID)
except (TypeError, ValueError):
    print(f"=> DINGTALK_AGENT_ID 非法：{settings.DINGTALK_AGENT_ID!r}")
    sys.exit(1)
msg = {
    "agent_id": agent_id,
    "userid_list": ADMIN_USERID,
    "msg": {
        "msgtype": "action_card",
        "action_card": {
            "title": "叙阅·钉钉推送测试",
            "markdown": "这是一条**测试**消息，用于验证「统分完成自动推送」链路。",
            "single_title": "查看",
            "single_url": "https://foil.6108.net",
        },
    },
}
r = requests.post(
    f"{_DING_BASE}/topapi/message/corpconversation/asyncsend_v2",
    params={"access_token": tok},
    json=msg,
    timeout=15,
).json()
print("返回:", r)
if r.get("errcode") == 0:
    print("=> 发送成功！请到钉钉「工作通知」查看测试消息")
else:
    print(f"=> 发送失败 errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
    print("   常见原因：agent_id 无效，或应用未开通「工作通知」发送权限，需在钉钉后台开启并重新发布")

print("\n=== 2) getbymobile 手机号反查（测通讯录手机号读取权限）===")
r2 = requests.post(
    f"{_DING_BASE}/topapi/v2/user/getbymobile",
    params={"access_token": tok},
    json={"mobile": ADMIN_MOBILE},
    timeout=15,
).json()
print("返回:", r2)
if r2.get("errcode") == 0:
    print(f"=> 成功，userid={(r2.get('result') or {}).get('userid')}")
else:
    print(f"=> getbymobile 失败 errcode={r2.get('errcode')} errmsg={r2.get('errmsg')}")
    print("   常见原因：未开「通讯录成员手机号」读取权限，或该手机号不在通讯录")
