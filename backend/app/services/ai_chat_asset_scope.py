# -*- coding: utf-8 -*-
"""AI 助教：资产库（家长端 PG 镜像）只读查询作用域。

- 资产库仅对 AI 助教暴露 5 张只读资产表，与 app/assets/models.py 一一对应。
- 敏感列剥离：家长端个人学习状态（user_id / mastery / is_weak，审核硬要求）与家长 PII
  （phone / email / password_hash / plain_password / city_code / city_name）在返回值中
  一律剔除，即使大模型拼出 SELECT mastery, user_id ... 也不带到模型上下文。
- 行级 user_id 白名单 scope 完整版留 P1：knowledge_points / subject_units 为家长端
  用户级表（user_id NOT NULL），本批先用敏感列剥离兜底，学校端 AI 演示读完整课标树/题库。
"""

from __future__ import annotations

# 资产库允许查询的表（与 app/assets/models.py 的表名严格一致，家长端 PG 镜像只读）
ASSET_ALLOWED_TABLES = frozenset(
    {
        "questions",
        "knowledge_points",
        "question_kp",
        "subject_units",
        "difficulty_gold",
    }
)

# 资产库返回结果集强制剥离的敏感列：
# - user_id / mastery / is_weak：家长端个人学习状态（审核硬要求）
# - phone / email / password_hash / plain_password / city_code / city_name：
#   家长端 users 表实际 PII 列（见父端 app/models/user.py）
# - mobile / address：防御性保留（父端 schema 若演进补列仍兜底剥离）
ASSET_SENSITIVE_COLUMNS = frozenset(
    {
        "user_id",
        "mastery",
        "is_weak",
        "phone",
        "mobile",
        "address",
        "email",
        "password_hash",
        "plain_password",
        "city_code",
        "city_name",
    }
)

# 家长端用户级表：user_id NOT NULL。
# 行级 user_id 白名单 scope 完整版留 P1（学校端 AI 演示读完整课标树），本批敏感列剥离兜底。
USER_SCOPED_TABLES = frozenset(
    {
        "knowledge_points",
        "subject_units",
    }
)
