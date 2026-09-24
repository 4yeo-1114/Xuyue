"""pytest 全局夹具入口。

背景：主目录 .env 已 fail-closed 清理（DB_* 被清空），本地起服务会因
app.config.Settings() 校验失败而 fail-fast，宁可不起来也不连生产库。
这导致 pytest 收集阶段 import app.config 时 Settings() 实例化即报错。

本文件用 os.environ.setdefault 注入占位 DB_*/JWT 配置，让测试在
fail-closed（.env 无 DB_*）环境下也能通过 Settings() 导入校验：
- setdefault 只设置缺省的键，不覆盖真实环境变量（CI/开发者已有配置时原样保留）
- 测试本身通过 mock 隔离数据库，不会真正连接 localhost:3306
- 不影响应用运行：应用仍读 .env（见 app/config._get_env_file），本文件只在
  pytest 收集阶段生效

注意：这些 setdefault 必须在任何 `from app import ...` 之前执行——
pytest 会最先加载根 conftest.py，放在顶层即满足该顺序要求。
"""

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-only-secret-key-01234567890123456789",  # 占位密钥，仅用于通过长度 >= 32 校验
)

# 测试永不对数据库执行 DDL。
# 理由：本机 backend/.env 里 `AUTO_DDL=true`，会让 app/database.py 在**导入期**就调用
# _ensure_database() 去连库；而上面把 DB_HOST 设成 localhost（pydantic-settings 口径：
# 环境变量 > .env 文件）⇒ 实际去连 localhost:3306 ⇒ 2003 Connection refused ⇒
# 任何在模块级 import app.database 的测试文件都在 **collection 阶段**就挂掉。
# 用 setdefault（⛔ 不是强制赋值）以保住本文件既有语义：只设缺省键、不覆盖真实环境变量，
# CI / 已自带配置的环境不受影响。收口自 test_e04/e05/e08/e09/e10 与
# test_users_dingtalk_userid_upgrade 各自重复的那 6 行 setdefault("AUTO_DDL", "false")。
os.environ.setdefault("AUTO_DDL", "false")
