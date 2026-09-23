# -*- coding: utf-8 -*-
"""为指定用户在每个年级创建一个班级，每班约 50 名学生。

用法：python scripts/seed_classes_for_user.py
"""

import sys
from pathlib import Path
from random import choice, randint

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.models.user import gen_uuid  # noqa: E402

# 目标用户
USER_EMAIL = "admin@gradebuddy.com"

# 12 个年级：小学6 + 初中3 + 高中3
GRADE_PLAN = [
    # (school_level, grade, class_name_suffix, student_count)
    ("primary", "小学一年级", "一班", 50),
    ("primary", "小学二年级", "一班", 50),
    ("primary", "小学三年级", "一班", 50),
    ("primary", "小学四年级", "一班", 50),
    ("primary", "小学五年级", "一班", 50),
    ("primary", "小学六年级", "一班", 50),
    ("junior", "初一", "一班", 50),
    ("junior", "初二", "一班", 50),
    ("junior", "初三", "一班", 50),
    ("senior", "高一", "一班", 50),
    ("senior", "高二", "一班", 50),
    ("senior", "高三", "一班", 50),
]

# 随机姓名素材
SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙",
    "胡", "朱", "高", "林", "何", "郭", "马", "罗", "梁", "宋", "郑", "谢",
    "韩", "唐", "冯", "于", "董", "萧", "程", "曹", "袁", "邓", "许", "傅",
    "沈", "曾", "彭", "吕", "苏", "卢", "蒋", "蔡", "贾", "丁", "魏", "薛",
    "叶", "阎", "余", "潘", "杜", "戴", "夏", "钟", "汪", "田", "任", "姜",
]
GIVEN_NAMES = [
    "明轩", "欣怡", "浩然", "雨彤", "宇轩", "静怡", "文博", "雅琪", "俊杰", "诗涵",
    "子涵", "若曦", "子轩", "梓涵", "一鸣", "梦瑶", "天宇", "雪婷", "博文", "思源",
    "致远", "慧敏", "志远", "丽华", "建国", "秀英", "伟强", "美玲", "国栋", "春梅",
    "海峰", "秋菊", "鹏飞", "冬梅", "志强", "桂英", "建华", "瑞芳", "振华", "小燕",
    "子豪", "晓彤", "梓豪", "雨萱", "昊然", "晨曦", "宇涵", "思琪", "铭泽", "语嫣",
    "泽宇", "可欣", "峻熙", "雅静", "星辰", "嘉怡", "睿轩", "思雨", "天佑", "晓萌",
    "子阳", "晓雪", "宗翰", "婉清", "瑞霖", "月华", "浩宇", "家慧", "昊宇", "文静",
    "逸飞", "晓芳", "鸿飞", "玉兰", "云飞", "红梅", "龙飞", "桂兰", "志勇", "春兰",
    "俊峰", "金凤", "海涛", "玉珍", "明辉", "金花", "建平", "秋香", "志国", "秀芳",
    "文博", "雪梅", "浩然", "彩霞", "浩然", "明霞", "家豪", "丽丽", "建国", "婷婷",
]


def random_name():
    return f"{choice(SURNAMES)}{choice(GIVEN_NAMES)}"


def seed():
    with engine.begin() as conn:
        # 查用户
        user = conn.execute(
            text("SELECT id, email, display_name FROM users WHERE email=:e"),
            {"e": USER_EMAIL},
        ).first()
        if not user:
            print(f"错误：找不到用户 {USER_EMAIL}")
            return
        user_id = user[0]
        print(f"用户: {user[2]} ({user[1]})")

        # 删除用户现有的班级和学生（幂等：先清再建）
        old_classes = conn.execute(
            text("SELECT id FROM classes WHERE user_id=:uid"),
            {"uid": user_id},
        ).fetchall()
        for (cid,) in old_classes:
            conn.execute(text("DELETE FROM students WHERE class_id=:cid"), {"cid": cid})
        conn.execute(text("DELETE FROM classes WHERE user_id=:uid"), {"uid": user_id})
        print(f"已清理旧数据（{len(old_classes)} 个班级）")

        total_students = 0
        for school_level, grade, suffix, count in GRADE_PLAN:
            class_id = gen_uuid()
            class_name = f"{grade}{suffix}"
            conn.execute(
                text(
                    "INSERT INTO classes (id, user_id, school_level, grade, name, student_count) "
                    "VALUES (:id, :uid, :sl, :g, :n, :sc)"
                ),
                {"id": class_id, "uid": user_id, "sl": school_level,
                 "g": grade, "n": class_name, "sc": count},
            )
            names_used = set()
            for i in range(1, count + 1):
                name = random_name()
                while name in names_used:
                    name = random_name()
                names_used.add(name)
                sid = gen_uuid()
                num = f"{i:02d}"
                conn.execute(
                    text(
                        "INSERT INTO students (id, class_id, user_id, name, student_number, gender) "
                        "VALUES (:id, :cid, :uid, :n, :sn, :g)"
                    ),
                    {"id": sid, "cid": class_id, "uid": user_id,
                     "n": name, "sn": f"STU{num}", "g": choice(["男", "女"])},
                )
                total_students += 1
            print(f"  {class_name} ({school_level}): {count} 名学生")

    print(f"\n完成！创建 {len(GRADE_PLAN)} 个班级，共 {total_students} 名学生")


if __name__ == "__main__":
    seed()