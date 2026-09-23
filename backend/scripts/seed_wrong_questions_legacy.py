# -*- coding: utf-8 -*-
"""给「非演示-」旧班级（12 个班 / 600 学生）补错题库。

幂等：该生该科已有 student_wrong_questions 则跳过。
用法（云端）：DB_HOST=... DB_USER=xuyue ... /opt/gradebuddy_venv311/bin/python scripts/seed_wrong_questions_legacy.py
"""
import os
import random
import sys
import uuid

import pymysql

SUBJECTS = ["语文", "数学", "英语", "科学"]
SUBJECT_QUESTIONS = {
    "语文": ["一、看拼音写词语", "二、选词填空", "三、阅读理解", "四、古诗文默写", "五、作文", "六、修辞手法判断"],
    "数学": ["一、口算题", "二、竖式计算", "三、应用题", "四、单位换算填空", "五、图形几何选择题", "六、统计与概率"],
    "英语": ["一、听音选词", "二、单项选择", "三、阅读理解", "四、连词成句", "五、书面表达", "六、词汇拼写"],
    "科学": ["一、选择题-植物", "二、判断题", "三、实验题-水的三态", "四、填空题-动物", "五、简答题-天气", "六、观察记录题"],
}

random.seed(20260908)

conn = pymysql.connect(
    host=os.environ["DB_HOST"],
    port=int(os.environ.get("DB_PORT", "3306")),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"],
    charset="utf8mb4",
)
cur = conn.cursor()

cur.execute("SELECT id, name FROM classes WHERE name NOT LIKE %s", ("演示-%",))
classes = cur.fetchall()

total = 0
for cls_id, cls_name in classes:
    cur.execute("SELECT id, name FROM students WHERE class_id = %s", (cls_id,))
    students = cur.fetchall()
    added = 0
    for _sid, sname in students:
        for subject in SUBJECTS:
            cur.execute(
                "SELECT COUNT(*) FROM student_wrong_questions WHERE class_id=%s AND student_name=%s AND subject=%s",
                (cls_id, sname, subject),
            )
            if cur.fetchone()[0] > 0:
                continue
            n = random.randint(2, 5)
            for t in random.sample(SUBJECT_QUESTIONS[subject], n):
                cur.execute(
                    "INSERT INTO student_wrong_questions "
                    "(id, class_id, student_name, subject, exam_name, question_title, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'open')",
                    (str(uuid.uuid4()), cls_id, sname, subject, "月考", t),
                )
                added += 1
    conn.commit()
    total += added
    print(f"{cls_name}: {len(students)} 学生, 新增错题 {added} 条")

print("TOTAL_INSERTED", total)
cur.close()
conn.close()
