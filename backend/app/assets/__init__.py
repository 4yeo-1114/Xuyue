"""P0 资产引擎：家长端 PG 资产库只读接入（双库共存融合）。

仅提供只读数据库层（assets_base / assets_session / repo 查询），
不建表、不迁移、不写主 MySQL 业务。未配置 ASSETS_DB_* 时优雅降级。
"""
