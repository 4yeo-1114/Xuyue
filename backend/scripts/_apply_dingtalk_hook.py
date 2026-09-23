# -*- coding: utf-8 -*-
"""在生产 router.py 统分完成点插入钉钉通知钩子（幂等、带唯一性校验）。

用法：python _apply_dingtalk_hook.py <router.py 路径>
只做一次精确替换：在 ai_auto_report 钩子之后、`return {` 之前插入姊妹 try 块。
若已含 dingtalk_notify 则跳过；锚点不唯一则中止，绝不盲目写。
"""
import sys
from pathlib import Path

TARGET = sys.argv[1]

ANCHOR = '''        print(f"[ai_auto_report] hook after scoring apply failed: {e}")

    return {
'''

INSERT = '''        print(f"[ai_auto_report] hook after scoring apply failed: {e}")

    try:
        # 统分完成自动钉钉工作通知（user_id 在请求上下文先取值再传参，避免子线程 contextvar 丢失）
        from app.services.dingtalk_notify import notify_grading_done

        notify_grading_done(get_grading_user_id(), safe)
    except Exception as e:
        print(f"[dingtalk_notify] hook after scoring apply failed: {e}")

    return {
'''

p = Path(TARGET)
src = p.read_text(encoding="utf-8")

if "dingtalk_notify" in src:
    print("已包含 dingtalk_notify，跳过")
    sys.exit(0)

n = src.count(ANCHOR)
if n != 1:
    print(f"锚点出现 {n} 次（应为 1），中止，未做任何修改")
    sys.exit(1)

src = src.replace(ANCHOR, INSERT)
p.write_text(src, encoding="utf-8")
print("插入成功")
