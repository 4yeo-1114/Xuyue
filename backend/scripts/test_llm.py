# -*- coding: utf-8 -*-
"""文本大模型(DeepSeek via LLM_*) 连通性与质量自测。

用法（在 backend 根目录跑，让 app.config 读到 .env）：
    /d/anconda/python scripts/test_llm.py

结果同时写到 scripts/test_llm_out.txt（UTF-8），避免 Windows 控制台中文乱码。
不硬编码任何密钥：配置走 .env 的 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。
"""
import sys
import time
from pathlib import Path

import requests

# 与 seed 脚本一致：先把 backend 根目录加进 sys.path，再 import app.*
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.utils.qwen_settings import get_llm_config  # noqa: E402


# (用例名, prompt) —— 覆盖后端最常用的几种能力
CASES = [
    ("简单问答", "用一句话回答：1+1 等于几？"),
    ("中文表达", "请用一句通顺的中文解释什么是「因材施教」。"),
    ("JSON 结构化", "请只返回一个 JSON 对象、不要任何解释和代码块：{\"学科\":\"数学\",\"难度\":\"中等\",\"知识点\":[\"分数\",\"小数\"]}"),
    ("文本概括", "把下面这段浓缩成 20 字以内的一句话：\"小明这学期数学成绩稳步提升，从期中的 72 分进步到期末的 88 分，错题订正也很及时，但计算题粗心问题仍然存在，需要在草稿纸上养成列竖式验算的习惯。\""),
]


def main() -> None:
    base_url, api_key, model = get_llm_config()
    lines: list[str] = []
    lines.append(f"base_url = {base_url}")
    lines.append(f"model    = {model}")
    lines.append(f"api_key  = {'已配置' if api_key else '未配置'}")
    lines.append("=" * 70)

    for name, prompt in CASES:
        t0 = time.time()
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "enable_thinking": False,
            "max_tokens": 1000,
        }
        try:
            resp = requests.post(
                base_url + "/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                timeout=120,
            )
            data = resp.json()
            msg = (data.get("choices") or [{}])[0].get("message", {}) or {}
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")
            usage = data.get("usage") or {}
            dt = round(time.time() - t0, 1)
            lines.append(f"[{name}] HTTP {resp.status_code} · {dt}s · tokens={usage.get('total_tokens')}")
            lines.append(f"  正文  : {content[:400]}")
            if reasoning:
                lines.append(f"  思考  : {reasoning[:100]}…")
        except Exception as exc:  # noqa: BLE001
            dt = round(time.time() - t0, 1)
            lines.append(f"[{name}] 失败 · {dt}s · {exc}")
        lines.append("-" * 70)

    text = "\n".join(lines) + "\n"
    with open("scripts/test_llm_out.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
