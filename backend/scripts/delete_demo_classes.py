# -*- coding: utf-8 -*-
"""删除全部「演示-」班级及其关联数据，只保留 12 个旧班（及其学生/报表/考试数据）。

安全护栏：DB_NAME 必须为 xuyue（独立库），否则拒绝运行。
覆盖范围（只动演示数据，绝不碰旧班/其它账号）：
  1. 所有含 class_id 的表        —— 按「演示-」班级删除
  2. 所有含 student_id 的表      —— 按「演示-」学生删除
  3. students / classes          —— 删除 1222 学生 + 24 班
  4. demo_student_*@grade.local  —— 学生账户 + user_roles
  5. demo@ 的演示辅助数据          —— 智能组卷/题型模板/批改量/健康/兑换/积分

保留：demo@、admin@、teacher@/headteacher@/principal@ 账户、schools、12 个旧班及其数据。

用法（云端，env 显式覆盖，密码不落盘）：
  DB_HOST=... DB_USER=xuyue DB_PASSWORD=... DB_NAME=xuyue \
  /opt/gradebuddy_venv311/bin/python scripts/delete_demo_classes.py
"""
import os
import sys

import pymysql

if os.environ.get("DB_NAME") != "xuyue":
    print(f"[拒绝运行] DB_NAME 必须为 xuyue（独立库），当前为 {os.environ.get('DB_NAME')!r}")
    sys.exit(1)

conn = pymysql.connect(
    host=os.environ["DB_HOST"],
    port=int(os.environ.get("DB_PORT", "3306")),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"],
    charset="utf8mb4",
    autocommit=False,
)
cur = conn.cursor()


def q(sql, args=None):
    cur.execute(sql, args)
    return cur.fetchall()


def affected():
    return cur.rowcount


# ── 0) 快照规模（先打印，再执行）──
n_cls = q("SELECT COUNT(*) FROM classes WHERE name LIKE %s", ("演示-%",))[0][0]
n_stu = q("SELECT COUNT(*) FROM students WHERE class_id IN (SELECT id FROM classes WHERE name LIKE %s)", ("演示-%",))[0][0]
n_du = q("SELECT COUNT(*) FROM users WHERE email LIKE %s", ("demo_student_%@grade.local",))[0][0]
demo_admin = q("SELECT id FROM users WHERE email = %s", ("demo@grade.local",))
demo_id = demo_admin[0][0] if demo_admin else None
print(f"待删规模：演示-班级 {n_cls}，学生 {n_stu}，demo学生账户 {n_du}，demo管理员 {demo_id}")

# ── 1) 枚举所有含 class_id / student_id 的表 ──
class_tables = [r[0] for r in q(
    "SELECT DISTINCT TABLE_NAME FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA=%s AND COLUMN_NAME='class_id'", (os.environ["DB_NAME"],))]
student_tables = [r[0] for r in q(
    "SELECT DISTINCT TABLE_NAME FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA=%s AND COLUMN_NAME='student_id'", (os.environ["DB_NAME"],))]
print(f"含 class_id 的表 {len(class_tables)} 张，含 student_id 的表 {len(student_tables)} 张")

# ── 2) 删除（关 FK 检查，先子后父，最后 students/classes）──
cur.execute("SET FOREIGN_KEY_CHECKS=0")
del_cls_sql = "DELETE FROM `%s` WHERE class_id IN (SELECT id FROM classes WHERE name LIKE %%s)"
del_stu_sql = ("DELETE FROM `%s` WHERE student_id IN "
               "(SELECT id FROM students WHERE class_id IN (SELECT id FROM classes WHERE name LIKE %%s))")

for t in class_tables:
    if t == "classes":
        continue
    try:
        cur.execute(del_cls_sql % t, ("演示-%",))
        print(f"  [class_id]  {t:<30} -{affected()}")
    except Exception as e:
        print(f"  [class_id]  {t:<30} SKIP {e}")

for t in student_tables:
    if t == "students":
        continue
    try:
        cur.execute(del_stu_sql % t, ("演示-%",))
        print(f"  [student_id]{t:<30} -{affected()}")
    except Exception as e:
        print(f"  [student_id]{t:<30} SKIP {e}")

cur.execute("DELETE FROM students WHERE class_id IN (SELECT id FROM classes WHERE name LIKE %s)", ("演示-%",))
print(f"  students    -{affected()}")
cur.execute("DELETE FROM classes WHERE name LIKE %s", ("演示-%",))
print(f"  classes     -{affected()}")

# ── 3) demo 学生账户 + 角色绑定 ──
cur.execute("DELETE FROM user_roles WHERE user_id IN (SELECT id FROM users WHERE email LIKE %s)",
            ("demo_student_%@grade.local",))
print(f"  user_roles  -{affected()}")
cur.execute("DELETE FROM users WHERE email LIKE %s", ("demo_student_%@grade.local",))
print(f"  users       -{affected()}")

# ── 4) demo@ 的演示辅助数据 ──
if demo_id:
    for t, col in [
        ("smart_exam_papers", "user_id"),
        ("exam_question_templates", "user_id"),
        ("grading_daily_stats", "user_id"),
        ("health_checks", "recorded_by"),
        ("reward_products", "created_by"),
        ("redemption_records", "operator_id"),
        ("credit_transactions", "operator_id"),
    ]:
        try:
            cur.execute(f"DELETE FROM `{t}` WHERE {col} = %s", (demo_id,))
            print(f"  aux {t:<26} -{affected()}")
        except Exception as e:
            print(f"  aux {t:<26} SKIP {e}")

cur.execute("SET FOREIGN_KEY_CHECKS=1")
conn.commit()

# ── 5) 结果核对 ──
left_cls = q("SELECT COUNT(*) FROM classes WHERE name LIKE %s", ("演示-%",))[0][0]
total_cls = q("SELECT COUNT(*) FROM classes")[0][0]
print(f"\n完成。剩余「演示-」班级 {left_cls}，班级总数 {total_cls}")
cur.close()
conn.close()
