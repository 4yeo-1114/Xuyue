# -*- coding: utf-8 -*-
"""给 12 个旧班（非「演示-」）补全「班级看板 + 学情分析」全套数据。

复用 demo_seed.py 里已严格对齐前端解析的报表构造函数，只针对已存在的旧班/旧学生
生成以下表（student_wrong_questions 已由 seed_wrong_questions_legacy.py 补齐，本脚本不动它）：
  - student_analysis           → ClassDashboard 三卡（均分/完成率/预警）+ 学情
  - student_score_history      → 学生成绩折线
  - class_analysis_reports     → 班级画像/对比页折线+热力+预警
  - class_review_sessions      → 题目分析页作答分布
  - exams + exam_scores        → 成绩录入/分数结果
  - class_teachers             → 班主任（head=班级 owner）

幂等：先按 class_id 清理上述表，再重建。绝不删 students / classes / 演示-数据。

安全护栏：DB_NAME 必须为 xuyue（独立库），否则拒绝运行，防止误连本地/共享 grade 库。

用法（云端，env 显式覆盖，密码不落盘）：
  DB_HOST=... DB_USER=xuyue DB_PASSWORD=... DB_NAME=xuyue \
  /opt/gradebuddy_venv311/bin/python scripts/seed_old_classes_full.py
"""
import os
import sys
import uuid
import random
from datetime import datetime
from pathlib import Path

# ── 安全护栏：只允许对独立库 xuyue 运行 ──
if os.environ.get("DB_NAME") != "xuyue":
    print(f"[拒绝运行] DB_NAME 必须为 xuyue（独立库），当前为 {os.environ.get('DB_NAME')!r}")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 复用 demo_seed 的常量与函数（会连带 import app.database；env 已在 shell 里指到云端 xuyue）
import demo_seed as ds  # noqa: E402
from sqlalchemy import text  # noqa: E402

OLD_SUBJECTS = ["语文", "数学", "英语", "科学"]


def school_level_of(grade):
    if grade.startswith("小学"):
        return "primary"
    if grade.startswith("初"):
        return "junior"
    if grade.startswith("高"):
        return "senior"
    return "primary"


def run():
    random.seed(20260908)

    t_analysis = ds._table("student_analysis")
    t_history = ds._table("student_score_history")
    t_car = ds._table("class_analysis_reports")
    t_crs = ds._table("class_review_sessions")
    t_exams = ds._table("exams")
    t_exam_scores = ds._table("exam_scores")
    t_teachers = ds._table("class_teachers")

    # ── 读 12 个旧班 + 各自学生（students_dict 结构对齐 demo_seed: name -> {id, number, gender}）──
    with ds.engine.begin() as conn:
        cls_rows = conn.execute(
            text("SELECT id, name, grade, user_id FROM classes WHERE name NOT LIKE :p ORDER BY name"),
            {"p": "演示-%"},
        ).fetchall()

    class_records = []
    for cls_id, cls_name, grade, owner_id in cls_rows:
        with ds.engine.begin() as conn:
            stu = conn.execute(
                text("SELECT id, name, student_number, gender FROM students WHERE class_id = :c ORDER BY name"),
                {"c": cls_id},
            ).fetchall()
        students_dict = {s[1]: {"id": s[0], "number": s[2] or "", "gender": s[3]} for s in stu}
        class_records.append((cls_id, cls_name, grade, owner_id, students_dict))

    print(f"旧班数量: {len(class_records)}")
    for c in class_records:
        print(f"  {c[1]}  {len(c[4])} 学生")

    # ── 幂等清理：只清目标表里这些旧班的旧行，不动 students / classes / 演示- ──
    ids = [c[0] for c in class_records]
    in_clause = ",".join([":c%d" % i for i in range(len(ids))])
    params = {"c%d" % i: v for i, v in enumerate(ids)}
    with ds.engine.begin() as conn:
        for t in ["student_analysis", "student_score_history", "class_analysis_reports",
                  "class_review_sessions", "class_teachers", "exam_scores"]:
            conn.execute(text(f"DELETE FROM {t} WHERE class_id IN ({in_clause})"), params)
        conn.execute(text(f"DELETE FROM exams WHERE class_id IN ({in_clause})"), params)

    now = datetime.now()
    analysis_rows, history_rows = [], []
    car_rows, crs_rows = [], []
    exam_rows, exam_score_rows = [], []
    teacher_rows = []

    for cls_id, cls_name, grade, owner_id, students_dict in class_records:
        school_level = school_level_of(grade)
        name_list = list(students_dict.keys())
        for subject in OLD_SUBJECTS:
            # 每个学生 3 次考试分数（时间渐升）；随机 3%-8% 缺考个别场次
            absent_by_exam = [ds.pick_absent_students(name_list) for _ in range(3)]
            scores = {}
            for name in name_list:
                base = ds._clip(random.gauss(78, 9), 42, 100)
                scores[name] = [
                    None if name in absent_by_exam[idx] else ds.gen_exam_scores(base, idx)
                    for idx in range(3)
                ]
            present_by_idx = [[n for n in name_list if scores[n][idx] is not None] for idx in range(3)]
            n_present_final = len(present_by_idx[2])

            class_avgs, rankings, wrong_map, blank_map = {}, {}, {}, {}
            for idx, exam_name in enumerate(ds.EXAM_NAMES):
                present = present_by_idx[idx]
                s_list = [scores[n][idx] for n in present]
                class_avgs[exam_name] = round(sum(s_list) / len(s_list)) if s_list else 0
                ordered = sorted(present, key=lambda n: (-scores[n][idx], students_dict[n]["number"]))
                rank_rows = []
                prev_score, prev_rank = None, 0
                for r_i, name in enumerate(ordered, start=1):
                    rank = prev_rank if prev_score == scores[name][idx] else r_i
                    prev_score, prev_rank = scores[name][idx], rank
                    rank_rows.append({
                        "student_id": students_dict[name]["id"],
                        "student_name": name,
                        "student_number": students_dict[name]["number"],
                        "score": scores[name][idx],
                        "grade": ds.grade_for_score(scores[name][idx]),
                        "rank": rank,
                    })
                rankings[exam_name] = rank_rows
                for name in present:
                    w, b = ds.wrong_blank_of_score(scores[name][idx])
                    wrong_map[(name, idx)] = w
                    blank_map[(name, idx)] = b

            # student_analysis：每生每科 1 行
            for name in name_list:
                current = scores[name][2]
                if current is None:
                    current = scores[name][1] if scores[name][1] is not None else scores[name][0]
                if current is None:
                    current = 60
                gap = random.randint(3, 8) if current >= 60 else random.randint(6, 12)
                analysis_rows.append({
                    "id": str(uuid.uuid4()),
                    "class_id": cls_id,
                    "student_name": name,
                    "subject": subject,
                    "current_score": current,
                    "target_score": min(100, current + gap),
                })

            # student_score_history：每生每科 3 行（缺考场次无记录）
            for idx, exam_name in enumerate(ds.EXAM_NAMES):
                for name in name_list:
                    if scores[name][idx] is None:
                        continue
                    history_rows.append({
                        "id": str(uuid.uuid4()),
                        "class_id": cls_id,
                        "student_name": name,
                        "subject": subject,
                        "exam_name": exam_name,
                        "score": scores[name][idx],
                        "class_avg": class_avgs[exam_name],
                        "created_at": datetime(2026, 3 if idx == 0 else 5 if idx == 1 else 7, 15 + idx * 5),
                    })

            # exams + exam_scores（每班每科 3 场，成绩与 history 一致）
            for idx, exam_name in enumerate(ds.EXAM_NAMES):
                eid = str(uuid.uuid4())
                exam_rows.append({
                    "id": eid,
                    "user_id": owner_id,
                    "class_id": cls_id,
                    "subject": subject,
                    "title": f"{cls_name}-{subject}-{exam_name}",
                    "total_score": 100,
                    "exam_date": ds.EXAM_DATES[exam_name],
                })
                rank_by_name = {r["student_name"]: r["rank"] for r in rankings[exam_name]}
                for name in name_list:
                    if scores[name][idx] is None:
                        continue
                    exam_score_rows.append({
                        "id": str(uuid.uuid4()),
                        "user_id": owner_id,
                        "exam_id": eid,
                        "student_id": students_dict[name]["id"],
                        "score": float(scores[name][idx]),
                        "class_avg": float(class_avgs[exam_name]),
                        "class_rank": rank_by_name[name],
                        "class_id": cls_id,
                        "school_id": None,
                    })

            # class_analysis_reports（回填正确的 school_level：初中/高中不是 primary）
            source_summary, analysis = ds.build_class_analysis_report(
                cls_id, cls_name, grade, subject, students_dict, scores, class_avgs, rankings, wrong_map, blank_map,
            )
            source_summary["class"]["school_level"] = school_level
            car_rows.append({
                "id": str(uuid.uuid4()),
                "report_uuid": str(uuid.uuid4()),
                "class_id": cls_id,
                "class_name": cls_name,
                "subject": subject,
                "exam_names_json": ds._j(ds.EXAM_NAMES),
                "imported_folder_names_json": ds._j([f"cls_{cls_id}__{e}" for e in ds.EXAM_NAMES]),
                "source_summary_json": ds._j(source_summary),
                "analysis_json": ds._j(analysis),
                "generated_at": now,
            })

            # class_review_sessions
            crs_source, crs_pre = ds.build_class_review_session(
                cls_id, subject, class_avgs[ds.EXAM_NAMES[-1]], n_present_final,
            )
            crs_rows.append({
                "id": str(uuid.uuid4()),
                "class_id": cls_id,
                "subject": subject,
                "title": f"{subject}课堂讲评",
                "exam_names_json": ds._j(ds.EXAM_NAMES),
                "imported_folder_names_json": ds._j([f"cls_{cls_id}__{e}" for e in ds.EXAM_NAMES]),
                "source_summary_json": ds._j(crs_source),
                "pre_class_json": ds._j(crs_pre),
                "generated_at": now,
            })

            # class_teachers：每班 1 班主任 = owner（仅首个学科时插入一次）
            if subject == OLD_SUBJECTS[0]:
                teacher_rows.append({
                    "id": str(uuid.uuid4()),
                    "class_id": cls_id,
                    "user_id": owner_id,
                    "role": "head",
                    "subject": None,
                })

    with ds.engine.begin() as conn:
        ds._bulk(conn, t_analysis, analysis_rows)
        ds._bulk(conn, t_history, history_rows)
        ds._bulk(conn, t_car, car_rows)
        ds._bulk(conn, t_crs, crs_rows)
        ds._bulk(conn, t_exams, exam_rows)
        ds._bulk(conn, t_exam_scores, exam_score_rows)
        ds._bulk(conn, t_teachers, teacher_rows)

    print("\nINSERTED:")
    print(f"  student_analysis       {len(analysis_rows)}")
    print(f"  student_score_history  {len(history_rows)}")
    print(f"  class_analysis_reports {len(car_rows)}")
    print(f"  class_review_sessions  {len(crs_rows)}")
    print(f"  exams                  {len(exam_rows)}")
    print(f"  exam_scores            {len(exam_score_rows)}")
    print(f"  class_teachers         {len(teacher_rows)}")
    total = (len(analysis_rows) + len(history_rows) + len(car_rows) + len(crs_rows)
             + len(exam_rows) + len(exam_score_rows) + len(teacher_rows))
    print(f"  TOTAL                  {total}")


if __name__ == "__main__":
    run()
