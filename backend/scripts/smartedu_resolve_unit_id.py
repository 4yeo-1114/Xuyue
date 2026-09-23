# -*- coding: utf-8 -*-
"""确认详情 URL 的 contentId(=unit_id) 是课时叶子节点还是单元节点。"""
import re
import requests

t = requests.get("https://teacher.ykt.eduyun.cn/js/app-9879aaaa.js",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text

print("--- unit_id 赋值/来源上下文 ---")
seen = set()
for m in re.findall(r".{60}unit_id.{60}", t):
    if m in seen:
        continue
    seen.add(m)
    print(repr(m))
    if len(seen) >= 20:
        break

print("\n--- detail 拼接完整片段 (更长) ---")
for m in sorted(set(re.findall(r".{120}prepare/detail.{120}", t)))[:6]:
    print(repr(m))
