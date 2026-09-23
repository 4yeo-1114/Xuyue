# -*- coding: utf-8 -*-
"""一次性迁移：users 加 dingtalk_userid 列 + 绑定 demo@grade.local 的钉钉 userid（幂等）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text
from app.database import engine

TARGET_EMAIL = "demo@grade.local"
DINGTALK_USERID = "08255256291939912825"

insp = inspect(engine)
cols = [c["name"] for c in insp.get_columns("users")]

if "dingtalk_userid" not in cols:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN dingtalk_userid VARCHAR(64) NULL"))
    print("OK: added column dingtalk_userid")
else:
    print("SKIP: dingtalk_userid already exists")

with engine.begin() as conn:
    r = conn.execute(
        text("UPDATE users SET dingtalk_userid = :uid WHERE email = :em"),
        {"uid": DINGTALK_USERID, "em": TARGET_EMAIL},
    )
    print("bound rows:", r.rowcount)

with engine.connect() as conn:
    r = conn.execute(
        text("SELECT email, phone, dingtalk_userid FROM users WHERE email = :em"),
        {"em": TARGET_EMAIL},
    )
    for row in r:
        print("verify:", row)
