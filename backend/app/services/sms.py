"""阿里云短信发送（登录/注册合规）。

只用标准库（hmac/hashlib/base64/urllib）+ 已装 `requests` 手写 legacy RPC V1 签名，
不引入阿里云 SDK——与 dingtalk.py 手写 HTTP 的风格一致。

签名算法（阿里云短信 SendSms，Version=2017-05-25）：
  1. 公共参数（AccessKeyId/Action/SignatureMethod=HMAC-SHA1/SignatureNonce/Timestamp/Version）
     + 业务参数（PhoneNumbers/SignName/TemplateCode/TemplateParam）合并；
  2. 按 key 字典序 percent-encode（RFC3986，空格→%20，~ 不编码）拼成 CanonicalizedQueryString；
  3. StringToSign = "POST" + "&" + percent_encode("/") + "&" + percent_encode(CanonicalizedQueryString)；
  4. Signature = Base64(HMAC-SHA1(AccessKeySecret + "&", StringToSign))。
"""
import base64
import hashlib
import hmac
import time
import urllib.parse
import uuid

import requests

from app.config import settings


def _percent_encode(value: str) -> str:
    """阿里云 RPC 签名专用 percent-encode：与 urllib.quote 略有差异（~ 不编码、空格→%20）。"""
    return urllib.parse.quote(str(value), safe="~")


def _sign(access_key_secret: str, string_to_sign: str) -> str:
    key = (access_key_secret + "&").encode("utf-8")
    msg = string_to_sign.encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_sms(phone: str, code: str) -> None:
    """发送一条验证码短信到手机号。

    未配置 AccessKey/签名/模板时抛 RuntimeError（fail-closed，由路由层转 501）。
    阿里云返回 Code != "OK" 时抛 RuntimeError，避免「发送失败但提示已发」。
    """
    access_key_id = (settings.ALIYUN_SMS_ACCESS_KEY_ID or "").strip()
    access_key_secret = (settings.ALIYUN_SMS_ACCESS_KEY_SECRET or "").strip()
    sign_name = (settings.ALIYUN_SMS_SIGN_NAME or "").strip()
    template_code = (settings.ALIYUN_SMS_TEMPLATE_CODE or "").strip()
    endpoint = (settings.ALIYUN_SMS_ENDPOINT or "dysmsapi.aliyuncs.com").strip()

    if not access_key_id or not access_key_secret or not sign_name or not template_code:
        raise RuntimeError("短信未配置")

    params = {
        "AccessKeyId": access_key_id,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": "cn-hangzhou",
        "SignName": sign_name,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "TemplateCode": template_code,
        "TemplateParam": '{"code":"%s"}' % code,
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Version": "2017-05-25",
    }

    canonicalized = "&".join(
        "%s=%s" % (_percent_encode(k), _percent_encode(v))
        for k, v in sorted(params.items())
    )
    string_to_sign = "POST&%s&%s" % (
        _percent_encode("/"),
        _percent_encode(canonicalized),
    )
    params["Signature"] = _sign(access_key_secret, string_to_sign)

    url = "https://%s/" % endpoint
    try:
        resp = requests.post(url, data=params, timeout=15)
    except requests.RequestException as e:
        raise RuntimeError(f"短信发送请求失败: {e}") from e

    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(f"短信服务响应异常: HTTP {resp.status_code}")

    if body.get("Code") != "OK":
        raise RuntimeError(f"短信发送失败: {body.get('Code')} {body.get('Message')}")
