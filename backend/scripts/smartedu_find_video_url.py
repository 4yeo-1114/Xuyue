# -*- coding: utf-8 -*-
"""从前端 JS 里挖 syncClassroom 课时详情 URL 与 catalogType 取值。"""
import re
import requests

t = requests.get("https://teacher.ykt.eduyun.cn/js/app-9879aaaa.js",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text

print("--- prepare/detail 上下文 ---")
for m in sorted(set(re.findall(r".{40}prepare/detail.{60}", t)))[:10]:
    print(repr(m))

print("\n--- syncClassroomSilent ---")
for m in sorted(set(re.findall(r".{25}syncClassroomSilent.{25}", t)))[:10]:
    print(repr(m))

print("\n--- catalogType=取值 ---")
for m in sorted(set(re.findall(r"catalogType=([a-zA-Z]+)", t)))[:20]:
    print(m)

print("\n--- contentId= 与 unit_id 组合 ---")
for m in sorted(set(re.findall(r".{30}contentId=.{50}", t)))[:15]:
    print(repr(m))

print("\n--- 详情路由 path 组合 (detail? ) ---")
for m in sorted(set(re.findall(r"concat\([^)]*\"(?:/syncClassroom|/detail)[^\"]*\"[^)]*\)", t)))[:15]:
    print(repr(m))
