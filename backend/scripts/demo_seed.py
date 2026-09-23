# -*- coding: utf-8 -*-
"""演示数据造数脚本（叙阅/叙阅后端）。

在本地演示库（.env 配置：127.0.0.1:13307 root/root_pw_2026 grade）生成一套完整、
合理、可重复运行的演示数据，覆盖全部图表链路：

  - 班级画像页/对比页折线+热力+预警  ← class_analysis_reports（JSON 列）
  - 题目分析页作答分布柱状图         ← class_review_sessions（JSON 列）
  - ClassDashboard 三卡（均分/完成率/预警）← student_analysis
  - 学生成绩折线                     ← student_score_history
  - 成绩录入/分数结果                ← exams + exam_scores
  - 智能组卷测试试卷/学科题型模板    ← smart_exam_papers + exam_question_templates

数据规模：
  - 1 所「演示小学」（schools 锚表，schoolName 来源）+ 全部演示用户经 user_roles 绑定该校
    （demo 管理员 role=school_admin，学生账户 role=student），使学校驾驶舱用户数 KPI 不为 1
  - 小学 6 个年级 × 每年级 4 班 = 24 班，每班约 42-58 学生（高斯随机，不再固定 50）
  - 全部班级 school_id 归属「演示小学」（school scope 生效但单校演示行为不变）
  - 每班 4 科（语文/数学/英语/科学）× 3 次考试（月考/期中考试/期末考试）
  - 每次考试随机 3%-8% 学生缺考（该生该场次无成绩/历史记录），但每班每科仍有充足样本
  - 班级名统一前缀 `演示-`，作为幂等清理标识；绝不触碰非演示数据
  - 可重复运行：脚本内部连跑两遍，验证幂等（两次各表行数一致）

用法：python scripts/demo_seed.py
"""
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# ── 环境变量必须在 import app.* 之前设置 ──
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "13307")
os.environ.setdefault("DB_USER", "root")
os.environ.setdefault("DB_PASSWORD", "root_pw_2026")
os.environ.setdefault("DB_NAME", "grade")
os.environ.setdefault("JWT_SECRET_KEY", "demo_seed_local_dev_secret_key_2026_08000")
os.environ.setdefault("AUTO_DDL", "false")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import MetaData, Table, text  # noqa: E402
from app.database import engine  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

# ═══════════════════════════════════ 常量 ═══════════════════════════════════
GRADES = ["小学一年级", "小学二年级", "小学三年级", "小学四年级", "小学五年级", "小学六年级"]
CLASSES_PER_GRADE = 4
SUBJECTS = ["语文", "数学", "英语", "科学"]
EXAM_NAMES = ["月考", "期中考试", "期末考试"]
EXAM_DATES = {
    "月考": date(2026, 3, 20),
    "期中考试": date(2026, 5, 15),
    "期末考试": date(2026, 7, 5),
}
STUDENTS_PER_CLASS_MIN = 42
STUDENTS_PER_CLASS_MAX = 58
ABSENT_RATE_MIN = 0.03
ABSENT_RATE_MAX = 0.08
MIN_PRESENT_PER_EXAM = 30
SCHOOL_LEVEL = "primary"
DEMO_PREFIX = "演示-"
DEMO_ADMIN_EMAIL = "demo@grade.local"
DEMO_USER_DOMAIN = "@grade.local"
DEMO_SCHOOL_NAME = "演示小学"  # 学校版「预警中心」的 schoolName 来源（D10）

# 分层分级演示账户（教师-班主任-校领导三级，密码均 demo123，沿用现有角色体系）
DEMO_TEACHER_EMAIL = "teacher@grade.local"          # 任课教师：class_teachers role=teacher 挂 1 班
DEMO_HEADTEACHER_EMAIL = "headteacher@grade.local"  # 班主任：class_teachers role=head 挂 1 班 + user_roles role=teacher
DEMO_PRINCIPAL_EMAIL = "principal@grade.local"      # 校级管理者：user_roles role=school_admin + job_title=校长
DEMO_ROLE_TEACHER = "任课教师"
DEMO_ROLE_HEADTEACHER = "班主任"
DEMO_ROLE_PRINCIPAL = "校级管理者"
DEMO_HEADTEACHER_CLASS_NAME = "演示-小学三年级1班"  # 班主任接管班级（demo@ 让出该班 head）

# 问题班科（D11）：把指定班级某科成绩整体压到低分段，让学校版预警中心
# （/school/warnings，期末均分<60→red、<70→yellow）自然出现预警。
# 双条件精确匹配（班级名 + 科目），宁可少命中不可误伤其他班科。
PROBLEM_CLASS_SPEC = {"班级名": "演示-小学四年级1班", "subject": "数学"}
PROBLEM_CLASS_BASE_MEAN = 50   # 低分档 base 均值
PROBLEM_CLASS_BASE_SIGMA = 7   # 低分档 base 标准差
PROBLEM_CLASS_BASE_LO = 25     # 低分档 base 下界（保证极端值不穿帮）
PROBLEM_CLASS_BASE_HI = 72     # 低分档 base 上界（期末 +delta4-8 后仍远低于及格线）

# 常见姓氏 + 名字（真实中文名，非拼音）
SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "黄", "赵", "吴", "周",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "林", "罗", "郑",
    "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹", "彭",
    "曾", "萧", "田", "董", "潘", "袁", "蒋", "蔡", "余", "杜",
    "叶", "程", "苏", "魏", "吕", "丁", "任", "沈", "姚", "卢",
]
GIVEN_M = [
    "梓涵", "子轩", "浩然", "明轩", "宇轩", "浩宇", "俊杰", "博文", "文昊", "鹏飞",
    "志强", "伟民", "立新", "家豪", "子豪", "睿", "文轩", "嘉懿", "懿轩", "子墨",
    "嘉禾", "子骞", "瑞霖", "浩宸", "奕辰", "一鸣", "承泽", "文博", "昊然", "辰逸",
]
GIVEN_F = [
    "雨桐", "欣怡", "梓萱", "梦瑶", "思彤", "若曦", "芷晴", "语嫣", "欣妍", "雨萱",
    "诗涵", "静怡", "雪琪", "婉婷", "怡然", "悦宁", "清雅", "慧敏", "晓婷", "佳琪",
    "思涵", "诗琪", "语桐", "欣悦", "可馨", "雅静", "舒雅", "梦洁", "芷若", "语诺",
]

# 各科常见知识点（用于班级画像热力图/薄弱点）
SUBJECT_KNOWLEDGE = {
    "语文": ["拼音字词", "古诗文默写", "阅读理解", "语言表达", "标点符号", "作文立意", "修辞手法"],
    "数学": ["数的运算", "应用题", "几何图形", "单位换算", "分数小数", "统计与概率", "基础概念"],
    "英语": ["词汇拼写", "语法时态", "阅读理解", "听力理解", "书面表达", "情景交际", "句型转换"],
    "科学": ["科学探究", "生命科学", "物质科学", "地球与宇宙", "实验设计", "现象解释", "科学概念"],
}

# 各科题目池（用于题目分析页高/强频错题 + 错题本）
SUBJECT_QUESTIONS = {
    "语文": [
        {"key": "yuwen_1", "title": "一、看拼音写词语", "knowledge_point": "拼音字词"},
        {"key": "yuwen_2", "title": "二、选词填空", "knowledge_point": "词语辨析"},
        {"key": "yuwen_3", "title": "三、阅读理解", "knowledge_point": "阅读理解"},
        {"key": "yuwen_4", "title": "四、古诗文默写", "knowledge_point": "古诗文"},
        {"key": "yuwen_5", "title": "五、作文", "knowledge_point": "书面表达"},
        {"key": "yuwen_6", "title": "六、修辞手法判断", "knowledge_point": "修辞手法"},
    ],
    "数学": [
        {"key": "math_1", "title": "一、口算题", "knowledge_point": "数的运算"},
        {"key": "math_2", "title": "二、竖式计算", "knowledge_point": "数的运算"},
        {"key": "math_3", "title": "三、应用题", "knowledge_point": "应用题"},
        {"key": "math_4", "title": "四、单位换算填空", "knowledge_point": "单位换算"},
        {"key": "math_5", "title": "五、图形几何选择题", "knowledge_point": "几何图形"},
        {"key": "math_6", "title": "六、统计与概率", "knowledge_point": "统计与概率"},
    ],
    "英语": [
        {"key": "eng_1", "title": "一、听音选词", "knowledge_point": "听力理解"},
        {"key": "eng_2", "title": "二、单项选择", "knowledge_point": "语法时态"},
        {"key": "eng_3", "title": "三、阅读理解", "knowledge_point": "阅读理解"},
        {"key": "eng_4", "title": "四、连词成句", "knowledge_point": "句型转换"},
        {"key": "eng_5", "title": "五、书面表达", "knowledge_point": "书面表达"},
        {"key": "eng_6", "title": "六、词汇拼写", "knowledge_point": "词汇拼写"},
    ],
    "科学": [
        {"key": "sci_1", "title": "一、选择题-植物", "knowledge_point": "生命科学"},
        {"key": "sci_2", "title": "二、判断题", "knowledge_point": "科学概念"},
        {"key": "sci_3", "title": "三、实验题-水的三态", "knowledge_point": "实验设计"},
        {"key": "sci_4", "title": "四、填空题-动物", "knowledge_point": "生命科学"},
        {"key": "sci_5", "title": "五、简答题-天气", "knowledge_point": "地球与宇宙"},
        {"key": "sci_6", "title": "六、观察记录题", "knowledge_point": "科学探究"},
    ],
}

# 六维能力维度名（对齐后端 app/routers/student_analysis.py 的 ai-diagnosis 模板）
SUBJECT_CAPABILITY_DIMS = {
    "语文": ["作文结构", "阅读理解", "基础知识", "古诗文", "语言表达", "创新思维"],
    "数学": ["计算能力", "逻辑推理", "空间想象", "数据分析", "建模应用", "创新思维"],
    "英语": ["听力理解", "口语表达", "阅读理解", "写作能力", "词汇语法", "翻译能力"],
    "科学": ["基础掌握", "应用能力", "综合分析", "创新思维", "逻辑推理", "知识广度"],
}

TEACHING_ACTIONS_POOL = [
    "针对班级薄弱知识点，安排每日 10 分钟专项练习，滚动复习易错题型",
    "将高频错题整理成错题集，每周开展一次错题重做与变式训练",
    "对成绩靠后学生进行一对一辅导，重点关注基础概念与解题规范",
    "课堂增加互动提问环节，提高学生参与度，当堂检测掌握情况",
    "布置分层作业，基础层巩固概念，提升层强化应用题综合训练",
    "加强与家长沟通，推送每日学习任务，形成家校共育合力",
    "组织小组合作学习，以优带弱，营造互助学习氛围",
    "每两周进行一次章节小测，及时检验阶段性学习效果",
]


def grade_for_score(score):
    """分数 → 等级（与后端 grade_scores.grade_for_score 一致）。"""
    if score is None:
        return None
    try:
        v = float(score)
    except (TypeError, ValueError):
        return None
    if v >= 85:
        return "excellent"
    if v >= 70:
        return "good"
    if v >= 60:
        return "pass"
    return "needs_work"


def _clip(v, lo, hi):
    return max(lo, min(hi, int(round(v))))


def class_student_count():
    """班级人数：以 50 为中心的高斯随机，裁剪到 42-58，避免各班人数雷同。"""
    return _clip(random.gauss(50, 4), STUDENTS_PER_CLASS_MIN, STUDENTS_PER_CLASS_MAX)


def pick_absent_students(name_list):
    """随机选 3%-8% 学生缺考某一场次，保证该场至少保留 MIN_PRESENT_PER_EXAM 人。"""
    n = len(name_list)
    max_absent = max(0, n - MIN_PRESENT_PER_EXAM)
    if max_absent <= 0:
        return set()
    n_absent = min(int(round(n * random.uniform(ABSENT_RATE_MIN, ABSENT_RATE_MAX))), max_absent)
    if n_absent <= 0:
        return set()
    return set(random.sample(name_list, n_absent))


def _birthday(grade_idx):
    """按年级生成出生日期：出生年份集中在年级对应学段，月份向 8-10 月（入学截止）倾斜。"""
    base_year = 2019 - grade_idx  # 一年级≈2019 年出生，逐年级前推
    year = base_year + random.randint(-1, 1)
    month = random.choices(range(1, 13), weights=[1, 1, 1, 1, 1, 1, 1, 3, 3, 2, 1, 1])[0]
    day = random.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


# ═══════════════════════════════ 数据生成 ═══════════════════════════════

def build_class_names():
    """返回 24 个班级名：演示-小学一年级1班 ... 演示-小学六年级4班。"""
    names = []
    for g in GRADES:
        for i in range(1, CLASSES_PER_GRADE + 1):
            names.append(f"{DEMO_PREFIX}{g}{i}班")
    return names


def build_student_names(class_idx, n_students, boy_ratio):
    """为某班级生成 n_students 个唯一姓名 + 性别（男女性别比约 45%-55% 随机）。"""
    rng = random.Random(1000 + class_idx)
    boy_pool = [f"{s}{g}" for s in SURNAMES for g in GIVEN_M]
    girl_pool = [f"{s}{g}" for s in SURNAMES for g in GIVEN_F]
    rng.shuffle(boy_pool)
    rng.shuffle(girl_pool)
    n_boy = max(0, min(n_students, int(round(n_students * boy_ratio))))
    n_girl = n_students - n_boy
    items = [(name, "男") for name in boy_pool[:n_boy]] + [
        (name, "女") for name in girl_pool[:n_girl]
    ]
    rng.shuffle(items)
    return items


def gen_exam_scores(base, exam_idx):
    """根据基准分生成 3 次考试分数，时间顺序渐升。

    高分段收敛：base≥95 的期中 delta 收窄到 [0,1] 且结果封顶 99、base≥92 的期末
    delta 收窄到 [0,2]，避免 base≥92 的学生被批量截断成 100 分。收敛后满分只出现
    在期末且 base≥98 的学生（base 98/99 + delta 0-2 → 100），期中/月考不再有满分，
    每班每科 100 分收敛到 0-1 个。
    """
    if exam_idx == 0:
        delta = -random.randint(3, 6)
    elif exam_idx == 1:
        if base >= 95:
            delta = random.randint(0, 1)
        else:
            delta = random.randint(0, 3)
    else:
        if base >= 92:
            delta = random.randint(0, 2)
        else:
            delta = random.randint(4, 8)
    score = _clip(base + delta, 35, 100)
    if exam_idx == 1 and base >= 95:
        score = min(score, 99)  # 期中高分段封顶 99：base 上界放宽到 100 后，杜绝期中满分
    return score


def wrong_blank_of_score(score):
    """由分数派生该生该次考试的错题数/空白数（低分对应更多错题）。"""
    diff = 100 - score
    if score >= 60:
        wrong = round(diff / 10.0)
    else:
        wrong = round(diff / 7.0)
    wrong = min(wrong, 9)
    blank = 1 if score < 50 and random.random() < 0.5 else 0
    return wrong, blank


# ═══════════════════════════════ 报表 JSON 构造 ═══════════════════════════════

def build_class_analysis_report(cls_id, cls_name, grade, subject, students, scores, class_avgs, rankings, wrong_map, blank_map):
    """构造 class_analysis_reports 的 source_summary + analysis 两段 JSON（严格对齐前端解析）。"""
    exam_names = EXAM_NAMES
    class_size = len(students)
    # 每场考试的有效学生（未缺考）；scores 中缺考场次为 None
    present_by_idx = [
        [n for n in students if scores[n][idx] is not None] for idx in range(3)
    ]

    # ---- source_summary.exam_summaries ----
    exam_summaries = []
    for idx, exam_name in enumerate(exam_names):
        present = present_by_idx[idx]
        scores_list = [scores[name][idx] for name in present]
        n_present = len(scores_list)
        avg = round(sum(scores_list) / n_present, 1) if n_present else None
        median = round(sorted(scores_list)[n_present // 2], 1) if n_present else None
        highest = max(scores_list) if n_present else None
        lowest = min(scores_list) if n_present else None
        answer_area_count = n_present * 10
        wrong_count = sum(wrong_map[(name, idx)] for name in present)
        blank_count = sum(blank_map[(name, idx)] for name in present)
        wrong_rate = round((wrong_count + blank_count) / answer_area_count * 100, 1) if answer_area_count else None
        exam_summaries.append({
            "exam_name": exam_name,
            "folder_name": f"cls_{cls_id}__{exam_name}",
            "order": idx + 1,
            "participant_count": n_present,
            "record_paper_count": n_present,
            "average_score": avg,
            "median_score": median,
            "highest_score": highest,
            "lowest_score": lowest,
            "answer_area_count": answer_area_count,
            "wrong_count": wrong_count,
            "blank_count": blank_count,
            "wrong_rate": wrong_rate,
            "rankings": rankings[exam_name],
        })

    latest_avg = exam_summaries[-1]["average_score"]
    first_avg = exam_summaries[0]["average_score"]
    total_papers = sum(len(p) for p in present_by_idx)
    overall_metrics = {
        "exam_count": 3,
        "latest_average_score": latest_avg,
        "average_score_change": round(latest_avg - first_avg, 1),
        "record_paper_count": total_papers,
        "image_count": total_papers,
        "image_paper_coverage_rate": 100.0,
    }
    source_summary = {
        "class": {
            "class_id": cls_id,
            "class_name": cls_name,
            "school_level": SCHOOL_LEVEL,
            "grade": grade,
            "student_count": class_size,
        },
        "overall_metrics": overall_metrics,
        "exam_summaries": exam_summaries,
        "ignored_paper_count": 0,
        "vision_batch_count": 1,
        "model": "qwen3.7-plus",
    }

    # ---- analysis.overall_level ----
    level = ("优秀" if latest_avg >= 85 else "良好" if latest_avg >= 75 else "中等" if latest_avg >= 65 else "需提升")
    overall_level = {
        "level": level,
        "summary": (
            f"本班{grade}{subject}本学期共完成 3 次考试，班级平均分从 {first_avg} 分"
            f"提升至 {latest_avg} 分，整体呈上升趋势。学生在基础知识掌握和答题规范方面"
            f"有进步，但部分知识点仍存在薄弱环节，需在后续教学中重点加强。"
        ),
        "trend": "班级平均分持续上升，优秀学生保持稳定，中后段学生进步明显。",
        "score_interpretation": (
            f"以最近一次考试计，班级均分 {latest_avg} 分，最高 {exam_summaries[-1]['highest_score']} 分，"
            f"最低 {exam_summaries[-1]['lowest_score']} 分。超过 60 分的学生占比约 "
            f"{round(sum(1 for s in present_by_idx[2] if scores[s][2] >= 60) / max(1, len(present_by_idx[2])) * 100)}%。"
        ),
        "strengths": _pick_strengths(subject),
        "data_notes": [],
    }

    # ---- analysis.knowledge_heatmap（values 严格覆盖 3 次考试，顺序一致）----
    kps = SUBJECT_KNOWLEDGE[subject]
    random.shuffle(kps)
    knowledge_heatmap = []
    for kp in kps[: random.randint(5, 6)]:
        values = []
        for idx, exam_name in enumerate(exam_names):
            base_risk = random.randint(28, 72)
            risk = _clip(base_risk - idx * random.randint(0, 6), 12, 92)
            values.append({
                "exam_name": exam_name,
                "risk_score": risk,
                "evidence_count": random.randint(8, 30),
            })
        knowledge_heatmap.append({
            "knowledge_point": kp,
            "values": values,
            "summary": f"{kp}为班级{subject}学习中较受关注的能力点，错误率随练习有所下降。",
        })

    # ---- analysis.weak_points ----
    weak_points = []

    def _last_score(s):
        for i in (2, 1, 0):
            if scores[s][i] is not None:
                return scores[s][i]
        return None

    low_scorers = [s for s in students if _last_score(s) is not None and _last_score(s) < 75]
    low_scorers_sorted = sorted(low_scorers, key=_last_score)
    affected_names = [s for s in low_scorers_sorted[:8]]
    for kp in sorted(knowledge_heatmap, key=lambda r: r["values"][-1]["risk_score"], reverse=True)[:3]:
        risk = kp["values"][-1]["risk_score"]
        severity = "high" if risk >= 60 else "medium" if risk >= 30 else "low"
        weak_points.append({
            "knowledge_point": kp["knowledge_point"],
            "severity": severity,
            "affected_student_count": max(1, len(low_scorers)),
            "affected_students": affected_names,
            "evidence_exam_names": list(exam_names),
            "evidence": f"{kp['knowledge_point']}相关题目三次考试平均错误率约 {risk}%，影响学生 {len(low_scorers)} 人。",
            "teaching_suggestion": f"建议围绕{kp['knowledge_point']}设计专项练习与变式训练，利用错题集滚动巩固。",
        })

    # ---- analysis.student_warnings（3-8 人，姓名/分数/警示原因/涉及考试齐全）----
    student_warnings = []

    def _avg_present(s):
        vals = [v for v in scores[s] if v is not None]
        return sum(vals) / len(vals) if vals else 0

    students_sorted_by_avg = sorted(students, key=_avg_present)
    warned = students_sorted_by_avg[: random.randint(3, 8)]
    for s in warned:
        w_exams = []
        total_wrong = 0
        for idx, exam_name in enumerate(exam_names):
            if scores[s][idx] is None:
                continue  # 缺考场次不计入预警
            wc = wrong_map[(s, idx)]
            bc = blank_map[(s, idx)]
            if wc + bc >= 4:
                class_wrong = [wrong_map[(x, idx)] + blank_map[(x, idx)] for x in present_by_idx[idx]]
                class_avg_wrong = round(sum(class_wrong) / len(class_wrong), 1)
                ordered = sorted(class_wrong)
                threshold = max(2, ordered[int(len(ordered) * 0.75)])
                rank_row = next((r for r in rankings[exam_name] if r["student_name"] == s), None)
                total_wrong += wc + bc
                w_exams.append({
                    "exam_name": exam_name,
                    "wrong_count": wc + bc,
                    "class_average_wrong_count": class_avg_wrong,
                    "warning_threshold": threshold,
                    "score": scores[s][idx],
                    "rank": rank_row["rank"] if rank_row else None,
                    "top_wrong_titles": [q["title"] for q in random.sample(SUBJECT_QUESTIONS[subject], min(4, len(SUBJECT_QUESTIONS[subject])))],
                })
        if not w_exams:
            continue
        risk_level = "high" if len(w_exams) >= 2 else "medium"
        exam_bits = "；".join(f"{x['exam_name']}错题{x['wrong_count']}道" for x in w_exams)
        student_warnings.append({
            "student_id": _student_id(students, s),
            "student_name": s,
            "student_number": _student_number(students, s),
            "risk_level": risk_level,
            "reason": f"{s}本学期{subject}成绩偏低，{exam_bits}，基础知识掌握不牢固，需重点关注。",
            "suggestion": "建议优先订正高频错题并重做同类题，加强基础概念复习，家长配合每日专项训练。",
            "warning_exams": w_exams,
            "total_wrong_count": total_wrong,
        })
        if len(student_warnings) >= 8:
            break

    # ---- analysis.capability_dimensions（六维能力雷达图数据源，纯新增字段）----
    dim_names = SUBJECT_CAPABILITY_DIMS.get(subject, SUBJECT_CAPABILITY_DIMS["科学"])
    cap_final_avg = class_avgs[exam_names[-1]]  # 期末班级均分（0-100 整数），作为能力水平基准
    dims = []
    for dname in dim_names:
        base_dim = random.randint(55, 90)  # 各维度独立随机，体现强弱势
        cap_score = _clip(base_dim + (cap_final_avg - 70), 40, 96)
        cap_class_avg = random.randint(62, 78)  # 固定合理基准，供前端画「本班 vs 班级平均」双序列雷达
        dims.append({"name": dname, "score": cap_score, "classAvg": cap_class_avg})
    strongest = max(dims, key=lambda d: d["score"])
    weakest = min(dims, key=lambda d: d["score"])
    cap_level = ("优秀" if cap_final_avg >= 85 else "良好" if cap_final_avg >= 75 else "中等" if cap_final_avg >= 65 else "需提升")
    cap_summary = (
        f"本班{subject}六维能力整体水平{cap_level}，「{strongest['name']}」维度表现最突出"
        f"（得分 {strongest['score']} 分），「{weakest['name']}」维度相对薄弱"
        f"（得分 {weakest['score']} 分）。建议在巩固{strongest['name']}优势的同时，"
        f"围绕{weakest['name']}设计专项训练与变式练习，均衡提升综合能力。"
    )
    capability_dimensions = {
        "dims": dims,
        "level": cap_level,
        "summary": cap_summary,
    }

    analysis = {
        "overall_level": overall_level,
        "knowledge_heatmap": knowledge_heatmap,
        "weak_points": weak_points,
        "student_warnings": student_warnings,
        "teaching_actions": random.sample(TEACHING_ACTIONS_POOL, random.randint(4, 6)),
        "capability_dimensions": capability_dimensions,
    }

    return source_summary, analysis


def _pick_strengths(subject):
    pools = {
        "语文": ["基础字词掌握扎实", "朗读与背诵习惯良好", "书写工整规范", "阅读理解进步明显"],
        "数学": ["口算能力较强", "计算规范、卷面整洁", "应用题审题较准", "几何图形识别准确"],
        "英语": ["语音语调较好", "单词记忆较牢", "情景对话参与积极", "书写规范"],
        "科学": ["观察记录认真", "实验操作规范", "对自然现象兴趣浓厚", "科学概念理解较好"],
    }
    return random.sample(pools[subject], 3)


def _student_id(students, name):
    return students[name]["id"]


def _student_number(students, name):
    return students[name]["number"]


def build_class_review_session(cls_id, subject, source_summary_class_avg, class_size):
    """构造 class_review_sessions 的 source_summary + pre_class 两段 JSON（严格对齐前端解析）。"""
    exam_names = EXAM_NAMES
    questions = SUBJECT_QUESTIONS[subject]
    random.shuffle(questions)

    high_risk = []
    for q in questions[: random.randint(3, 4)]:
        wrong_rate = random.uniform(0.25, 0.55)
        blank_rate = random.uniform(0.02, 0.10)
        wrong = int(round(class_size * wrong_rate))
        blank = int(round(class_size * blank_rate))
        correct = max(0, class_size - wrong - blank)
        reasons = _build_reasons(wrong + blank)
        high_risk.append({
            "question_key": q["key"],
            "display_title": q["title"],
            "knowledge_point": q["knowledge_point"],
            "correct_count": correct,
            "wrong_count": wrong,
            "blank_count": blank,
            "ungraded_count": 0,
            "reasons": reasons,
        })

    strong = []
    for q in questions[len(high_risk): len(high_risk) + random.randint(2, 3)]:
        wrong = random.randint(1, 4)
        blank = 0
        correct = max(0, class_size - wrong - blank)
        reasons = _build_reasons(wrong)
        strong.append({
            "question_key": q["key"],
            "display_title": q["title"],
            "knowledge_point": q["knowledge_point"],
            "correct_count": correct,
            "wrong_count": wrong,
            "blank_count": blank,
            "ungraded_count": 0,
            "reasons": reasons,
        })

    all_q = high_risk + strong
    total_answer = sum(q["correct_count"] + q["wrong_count"] + q["blank_count"] for q in all_q)
    total_correct = sum(q["correct_count"] for q in all_q)
    total_wrong = sum(q["wrong_count"] for q in all_q)
    total_blank = sum(q["blank_count"] for q in all_q)

    source_summary = {
        "valid_student_count": class_size,
        "class_avg_score": round(source_summary_class_avg, 1),
        "answer_area_count": total_answer,
        "correct_count": total_correct,
        "wrong_count": total_wrong,
        "blank_count": total_blank,
        "high_risk_questions": high_risk,
        "strong_questions": strong,
    }

    # ---- pre_class ----
    overview = {
        "summary": f"本班{subject}共完成 3 次考试，班级整体均分 {round(source_summary_class_avg, 1)} 分。高频错题集中在基础概念与审题能力，讲评重点放在典型错因与变式训练。",
        "weak_points": [q["knowledge_point"] for q in high_risk[:3]],
        "strengths": [q["knowledge_point"] for q in strong[:2]],
        "data_basis": [
            f"全班共 {class_size} 名学生参与",
            f"高频错题平均正确率约 {round(100 - (total_wrong + total_blank) / max(1, total_answer) * 100, 1)}%",
        ],
    }

    review_plan = {
        "duration": "40分钟",
        "objectives": [
            f"梳理{subject}高频错题对应的核心知识点，厘清概念混淆",
            "针对典型错因进行当堂变式训练，当堂订正",
            "掌握正确的审题与答题规范，减少非知识性失分",
            "通过小组互评提升学生反思与表达能力",
        ],
        "key_points": [f"{q['knowledge_point']}掌握不牢" for q in high_risk[: min(5, len(high_risk))]],
        "teaching_flow": [
            {"step": "导入回顾", "minutes": 5, "teacher_action": "展示班级成绩分布与高频错题", "student_action": "回顾自己的错题，明确讲评目标"},
            {"step": "高频错题讲评", "minutes": 15, "teacher_action": "逐题分析错因，讲解正确思路", "student_action": "记录错因，重做错题"},
            {"step": "变式训练", "minutes": 12, "teacher_action": "布置同类变式题，巡视指导", "student_action": "独立完成变式题并互批"},
            {"step": "总结反馈", "minutes": 8, "teacher_action": "归纳易错点，布置课后巩固练习", "student_action": "整理错题本，提交巩固作业"},
        ],
        "blackboard_design": [
            "高频错题统计（错误率/错因）",
            "典型错因对比（正确 vs 错误示例）",
            "核心知识点框架图",
            "课后巩固任务清单",
        ],
        "interaction_questions": [
            f"这道{high_risk[0]['display_title']}的常见错因是什么？",
            "还有哪些同类型题目容易出现类似错误？",
            "你能举出一个变式例子吗？",
            "做这道题时最需要注意哪一步？",
        ],
    }

    question_cards = []
    for q in all_q:
        error_patterns = [f"对{q['knowledge_point']}概念理解模糊", "审题不仔细导致答非所问", "计算/表达步骤不规范"]
        question_cards.append({
            "title": q["display_title"],
            "knowledge_point": q["knowledge_point"],
            "correct_count": q["correct_count"],
            "wrong_count": q["wrong_count"],
            "blank_count": q["blank_count"],
            "error_patterns": error_patterns[:2],
            "teaching_strategy": f"围绕{q['knowledge_point']}进行专项讲评，结合错因给出规范的解题步骤，并安排同类型变式巩固。",
            "follow_up_exercise": f"完成同类{q['knowledge_point']}变式练习 3 道，下节课前交齐。",
        })

    pre_class = {
        "overview": overview,
        "review_plan": review_plan,
        "question_cards": question_cards,
        "all_wrong_images": [],
    }

    return source_summary, pre_class


def _build_reasons(total):
    """把错题数拆成 1-3 条错误原因（text -> count）。"""
    if total <= 0:
        return {}
    rng = random.Random()
    n = min(3, total)
    parts = []
    remaining = total
    for i in range(n):
        if i == n - 1:
            parts.append(remaining)
        else:
            take = max(1, remaining - (n - 1 - i))
            parts.append(take)
            remaining -= take
    reasons = {}
    texts = ["概念不清", "粗心失误", "审题不仔细", "方法不会用", "书写不规范"]
    random.shuffle(texts)
    for i, cnt in enumerate(parts):
        reasons[texts[i]] = cnt
    return reasons


# ═════════════════════════ 智能组卷试卷 / 题型模板造数 ═════════════════════════

def _exam_q(qtype, content, score, stem="", options=None, sub=None):
    """构造智能组卷前端 ExamQuestion 结构的一题。

    字段对齐 src/components/smart-exam/ExamGenPage.tsx 的 ExamQuestion 接口：
    id / type / stem / content / options[] / score / subQuestions?
    - type ∈ {choice, fill, judge, short_answer, essay}
    - choice 必须提供 4 个中文选项（options）；其余题型 options 为空数组
    - short_answer 带 2-3 个子题（subQuestions）
    """
    q = {
        "id": str(uuid.uuid4()),
        "type": qtype,
        "stem": stem,
        "content": content,
        "score": score,
        "options": options if options is not None else (["", "", "", ""] if qtype == "choice" else []),
    }
    if qtype == "short_answer":
        q["subQuestions"] = sub or []
    return q


def build_smart_exam_papers(admin_id):
    """智能组卷-用户试卷库造数：4 科 × 2 套 = 8 套测试卷，每套 8-12 题。

    questions 存 Python list（smart_exam_papers.questions 为 MySQL JSON 列，
    交给 SQLAlchemy 负责序列化；不要预转 JSON 字符串，否则双重编码后前端拿不到数组）。
    """
    papers = [
        # ── 语文：fill 拼音/课文/古诗 + choice + judge + short_answer 阅读 + essay 作文 ──
        {
            "title": "演示-小学六年级语文期末测试卷",
            "subject": "语文",
            "questions": [
                _exam_q("fill", "看拼音写词语：míng mèi（　）zàn tàn（　）wēn nuǎn（　）。", 6),
                _exam_q("fill", "《匆匆》按课文内容填空：燕子去了，有再来的时候；杨柳枯了，有再青的时候；______了，有______的时候。", 6),
                _exam_q("fill", "默写《竹石》：咬定青山不放松，______。千磨万击还坚劲，______。", 6),
                _exam_q("fill", "在括号里填上恰当的关联词语：我们（　）要学好各门功课，（　）要锻炼好身体。", 4),
                _exam_q("choice", "下列词语书写完全正确的一项是（　）", 4,
                        options=["再接再厉", "兴高彩烈", "阴谋鬼计", "迫不急待"]),
                _exam_q("judge", "“鼎”字共有 12 画。", 3),
                _exam_q("judge", "《卖火柴的小女孩》的作者是丹麦作家安徒生。", 3),
                _exam_q("short_answer", "根据短文内容，回答下面的问题。", 12,
                        stem="阅读短文《父亲的爱》，完成下列问题。",
                        sub=["短文主要写了父亲的哪几件事？", "从这些事中你体会到了父亲怎样的爱？", "文中的“我”最后明白了什么？"]),
                _exam_q("short_answer", "根据课文内容回答问题。", 12,
                        stem="阅读《草船借箭》片段，回答问题。",
                        sub=["诸葛亮为什么能成功借到箭？", "从这件事可以看出诸葛亮怎样的特点？"]),
                _exam_q("short_answer", "回答下列问题。", 10,
                        stem="阅读古诗《泊船瓜洲》。",
                        sub=["“春风又绿江南岸”中的“绿”字好在哪里？", "这首诗表达了诗人怎样的思想感情？"]),
                _exam_q("essay", "题目：一件难忘的事。要求：把事情的经过写清楚，写出自己的真实感受，字数不少于 400 字。", 30),
            ],
        },
        {
            "title": "演示-小学五年级语文单元测试卷",
            "subject": "语文",
            "questions": [
                _exam_q("fill", "看拼音写词语：jìng mò（　）qīng tīng（　）jī lì（　）。", 6),
                _exam_q("fill", "《白鹭》按课文内容填空：白鹭实在是一首诗，一首______的散文诗。", 6),
                _exam_q("fill", "把下列词语补充完整：千（　）万（　）；（　）山（　）水。", 5),
                _exam_q("choice", "下列加点字读音全部正确的一组是（　）", 4,
                        options=["便（pián）宜", "间隔（jiān）", "待（dāi）会儿", "勉强（qiáng）"]),
                _exam_q("choice", "“居高声自远，非是藉秋风”一诗的作者是（　）", 4,
                        options=["骆宾王", "虞世南", "王维", "李白"]),
                _exam_q("judge", "《落花生》告诉我们：人要做有用的人，不要做只讲体面而对别人没有好处的人。", 4),
                _exam_q("judge", "“信赖，往往创造出美好的境界。”这句话出自课文《珍珠鸟》。", 4),
                _exam_q("short_answer", "根据课文内容回答。", 12,
                        stem="阅读《落花生》片段，回答问题。",
                        sub=["父亲拿花生与桃子、石榴、苹果作比较，目的是什么？", "你从“落花生”身上学到了什么做人的道理？"]),
                _exam_q("short_answer", "根据课文内容回答。", 12,
                        stem="阅读《桂花雨》，回答问题。",
                        sub=["“这里的桂花再香，也比不上家乡院子里的桂花。”这句话表达了作者怎样的思想感情？", "课文题目为什么叫“桂花雨”？"]),
                _exam_q("fill", "用“骄傲”分别造一个表示“自满”和“自豪”意思的句子。（骄傲①______　骄傲②______）", 5),
                _exam_q("essay", "题目：我的家乡。要求：抓住家乡最有特点的一处景物或一种习俗来写，表达对家乡的热爱，字数不少于 350 字。", 30),
            ],
        },
        # ── 数学：choice 单选 + fill 计算/单位换算 + judge + short_answer 应用题 ──
        {
            "title": "演示-小学六年级数学期末测试卷",
            "subject": "数学",
            "questions": [
                _exam_q("choice", "下面各数中，读作“五百零三万零一”的是（　）", 6,
                        options=["5030001", "5030100", "5300001", "50300001"]),
                _exam_q("choice", "一个三角形三个内角分别是 50°、60°、70°，这个三角形是（　）", 6,
                        options=["锐角三角形", "直角三角形", "钝角三角形", "等腰三角形"]),
                _exam_q("choice", "把 20 克盐放入 200 克水中，盐占盐水的（　）", 6,
                        options=["1/10", "1/11", "1/9", "1/12"]),
                _exam_q("fill", "直接写出得数：25×40=（　）　720÷8=（　）　3.6+4.4=（　）。", 6),
                _exam_q("fill", "单位换算：3.5 千克=（　）克；2.4 时=（　）分。", 6),
                _exam_q("fill", "一个圆的直径是 6 厘米，它的周长是（　）厘米，面积是（　）平方厘米。（π 取 3.14）", 6),
                _exam_q("fill", "如果 a÷b=4（a、b 均不为 0），那么 a 是 b 的（　）倍。", 6),
                _exam_q("judge", "0 除以任何不为 0 的数都得 0。", 6),
                _exam_q("judge", "两个面积相等的三角形一定能拼成一个平行四边形。", 6),
                _exam_q("short_answer", "这条公路全长多少米？", 12,
                        stem="工程队修一条公路，已经修了全长的 3/5，正好是 240 米。",
                        sub=["求公路全长，需要用到怎样的数量关系？", "这条公路全长多少米？"]),
                _exam_q("short_answer", "连环画有多少本？", 12,
                        stem="学校买来故事书 120 本，科技书的本数是故事书的 3/4，连环画的本数是科技书的 5/6。",
                        sub=["先求科技书有多少本？", "再求连环画有多少本？"]),
                _exam_q("short_answer", "它的体积是多少立方厘米？", 12,
                        stem="一个长方体纸箱，长 60 厘米、宽 40 厘米、高 30 厘米。",
                        sub=["长方体体积的计算公式是什么？", "这个纸箱的体积是多少？"]),
            ],
        },
        {
            "title": "演示-小学四年级数学单元测试卷",
            "subject": "数学",
            "questions": [
                _exam_q("choice", "下面算式中，结果最小的是（　）", 6,
                        options=["100-25×2", "(100-25)×2", "100÷(25-5)", "100-25-5"]),
                _exam_q("choice", "把“60÷12=5，5×8=40”合并成一道综合算式是（　）", 6,
                        options=["60÷12×8", "60÷(12×8)", "60×8÷12", "(60÷12)×8"]),
                _exam_q("fill", "口算：125×8=（　）　540÷60=（　）　0÷35=（　）。", 6),
                _exam_q("fill", "在○里填上“＞”“＜”或“＝”：480÷60○480÷80；25×40○25×4×10。", 6),
                _exam_q("fill", "一个数加上 27 得 100，这个数是（　）；一个数乘 8 得 96，这个数是（　）。", 6),
                _exam_q("fill", "用简便方法计算：25×37×4=（　）。", 6),
                _exam_q("judge", "0 不能作除数，但可以作被除数。", 6),
                _exam_q("judge", "两个数相乘的积一定大于这两个数相加的和。", 6),
                _exam_q("short_answer", "需要租多少辆大客车？", 12,
                        stem="学校组织春游，四年级有 4 个班，每班 45 人，老师 20 人。租的大客车每辆限坐 50 人。",
                        sub=["一共有多少人参加春游？", "需要租多少辆大客车？"]),
                _exam_q("short_answer", "运来梨多少千克？", 12,
                        stem="水果店运来苹果 240 千克，运来的梨比苹果的 2 倍少 80 千克。",
                        sub=["先求苹果的 2 倍是多少？", "运来梨多少千克？"]),
                _exam_q("short_answer", "妈妈需要付多少钱？", 12,
                        stem="超市搞促销，每盒巧克力 24 元，买 3 盒送 1 盒。妈妈买了 4 盒。",
                        sub=["“买 3 盒送 1 盒”后，妈妈实际付了几盒的钱？", "妈妈需要付多少钱？"]),
                _exam_q("short_answer", "这本书一共有多少页？", 12,
                        stem="小明读一本书，前 3 天每天读 20 页，后 2 天每天读 30 页。",
                        sub=["前 3 天一共读了多少页？", "这本书一共有多少页？"]),
            ],
        },
        # ── 英语：choice 单选 + fill 单词/语法 + judge 情景判断 + short_answer 阅读 + essay ──
        {
            "title": "演示-小学五年级英语期末测试卷",
            "subject": "英语",
            "questions": [
                _exam_q("choice", "— How do you go to school? — I go to school ______.", 5,
                        options=["on foot", "by foot", "on bus", "by a bus"]),
                _exam_q("choice", "There ______ some milk in the glass.", 5,
                        options=["is", "are", "be", "am"]),
                _exam_q("choice", "We ______ have a football match next Sunday.", 5,
                        options=["are going to", "will going to", "is going to", "am going to"]),
                _exam_q("choice", "She usually ______ to school at 7:00.", 5,
                        options=["goes", "go", "going", "is go"]),
                _exam_q("fill", "根据首字母提示写单词：The c______ is sleeping under the tree.（猫）", 5),
                _exam_q("fill", "用所给词的适当形式填空：Look! The children ______（play）in the park.", 5),
                _exam_q("fill", "英汉互译：图书馆 ______；操场 ______。", 5),
                _exam_q("judge", "情景判断：当别人对你说 “Thank you” 时，你应该回答 “You're welcome”。", 5),
                _exam_q("judge", "判断读音：单词 cake 与 map 中字母 a 的读音相同。", 5),
                _exam_q("short_answer", "根据短文内容回答下列问题。", 12,
                        stem="阅读短文《My Family》。",
                        sub=["How many people are there in the family?", "What does Mr. Brown do?", "Where do they live?"]),
                _exam_q("short_answer", "根据短文内容回答问题。", 12,
                        stem="阅读短文《My Day》。",
                        sub=["What time does Tom get up?", "What does Tom do after school?"]),
                _exam_q("essay", "书面表达：以 “My Day” 为题写一篇英语短文，描述你一天的主要活动，不少于 5 句话，注意时态。", 30,
                        stem="请用英语写一篇短文。"),
            ],
        },
        {
            "title": "演示-小学三年级英语单元测试卷",
            "subject": "英语",
            "questions": [
                _exam_q("choice", "选出不同类的一项：", 5,
                        options=["apple", "banana", "cat", "orange"]),
                _exam_q("choice", "This is ______ eraser.", 5,
                        options=["a", "an", "/", "the"]),
                _exam_q("choice", "— How old are you? — I'm ______.", 5,
                        options=["ten", "fine", "OK", "thanks"]),
                _exam_q("fill", "写出下列单词的复数形式：book—______；pen—______。", 5),
                _exam_q("fill", "根据中文写单词：我______；你______；他______。", 5),
                _exam_q("fill", "用 be 动词填空：I ______ a student. She ______ my mother.", 5),
                _exam_q("judge", "情景判断：当别人问你 “How are you?” 时，你应该回答 “I'm fine, thank you.”", 5),
                _exam_q("judge", "情景判断：在别人帮助你之后，你应该说 “Sorry”。", 5),
                _exam_q("short_answer", "根据短文内容回答问题。", 12,
                        stem="阅读短文《My Friend》。",
                        sub=["What's the girl's name?", "How old is she?"]),
                _exam_q("short_answer", "根据短文内容回答问题。", 12,
                        stem="阅读短文《My Schoolbag》。",
                        sub=["What colour is the schoolbag?", "What's in the schoolbag?"]),
                _exam_q("essay", "书面表达：用英语介绍你的家人（father、mother 或 brother），不少于 3 句话。", 30,
                        stem="请写一段英文短文。"),
            ],
        },
        # ── 科学：choice 植物/物质 + fill + judge + short_answer 实验/观察 ──
        {
            "title": "演示-小学四年级科学期末测试卷",
            "subject": "科学",
            "questions": [
                _exam_q("choice", "植物进行光合作用的主要器官是（　）", 6,
                        options=["根", "茎", "叶", "花"]),
                _exam_q("choice", "下列物体中，容易导电的是（　）", 6,
                        options=["塑料尺", "铁钉", "干木棍", "橡皮"]),
                _exam_q("choice", "下列动物中，属于昆虫的是（　）", 6,
                        options=["蜘蛛", "蜈蚣", "蜜蜂", "蜗牛"]),
                _exam_q("fill", "水的三态变化：水受热变成______，水蒸气遇冷变成______。", 6),
                _exam_q("fill", "磁铁有______个磁极，分别是北极和______。", 6),
                _exam_q("fill", "我们周围常见的力有重力、______和摩擦力。", 6),
                _exam_q("judge", "水在 0℃ 时会结冰。", 6),
                _exam_q("judge", "所有植物的叶子都是绿色的。", 6),
                _exam_q("judge", "磁铁可以吸引所有的金属。", 6),
                _exam_q("short_answer", "观察火焰的变化并解释原因。", 12,
                        stem="实验探究：把点燃的蜡烛罩上玻璃杯。",
                        sub=["火焰会怎样变化？", "请你解释其中的原因。"]),
                _exam_q("short_answer", "记录昆虫的主要特征。", 12,
                        stem="观察与记录：观察身边的昆虫。",
                        sub=["它的身体分为哪几个部分？", "它有几对足？"]),
                _exam_q("short_answer", "根据所学知识回答。", 12,
                        stem="想一想：为什么一年会有四季？",
                        sub=["地球绕太阳公转一周约需多长时间？", "当北半球是夏季时，南半球是什么季节？"]),
            ],
        },
        {
            "title": "演示-小学三年级科学单元测试卷",
            "subject": "科学",
            "questions": [
                _exam_q("choice", "蜗牛喜欢生活在（　）的环境中。", 6,
                        options=["干燥", "潮湿", "寒冷", "明亮"]),
                _exam_q("choice", "下列动物中，能在水里生活的是（　）", 6,
                        options=["兔子", "金鱼", "燕子", "蜜蜂"]),
                _exam_q("choice", "鱼是用（　）呼吸的。", 6,
                        options=["肺", "鳃", "皮肤", "鼻子"]),
                _exam_q("fill", "动物的一生都要经历出生、______、繁殖、______的过程。", 6),
                _exam_q("fill", "鸟类的身体表面覆盖着______，一般都会飞。", 6),
                _exam_q("fill", "动物的分类：根据有没有脊椎，动物可以分为______动物和______动物。", 6),
                _exam_q("judge", "蚯蚓喜欢生活在干燥的土壤里。", 6),
                _exam_q("judge", "鱼的身体是流线型的，有利于在水中游泳。", 6),
                _exam_q("judge", "所有的鸟都会飞。", 6),
                _exam_q("short_answer", "记录它的生活习性和特征。", 12,
                        stem="观察与记录：观察一种你喜欢的动物。",
                        sub=["它住在哪里？", "它吃什么？"]),
                _exam_q("short_answer", "观察蚯蚓会爬向哪一边并说明原因。", 12,
                        stem="实验探究：把蚯蚓放在纸盒中间，一边干燥一边潮湿。",
                        sub=["蚯蚓会爬向哪一边？", "这说明蚯蚓喜欢怎样的环境？"]),
                _exam_q("short_answer", "举例说明动物对人们生活的帮助。", 12,
                        stem="说一说：动物和人类的关系非常密切。",
                        sub=["举一个动物帮助人类的例子。", "我们应该怎样保护动物？"]),
            ],
        },
    ]
    rows = []
    for p in papers:
        rows.append({
            "id": str(uuid.uuid4()),
            "user_id": admin_id,
            "title": p["title"],
            "subject": p["subject"],
            "questions": p["questions"],
        })
    return rows


def build_exam_question_templates(admin_id):
    """学科题型模板造数：4 科各 1 套模板（共 13 行），type_name 带 `演示-` 前缀便于幂等识别。"""
    specs = {
        "语文": [("拼音字词", 8, 4), ("古诗文默写", 6, 5), ("阅读理解", 3, 10), ("作文", 1, 30)],
        "数学": [("口算题", 10, 2), ("应用题", 4, 8), ("图形几何", 5, 4)],
        "英语": [("单词拼写", 10, 2), ("单项选择", 8, 3), ("阅读理解", 2, 10)],
        "科学": [("选择题", 8, 3), ("判断题", 6, 3), ("实验探究", 2, 15)],
    }
    rows = []
    for subject, items in specs.items():
        for sort_order, (type_name, default_count, default_score_each) in enumerate(items):
            rows.append({
                "id": str(uuid.uuid4()),
                "user_id": admin_id,
                "subject": subject,
                "type_name": DEMO_PREFIX + type_name,
                "default_count": default_count,
                "default_score_each": default_score_each,
                "sort_order": sort_order,
            })
    return rows


# ══════════════════════ 管理端看板趋势图数据源（d7-seed-stats） ══════════════════════

def build_grading_daily_stats(admin_id, class_records):
    """看板趋势图-批改量：近 90 天（含今天）每天每演示班级 1 条。

    folder_safe 用 `cls_{class_id}__demo_batch`，可被 admin_dashboard 按班级/年级归属。
    上传/批改份数：工作日 15-70、周末 3-15，并叠加近 90 天缓慢上升趋势
    （growth 0.7→1.3，越接近今天越高），体现真实运营节奏与周波动。
    """
    rows = []
    today = date.today()
    for cls_id, _cls_name, _grade, _students_dict in class_records:
        folder = f"cls_{cls_id}__demo_batch"
        for i in range(90):
            d = today - timedelta(days=i)
            growth = 0.7 + 0.6 * (1 - i / 90.0)  # 0.7(最早) → 1.3(今天)
            if d.weekday() >= 5:  # 周末
                base_u = random.randint(3, 15)
                base_g = random.randint(3, 15)
            else:  # 工作日
                base_u = random.randint(15, 70)
                base_g = random.randint(15, 70)
            upload = _clip(base_u * growth, 1, 120)
            grade = _clip(base_g * growth * random.uniform(0.75, 0.95), 1, 110)
            rows.append({
                "id": str(uuid.uuid4()),
                "user_id": admin_id,
                "folder_safe": folder,
                "stat_date": d,
                "upload_count": upload,
                "grade_count": grade,
            })
    return rows


def build_health_checks(admin_id, class_records):
    """看板趋势图-健康预警：近 30 天每天每班抽样 2-5 个演示学生。

    绝大多数 normal（温度 36.0-37.2、is_alert=0），约 5% 异常
    （温度 37.5-38.5 / health_status=fever / is_alert=1 / 症状），使预警曲线有真实波动。
    """
    rows = []
    today = date.today()
    for cls_id, _cls_name, _grade, students_dict in class_records:
        students = list(students_dict.values())
        for i in range(30):
            d = today - timedelta(days=i)
            for stu in random.sample(students, random.randint(2, 5)):
                if random.random() < 0.05:
                    temperature = Decimal(str(round(random.uniform(37.5, 38.5), 1)))
                    status = "fever"
                    is_alert = 1
                    symptoms = random.choice(["发烧", "咳嗽、咽痛", "乏力、头晕", "发烧、咳嗽"])
                else:
                    temperature = Decimal(str(round(random.uniform(36.0, 37.2), 1)))
                    status = "normal"
                    is_alert = 0
                    symptoms = None
                rows.append({
                    "id": str(uuid.uuid4()),
                    "student_id": stu["id"],
                    "class_id": cls_id,
                    "check_type": "morning",
                    "check_date": d,
                    "temperature": temperature,
                    "health_status": status,
                    "symptoms": symptoms,
                    "is_alert": is_alert,
                    "recorded_by": admin_id,
                })
    return rows


def build_reward_products(admin_id):
    """兑换商品演示数据。

    redemption_records.product_id 为 NOT NULL 外键（reward_products.id，RESTRICT），
    且 reward_products 表当前为空，必须先造商品再造兑换记录。
    """
    items = [
        {"name": "演示-卡通笔记本", "product_type": "physical", "points_required": 40, "stock": 100},
        {"name": "演示-创意文具套装", "product_type": "physical", "points_required": 80, "stock": 60},
        {"name": "演示-励志徽章", "product_type": "physical", "points_required": 25, "stock": 200},
        {"name": "演示-免作业券", "product_type": "coupon", "points_required": 120, "stock": 30},
        {"name": "演示-图书借阅券", "product_type": "coupon", "points_required": 160, "stock": 20},
    ]
    return [{
        "id": str(uuid.uuid4()),
        "name": it["name"],
        "description": f"{it['name']}（演示数据）",
        "product_type": it["product_type"],
        "points_required": it["points_required"],
        "stock": it["stock"],
        "stock_warning": 5,
        "is_active": 1,
        "exchange_limit_per_student": 0,
        "sort_order": 0,
        "created_by": admin_id,
    } for it in items]


def build_redemption_records(admin_id, class_records, product_rows):
    """看板趋势图-兑换量：近 30 天共 20-40 条，随机取演示学生。

    points_spent 20-200、status='approved'，operator_id/approver_id=demo 管理员；
    时间线 created_at → approved_at → delivered_at 严格递增；credit_transaction_id
    关联同批生成的 credit_transactions（redeem 流水，balance_after 按学生累减）。
    """
    redemptions = []
    credit_txns = []
    all_students = [(stu["id"], cls_id)
                    for cls_id, _cn, _g, sd in class_records
                    for stu in sd.values()]
    balance = {}  # student_id -> 该生兑换后的剩余积分
    n = random.randint(20, 40)
    now = datetime.now()
    for _ in range(n):
        sid, cid = random.choice(all_students)
        prod = random.choice(product_rows)
        points = random.randint(20, 200)
        created = now - timedelta(days=random.randint(0, 29),
                                  hours=random.randint(0, 23),
                                  minutes=random.randint(0, 59))
        approved = created + timedelta(hours=random.randint(1, 12))
        delivered = approved + timedelta(hours=random.randint(1, 48))
        rid = str(uuid.uuid4())
        txid = str(uuid.uuid4())
        bal = balance.get(sid, 500) - points
        balance[sid] = bal
        credit_txns.append({
            "id": txid,
            "student_id": sid,
            "class_id": cid,
            "amount": -points,
            "transaction_type": "redeem",
            "balance_after": bal,
            "source_type": "redemption",
            "source_id": rid,
            "operator_id": admin_id,
            "description": f"兑换{prod['name']}",
            "created_at": created,
        })
        redemptions.append({
            "id": rid,
            "student_id": sid,
            "product_id": prod["id"],
            "class_id": cid,
            "points_spent": points,
            "status": "approved",
            "operator_id": admin_id,
            "approver_id": admin_id,
            "approved_at": approved,
            "delivered_at": delivered,
            "notes": "演示兑换数据",
            "credit_transaction_id": txid,
            "created_at": created,
        })
    return redemptions, credit_txns


# ═══════════════════════════════ 清理与入库 ═══════════════════════════════

def _table(name):
    return Table(name, MetaData(), autoload_with=engine)


def cleanup(conn):
    """幂等清理：删除所有 `演示-` 前缀班级及其关联数据 + 演示用户，绝不动其他数据。"""
    ids = [r[0] for r in conn.execute(text("SELECT id FROM classes WHERE name LIKE :p"), {"p": DEMO_PREFIX + "%"})]
    n_class = len(ids)

    # 按 class_id 删除子表（先子后父，满足外键）
    by_class = [
        "student_wrong_questions", "student_score_history", "student_analysis",
        "class_analysis_reports", "class_review_sessions", "class_teachers",
        "exam_scores", "wrong_questions", "wrong_question_review",
    ]
    for t in by_class:
        if not ids:
            break
        in_clause = ",".join([":c%d" % i for i in range(len(ids))])
        params = {"c%d" % i: v for i, v in enumerate(ids)}
        try:
            conn.execute(text(f"DELETE FROM {t} WHERE class_id IN ({in_clause})"), params)
        except Exception:
            pass  # 表可能不存在（如 wrong_question_review）

    # exams：按 class_id 删除（其 name 也带"演示"标识）
    if ids:
        in_clause = ",".join([":c%d" % i for i in range(len(ids))])
        params = {"c%d" % i: v for i, v in enumerate(ids)}
        conn.execute(text(f"DELETE FROM exams WHERE class_id IN ({in_clause})"), params)

    # students / classes
    if ids:
        in_clause = ",".join([":c%d" % i for i in range(len(ids))])
        params = {"c%d" % i: v for i, v in enumerate(ids)}
        conn.execute(text(f"DELETE FROM students WHERE class_id IN ({in_clause})"), params)
        conn.execute(text(f"DELETE FROM classes WHERE id IN ({in_clause})"), params)

    # 演示用户（教师 + 学生账户）
    conn.execute(text("DELETE FROM users WHERE email LIKE :p"), {"p": "demo_%" + DEMO_USER_DOMAIN})

    # D10：演示用户 → 学校绑定（user_roles）+ 「演示小学」锚点，保证重跑从干净状态重建
    conn.execute(text(
        "DELETE ur FROM user_roles ur JOIN users u ON u.id = ur.user_id "
        "WHERE u.email = :e OR u.email LIKE :p"
    ), {"e": DEMO_ADMIN_EMAIL, "p": "demo_%" + DEMO_USER_DOMAIN})
    # 分层分级账户（teacher@/headteacher@/principal@）→ 学校绑定同样先清空：
    # 用户本体走 get_or_create 保留，但每次重跑须重新绑定重建后的演示小学
    #（避免残留旧 school_id 指向已删除的学校行，school scope 会因此查不到班级）。
    conn.execute(text(
        "DELETE ur FROM user_roles ur JOIN users u ON u.id = ur.user_id "
        "WHERE u.email IN (:e1, :e2, :e3)"
    ), {"e1": DEMO_TEACHER_EMAIL, "e2": DEMO_HEADTEACHER_EMAIL, "e3": DEMO_PRINCIPAL_EMAIL})
    try:
        conn.execute(text("DELETE FROM schools WHERE name = :n"), {"n": DEMO_SCHOOL_NAME})
    except Exception:
        pass  # schools 表可能不存在（老库未建锚表），幂等跳过

    # 兜底：名称带"演示"的考试
    conn.execute(text("DELETE FROM exams WHERE title LIKE :p"), {"p": "%" + DEMO_PREFIX + "%"})

    # 智能组卷试卷 / 学科题型模板：按 demo 管理员 user_id 清理（有 id 才执行，表为空/不存在时跳过）
    demo_admin = conn.execute(
        text("SELECT id FROM users WHERE email = :e"), {"e": DEMO_ADMIN_EMAIL}
    ).first()
    if demo_admin:
        for t in ("smart_exam_papers", "exam_question_templates"):
            try:
                conn.execute(text(f"DELETE FROM {t} WHERE user_id = :uid"), {"uid": demo_admin[0]})
            except Exception:
                pass  # 表可能不存在（老库未建），幂等跳过

    # 看板趋势图数据源三张表 + 关联的兑换商品/积分流水：按 demo 管理员 id 清理（幂等）。
    # 顺序：先删 redemption_records（product_id 外键 RESTRICT 指向 reward_products），
    # 再删 credit_transactions / reward_products / grading_daily_stats / health_checks。
    if demo_admin:
        trend_cleanup = {
            "redemption_records": "operator_id",
            "credit_transactions": "operator_id",
            "reward_products": "created_by",
            "grading_daily_stats": "user_id",
            "health_checks": "recorded_by",
        }
        for t, col in trend_cleanup.items():
            try:
                conn.execute(text(f"DELETE FROM {t} WHERE {col} = :uid"), {"uid": demo_admin[0]})
            except Exception:
                pass  # 表可能不存在，幂等跳过

    return n_class


def get_or_create_demo_admin(conn):
    """演示班级归属的系统管理员账号（demo@grade.local / demo123，真哈希）。

    库中已存在则直接复用（不覆盖已有哈希/角色）；不存在则以系统管理员角色创建。
    """
    row = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": DEMO_ADMIN_EMAIL}).first()
    if row:
        return row[0]
    uid = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO users (id, email, password_hash, display_name, roles) "
            "VALUES (:id, :email, :ph, :name, :roles)"
        ),
        {"id": uid, "email": DEMO_ADMIN_EMAIL, "ph": hash_password("demo123"), "name": "演示管理员", "roles": "系统管理员"},
    )
    return uid


def get_or_create_demo_role_user(conn, email, display_name, roles, job_title=None):
    """幂等获取/创建分层分级演示账户（teacher@/headteacher@/principal@，密码 demo123 真哈希）。

    与 get_or_create_demo_admin 同语义：库中已存在则直接复用（不覆盖已有哈希/角色），
    不存在则以指定中文角色创建；job_title 仅校长账户填写。
    """
    row = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).first()
    if row:
        return row[0]
    uid = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO users (id, email, password_hash, display_name, roles, job_title) "
            "VALUES (:id, :email, :ph, :name, :roles, :jt)"
        ),
        {"id": uid, "email": email, "ph": hash_password("demo123"),
         "name": display_name, "roles": roles, "jt": job_title},
    )
    return uid


def _ensure_schools_table(conn):
    """AUTO_DDL=false 下 schools 锚表由 seed 自建（幂等）。

    D9 只建了 School model 未做迁移，库中 schools 表可能不存在；
    seed 以 DDL 兜底，字段对齐 app/models/school.py 的 School
    （region_id 列保留但不建 FK——regions 表可能也不存在，demo 学校不需要区域）。
    """
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS schools ("
        "  id VARCHAR(36) NOT NULL,"
        "  name VARCHAR(128) NOT NULL,"
        "  region_id VARCHAR(36) NULL,"
        "  db_profile_id VARCHAR(36) NULL,"
        "  db_name VARCHAR(128) NULL,"
        "  created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,"
        "  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
        "  deleted_at DATETIME NULL,"
        "  PRIMARY KEY (id),"
        "  KEY idx_schools_name (name),"
        "  KEY idx_schools_db_profile_id (db_profile_id),"
        "  KEY idx_schools_region_id (region_id)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    ))


def _ensure_missing_tables(conn):
    """AUTO_DDL=false 下 5 张缺表由 seed 自建兜底（幂等）。

    库落后 model（D8-AI 会话 / DL1 区域 / DL4a 校本题库均只建 model 未做迁移），
    `/api/v1/ai-chat/history` 等接口因表不存在直接 500。
    seed 以 CREATE TABLE IF NOT EXISTS 兜底，DDL 字段对齐各 model 定义；
    外键一律建成普通索引（schools 先例风格），避免建表顺序/表缺失导致的 FK 失败：
      - agent_conversations.user_id          → users.id（普通索引 idx_aconv_user_id）
      - agent_conversation_messages.conversation_id → agent_conversations.id
      - agent_audit_logs.user_id             → users.id
      - regions.parent_id                    → regions.id（自引用，跳过 FK 约束）
      - school_question_banks.school_id      → schools.id
    建表顺序保证 agent_conversations 先于 agent_conversation_messages。
    """
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS agent_conversations ("
        "  id VARCHAR(36) NOT NULL,"
        "  user_id VARCHAR(36) NOT NULL,"
        "  agent_role_id VARCHAR(36) NULL,"
        "  title VARCHAR(255) NULL,"
        "  summary TEXT NULL,"
        "  context_snapshot JSON NULL,"
        "  message_count INT NOT NULL DEFAULT 0,"
        "  total_tokens INT NOT NULL DEFAULT 0,"
        "  total_cost_cent INT NOT NULL DEFAULT 0,"
        "  status VARCHAR(16) NOT NULL DEFAULT 'active',"
        "  created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,"
        "  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
        "  PRIMARY KEY (id),"
        "  KEY idx_aconv_user_id (user_id),"
        "  KEY idx_aconv_status (status),"
        "  KEY idx_aconv_created_at (created_at)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    ))
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS agent_conversation_messages ("
        "  id VARCHAR(36) NOT NULL,"
        "  conversation_id VARCHAR(36) NOT NULL,"
        "  role VARCHAR(16) NOT NULL,"
        "  content LONGTEXT NOT NULL,"
        "  tool_name VARCHAR(64) NULL,"
        "  tool_call_id VARCHAR(64) NULL,"
        "  tool_result_json LONGTEXT NULL,"
        "  model VARCHAR(64) NULL,"
        "  tokens_used INT NULL,"
        "  cost_cent INT NULL,"
        "  seq INT NOT NULL DEFAULT 0,"
        "  created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,"
        "  PRIMARY KEY (id),"
        "  KEY idx_acmsg_conversation_id (conversation_id),"
        "  KEY idx_acmsg_seq (conversation_id, seq)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    ))
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS agent_audit_logs ("
        "  id VARCHAR(36) NOT NULL,"
        "  user_id VARCHAR(36) NOT NULL,"
        "  conversation_id VARCHAR(36) NULL,"
        "  event_type VARCHAR(32) NOT NULL,"
        "  event_subtype VARCHAR(64) NULL,"
        "  tool_name VARCHAR(64) NULL,"
        "  tool_args_json JSON NULL,"
        "  tool_result_summary TEXT NULL,"
        "  tool_success TINYINT(1) NULL,"
        "  model VARCHAR(64) NULL,"
        "  tokens_used INT NULL,"
        "  cost_cent INT NULL,"
        "  latency_ms INT NULL,"
        "  approval_status VARCHAR(16) NULL,"
        "  approval_reason TEXT NULL,"
        "  ip_address VARCHAR(45) NULL,"
        "  user_agent VARCHAR(512) NULL,"
        "  created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,"
        "  PRIMARY KEY (id),"
        "  KEY idx_aaal_user_id (user_id),"
        "  KEY idx_aaal_event_type (event_type),"
        "  KEY idx_aaal_conversation_id (conversation_id),"
        "  KEY idx_aaal_created_at (created_at)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    ))
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS regions ("
        "  id VARCHAR(36) NOT NULL,"
        "  name VARCHAR(128) NOT NULL,"
        "  level TINYINT NOT NULL,"
        "  parent_id VARCHAR(36) NULL,"
        "  code VARCHAR(32) NULL,"
        "  created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,"
        "  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
        "  deleted_at DATETIME NULL,"
        "  PRIMARY KEY (id),"
        "  KEY idx_regions_parent_id (parent_id),"
        "  KEY idx_regions_code (code)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    ))
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS school_question_banks ("
        "  id VARCHAR(36) NOT NULL,"
        "  school_id VARCHAR(36) NOT NULL,"
        "  subject VARCHAR(64) NULL,"
        "  question_type VARCHAR(32) NULL,"
        "  question_text TEXT NOT NULL,"
        "  correct_answer TEXT NULL,"
        "  knowledge_point_id VARCHAR(36) NULL,"
        "  fingerprint VARCHAR(67) NOT NULL,"
        "  difficulty VARCHAR(16) NULL,"
        "  created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,"
        "  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
        "  deleted_at DATETIME NULL,"
        "  PRIMARY KEY (id),"
        "  UNIQUE KEY uq_sqb_school_fp (school_id, fingerprint),"
        "  KEY idx_sqb_school_id (school_id)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    ))


def get_or_create_demo_school(conn):
    """幂等获取/创建「演示小学」学校锚点（schools 表），返回其 id。"""
    row = conn.execute(text("SELECT id FROM schools WHERE name = :n"), {"n": DEMO_SCHOOL_NAME}).first()
    if row:
        return row[0]
    sid = str(uuid.uuid4())
    conn.execute(
        text("INSERT INTO schools (id, name) VALUES (:id, :name)"),
        {"id": sid, "name": DEMO_SCHOOL_NAME},
    )
    return sid


def bind_demo_users_to_school(conn, school_id):
    """幂等绑定全部演示用户到演示小学（user_roles）。

    - 学生账户（email LIKE 'demo_%@grade.local'）role=student
    - demo 管理员（demo@grade.local）role=school_admin
    同 user_id 已有非空 school_id 行则不重复插入（cleanup 已先清空，此处兜底防重复）。
    """
    users = conn.execute(text(
        "SELECT id, email FROM users WHERE email = :e OR email LIKE :p"
    ), {"e": DEMO_ADMIN_EMAIL, "p": "demo_%" + DEMO_USER_DOMAIN}).fetchall()
    for uid, email in users:
        existing = conn.execute(text(
            "SELECT id FROM user_roles "
            "WHERE user_id = :uid AND school_id IS NOT NULL AND school_id != '' LIMIT 1"
        ), {"uid": uid}).first()
        if existing:
            continue
        role = "school_admin" if email == DEMO_ADMIN_EMAIL else "student"
        conn.execute(
            text(
                "INSERT INTO user_roles (id, user_id, role, school_id) "
                "VALUES (:id, :uid, :role, :sid)"
            ),
            {"id": str(uuid.uuid4()), "uid": uid, "role": role, "sid": school_id},
        )


def bind_demo_role_users_to_school(conn, school_id, headteacher_id, principal_id):
    """幂等绑定分层分级演示账户到演示小学（user_roles）。

    - headteacher@ → role=teacher（用户身份是教师；班主任权由 class_teachers.role=head 授权）
    - principal@  → role=school_admin
    teacher@ 不写 user_roles（任课教师仅经 class_teachers 挂班可见，school_id 为空=全局放行，
    与既有 任课教师 账户行为一致）。
    同 user_id 已有非空 school_id 行则不重复插入（cleanup 已先清空，此处兜底防重复）。
    """
    for uid, role in ((headteacher_id, "teacher"), (principal_id, "school_admin")):
        existing = conn.execute(text(
            "SELECT id FROM user_roles "
            "WHERE user_id = :uid AND school_id IS NOT NULL AND school_id != '' LIMIT 1"
        ), {"uid": uid}).first()
        if existing:
            continue
        conn.execute(
            text(
                "INSERT INTO user_roles (id, user_id, role, school_id) "
                "VALUES (:id, :uid, :role, :sid)"
            ),
            {"id": str(uuid.uuid4()), "uid": uid, "role": role, "sid": school_id},
        )


def run_seed():
    """执行一轮完整造数（清理 + 生成 + 入库），返回各演示表新增行数。"""
    random.seed(20260822)

    t_classes = _table("classes")
    t_students = _table("students")
    t_users = _table("users")
    t_analysis = _table("student_analysis")
    t_history = _table("student_score_history")
    t_wrong = _table("student_wrong_questions")
    t_car = _table("class_analysis_reports")
    t_crs = _table("class_review_sessions")
    t_exams = _table("exams")
    t_exam_scores = _table("exam_scores")
    t_teachers = _table("class_teachers")
    t_smart = _table("smart_exam_papers")
    t_tpl = _table("exam_question_templates")
    t_grading_stat = _table("grading_daily_stats")
    t_health_check = _table("health_checks")
    t_redemption = _table("redemption_records")
    t_credit_txn = _table("credit_transactions")
    t_products = _table("reward_products")

    counts = {}

    # ── 0) 确保 schools 锚表 + 5 张缺表存在（AUTO_DDL=false，seed 自建兜底）──
    with engine.begin() as conn:
        _ensure_schools_table(conn)
        _ensure_missing_tables(conn)

    # ── 1) 清理 ──
    with engine.begin() as conn:
        cleaned = cleanup(conn)
        admin_id = get_or_create_demo_admin(conn)
        school_id = get_or_create_demo_school(conn)
        # 分层分级演示账户（三级）：teacher@ 任课教师 / headteacher@ 班主任 / principal@ 校级管理者
        teacher_id = get_or_create_demo_role_user(conn, DEMO_TEACHER_EMAIL, "演示任课教师", DEMO_ROLE_TEACHER)
        headteacher_id = get_or_create_demo_role_user(conn, DEMO_HEADTEACHER_EMAIL, "演示班主任", DEMO_ROLE_HEADTEACHER)
        principal_id = get_or_create_demo_role_user(conn, DEMO_PRINCIPAL_EMAIL, "演示校长", DEMO_ROLE_PRINCIPAL, job_title="校长")
    counts["_cleaned_classes"] = cleaned

    # 智能组卷试卷（8 套）+ 学科题型模板（13 行），挂在 demo 管理员下
    smart_paper_rows = build_smart_exam_papers(admin_id)
    template_rows = build_exam_question_templates(admin_id)

    # 兑换商品（redemption_records.product_id 为 NOT NULL 外键，必须先造）
    product_rows = build_reward_products(admin_id)

    class_names = build_class_names()
    now = datetime.now()

    # ── 2) 班级 + 学生 + 学生账户 ──
    class_rows = []
    student_rows = []
    user_rows = []
    students_by_class = {}  # class_id -> {name: {id, number, gender}}
    student_user_map = {}   # student_id -> user_id

    class_records = []  # (cls_id, cls_name, grade, students_dict)
    for ci, cls_name in enumerate(class_names):
        grade = GRADES[ci // CLASSES_PER_GRADE]
        cls_id = str(uuid.uuid4())
        n_students = class_student_count()
        boy_ratio = random.uniform(0.45, 0.55)
        n_cols = random.choice([7, 8, 8, 8, 9])  # 教室桌椅列数各班会略有差异
        class_rows.append({
            "id": cls_id,
            "user_id": admin_id,
            "school_level": SCHOOL_LEVEL,
            "grade": grade,
            "name": cls_name,
            "student_count": n_students,
            "school_id": school_id,
        })
        students_dict = {}
        num_seq = random.randint(1, 4)
        stu_i = 0
        for name, gender in build_student_names(ci, n_students, boy_ratio):
            stu_i += 1
            num_seq += 1
            if random.random() < 0.08:
                num_seq += 1  # 学号偶有跳号（转学/休学留空位）
            sid = str(uuid.uuid4())
            number = f"{ci + 1:02d}{num_seq:03d}"
            students_dict[name] = {"id": sid, "number": number, "gender": gender}
            uid = str(uuid.uuid4())
            user_rows.append({
                "id": uid,
                "email": f"demo_student_{ci + 1}_{stu_i}{DEMO_USER_DOMAIN}",
                "password_hash": "x",
                "display_name": name,
                "roles": "学生",
            })
            student_user_map[sid] = uid
            enroll_date = "2025-09-01"
            if random.random() < 0.05:
                enroll_date = f"2025-{random.randint(9, 12):02d}-{random.randint(1, 28):02d}"  # 少量插班/转学
            student_rows.append({
                "id": sid,
                "class_id": cls_id,
                "user_id": uid,
                "name": name,
                "student_number": number,
                "gender": gender,
                "tier": random.choices(["A", "B", "C"], weights=[20, 50, 30])[0],
                "status": "在读",
                "birthday": _birthday(ci // CLASSES_PER_GRADE),
                "enroll_date": enroll_date,
                "seat_row": (stu_i - 1) // n_cols + 1,
                "seat_col": (stu_i - 1) % n_cols + 1,
                "school_id": None,
            })
        students_by_class[cls_id] = students_dict
        class_records.append((cls_id, cls_name, grade, students_dict))

    # 看板趋势图数据源：批改量 / 健康预警 / 兑换量（需 class_records 已生成）
    grading_stat_rows = build_grading_daily_stats(admin_id, class_records)
    health_check_rows = build_health_checks(admin_id, class_records)
    redemption_rows, credit_txn_rows = build_redemption_records(admin_id, class_records, product_rows)

    with engine.begin() as conn:
        conn.execute(t_users.insert(), user_rows)
        conn.execute(t_classes.insert(), class_rows)
        conn.execute(t_students.insert(), student_rows)
        # D10：单校演示 —— 历史遗留/手工班级也归属演示小学（school_id 空则全量放行的
        # 兼容逻辑靠数据填充收口），使 school scope 下班级全集与改前逐字节一致。
        # 额外重指孤儿 school_id：cleanup 每轮删除并重建演示小学，上一轮回填过旧学校 id
        # 的遗留班级需要跟随迁到新学校，否则 classes_with_school 会少记这 2 个班。
        conn.execute(text(
            "UPDATE classes SET school_id = :sid "
            "WHERE school_id IS NULL OR school_id = '' "
            "OR school_id NOT IN (SELECT id FROM schools)"
        ), {"sid": school_id})
        # D10：全部演示用户（admin + 学生账户）绑定到演示小学。
        # 必须在 users 插入之后执行，否则学生账户尚未存在、只绑到管理员。
        bind_demo_users_to_school(conn, school_id)
        # 分层分级演示账户：班主任/校长绑定到演示小学（user_roles）
        bind_demo_role_users_to_school(conn, school_id, headteacher_id, principal_id)
    counts["users"] = len(user_rows)
    counts["classes"] = len(class_rows)
    counts["students"] = len(student_rows)

    # ── 3) 每班每科：分数 / 分析 / 历史 / 错题 / 报表 / 考试 ──
    analysis_rows = []
    history_rows = []
    wrong_rows = []
    car_rows = []
    crs_rows = []
    exam_rows = []
    exam_score_rows = []
    teacher_rows = []

    for ci, (cls_id, cls_name, grade, students_dict) in enumerate(class_records):
        name_list = list(students_dict.keys())
        for subject in SUBJECTS:
            # 生成每个学生 3 次考试分数（时间渐升）；随机 3%-8% 学生缺考个别场次
            absent_by_exam = [pick_absent_students(name_list) for _ in range(3)]
            scores = {}
            base_scores = {}
            for name in name_list:
                if cls_name == PROBLEM_CLASS_SPEC["班级名"] and subject == PROBLEM_CLASS_SPEC["subject"]:
                    # D11 问题班科：独立低分档 base，其余班科逻辑不变
                    base = _clip(random.gauss(PROBLEM_CLASS_BASE_MEAN, PROBLEM_CLASS_BASE_SIGMA),
                                 PROBLEM_CLASS_BASE_LO, PROBLEM_CLASS_BASE_HI)
                else:
                    base = _clip(random.gauss(78, 9), 42, 100)
                base_scores[name] = base
                scores[name] = [
                    None if name in absent_by_exam[idx] else gen_exam_scores(base, idx)
                    for idx in range(3)
                ]
            present_by_idx = [
                [n for n in name_list if scores[n][idx] is not None] for idx in range(3)
            ]
            n_present_final = len(present_by_idx[2])

            # 班级均分 / 排名 / 错题空白（仅统计未缺考学生）
            class_avgs = {}
            rankings = {}
            wrong_map = {}
            blank_map = {}
            for idx, exam_name in enumerate(EXAM_NAMES):
                present = present_by_idx[idx]
                s_list = [scores[n][idx] for n in present]
                class_avgs[exam_name] = round(sum(s_list) / len(s_list)) if s_list else 0
                ordered = sorted(present, key=lambda n: (-scores[n][idx], students_dict[n]["number"]))
                rank_rows = []
                prev_score = None
                prev_rank = 0
                for r_i, name in enumerate(ordered, start=1):
                    rank = prev_rank if prev_score == scores[name][idx] else r_i
                    prev_score = scores[name][idx]
                    prev_rank = rank
                    rank_rows.append({
                        "student_id": students_dict[name]["id"],
                        "student_name": name,
                        "student_number": students_dict[name]["number"],
                        "score": scores[name][idx],
                        "grade": grade_for_score(scores[name][idx]),
                        "rank": rank,
                    })
                rankings[exam_name] = rank_rows
                for name in present:
                    w, b = wrong_blank_of_score(scores[name][idx])
                    wrong_map[(name, idx)] = w
                    blank_map[(name, idx)] = b

            # student_analysis：每生每科 1 行（current=期末分，缺考则取最近一次有效成绩；target=current+3~8）
            for name in name_list:
                current = scores[name][2]
                if current is None:  # 期末缺考取最近一次有效成绩
                    current = scores[name][1] if scores[name][1] is not None else scores[name][0]
                if current is None:
                    current = 60  # 极端兜底（几乎不可能全缺考）
                gap = random.randint(3, 8) if current >= 60 else random.randint(6, 12)
                target = min(100, current + gap)
                analysis_rows.append({
                    "id": str(uuid.uuid4()),
                    "class_id": cls_id,
                    "student_name": name,
                    "subject": subject,
                    "current_score": current,
                    "target_score": target,
                })

            # student_score_history：每生每科 3 行（缺考场次无历史成绩）
            for idx, exam_name in enumerate(EXAM_NAMES):
                for name in name_list:
                    if scores[name][idx] is None:
                        continue  # 缺考：无该场成绩历史
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

            # student_wrong_questions：每生每科 2-5 条（取有成绩场次中最低的一场）
            pool = SUBJECT_QUESTIONS[subject]
            for name in name_list:
                present_idx = [i for i in range(3) if scores[name][i] is not None]
                if not present_idx:
                    continue
                n_wrong = random.randint(2, 5)
                worst_idx = min(present_idx, key=lambda i: scores[name][i])
                titles = random.sample(pool, n_wrong)
                for q in titles:
                    wrong_rows.append({
                        "id": str(uuid.uuid4()),
                        "class_id": cls_id,
                        "student_name": name,
                        "subject": subject,
                        "exam_name": EXAM_NAMES[worst_idx],
                        "question_title": q["title"],
                        "image_url": None,
                        "answer_url": None,
                    })

            # exams + exam_scores（每班每科 3 场，成绩与 history 一致）
            exam_by_name = {}
            for idx, exam_name in enumerate(EXAM_NAMES):
                eid = str(uuid.uuid4())
                exam_by_name[exam_name] = eid
                exam_rows.append({
                    "id": eid,
                    "user_id": admin_id,
                    "class_id": cls_id,
                    "subject": subject,
                    "title": f"{DEMO_PREFIX}{cls_name[len(DEMO_PREFIX):]}-{subject}-{exam_name}",
                    "total_score": 100,
                    "exam_date": EXAM_DATES[exam_name],
                })
                rank_by_name = {r["student_name"]: r["rank"] for r in rankings[exam_name]}
                for name in name_list:
                    if scores[name][idx] is None:
                        continue  # 缺考：该生该场次无成绩记录
                    exam_score_rows.append({
                        "id": str(uuid.uuid4()),
                        "user_id": admin_id,
                        "exam_id": eid,
                        "student_id": students_dict[name]["id"],
                        "score": float(scores[name][idx]),
                        "class_avg": float(class_avgs[exam_name]),
                        "class_rank": rank_by_name[name],
                        "class_id": cls_id,
                        "school_id": None,
                    })

            # class_analysis_reports（每班每科 1 行，JSON 严格对齐前端解析）
            source_summary, analysis = build_class_analysis_report(
                cls_id, cls_name, grade, subject, students_dict, scores, class_avgs, rankings, wrong_map, blank_map,
            )
            car_rows.append({
                "id": str(uuid.uuid4()),
                "report_uuid": str(uuid.uuid4()),
                "class_id": cls_id,
                "class_name": cls_name,
                "subject": subject,
                "exam_names_json": _j(EXAM_NAMES),
                "imported_folder_names_json": _j([f"cls_{cls_id}__{e}" for e in EXAM_NAMES]),
                "source_summary_json": _j(source_summary),
                "analysis_json": _j(analysis),
                "generated_at": now,
            })

            # class_review_sessions（每班每科 1 行，JSON 严格对齐前端解析）
            crs_source, crs_pre = build_class_review_session(cls_id, subject, class_avgs[EXAM_NAMES[-1]], n_present_final)
            crs_rows.append({
                "id": str(uuid.uuid4()),
                "class_id": cls_id,
                "subject": subject,
                "title": f"{subject}课堂讲评",
                "exam_names_json": _j(EXAM_NAMES),
                "imported_folder_names_json": _j([f"cls_{cls_id}__{e}" for e in EXAM_NAMES]),
                "source_summary_json": _j(crs_source),
                "pre_class_json": _j(crs_pre),
                "generated_at": now,
            })

            # class_teachers（班主任，每班 1 条；uq_class_teacher_user 约束 (class_id,user_id) 唯一）
            if subject == SUBJECTS[0]:
                if cls_name == DEMO_HEADTEACHER_CLASS_NAME:
                    # 分层演示：班主任账户（headteacher@）接管该班 head，demo@ 让出该班；
                    # 任课教师账户（teacher@）以 teacher 角色挂同一班（与自助注册逻辑一致）。
                    # 每轮 cleanup 会按 class_id 清空该班 class_teachers，重跑不产生重复 head。
                    teacher_rows.append({
                        "id": str(uuid.uuid4()),
                        "class_id": cls_id,
                        "user_id": headteacher_id,
                        "role": "head",
                        "subject": None,
                    })
                    teacher_rows.append({
                        "id": str(uuid.uuid4()),
                        "class_id": cls_id,
                        "user_id": teacher_id,
                        "role": "teacher",
                        "subject": None,
                    })
                else:
                    teacher_rows.append({
                        "id": str(uuid.uuid4()),
                        "class_id": cls_id,
                        "user_id": admin_id,
                        "role": "head",
                        "subject": None,
                    })

    # 分批入库（executemany 控制每批行数，避免包过大）
    with engine.begin() as conn:
        _bulk(conn, t_analysis, analysis_rows)
        _bulk(conn, t_history, history_rows)
        _bulk(conn, t_wrong, wrong_rows)
        _bulk(conn, t_car, car_rows)
        _bulk(conn, t_crs, crs_rows)
        _bulk(conn, t_exams, exam_rows)
        _bulk(conn, t_exam_scores, exam_score_rows)
        _bulk(conn, t_teachers, teacher_rows)
        _bulk(conn, t_smart, smart_paper_rows)
        _bulk(conn, t_tpl, template_rows)
        _bulk(conn, t_products, product_rows)
        _bulk(conn, t_credit_txn, credit_txn_rows)
        _bulk(conn, t_redemption, redemption_rows)
        _bulk(conn, t_grading_stat, grading_stat_rows)
        _bulk(conn, t_health_check, health_check_rows)

    counts["student_analysis"] = len(analysis_rows)
    counts["student_score_history"] = len(history_rows)
    counts["student_wrong_questions"] = len(wrong_rows)
    counts["class_analysis_reports"] = len(car_rows)
    counts["class_review_sessions"] = len(crs_rows)
    counts["exams"] = len(exam_rows)
    counts["exam_scores"] = len(exam_score_rows)
    counts["class_teachers"] = len(teacher_rows)
    counts["smart_exam_papers"] = len(smart_paper_rows)
    counts["exam_question_templates"] = len(template_rows)
    counts["grading_daily_stats"] = len(grading_stat_rows)
    counts["health_checks"] = len(health_check_rows)
    counts["redemption_records"] = len(redemption_rows)
    counts["credit_transactions"] = len(credit_txn_rows)
    counts["reward_products"] = len(product_rows)

    return counts


def _j(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _bulk(conn, table, rows, batch=2000):
    if not rows:
        return
    for i in range(0, len(rows), batch):
        conn.execute(table.insert(), rows[i:i + batch])


def count_demo_rows():
    """统计各演示表新增行数（以 `演示-` 班级/用户/考试为范围）。"""
    counts = {}
    with engine.connect() as conn:
        demo_id_sql = "SELECT id FROM classes WHERE name LIKE :p"
        ids = [r[0] for r in conn.execute(text(demo_id_sql), {"p": DEMO_PREFIX + "%"})]
        in_clause = ",".join([":c%d" % i for i in range(len(ids))]) if ids else "''"
        params = {"c%d" % i: v for i, v in enumerate(ids)} if ids else {}

        def cnt(sql, p=None):
            return conn.execute(text(sql), p or {}).scalar() or 0

        counts["classes"] = cnt("SELECT COUNT(*) FROM classes WHERE name LIKE :p", {"p": DEMO_PREFIX + "%"})
        counts["students"] = cnt(f"SELECT COUNT(*) FROM students WHERE class_id IN ({in_clause})", params)
        for t in ["student_analysis", "student_score_history", "student_wrong_questions",
                  "class_analysis_reports", "class_review_sessions", "class_teachers", "exam_scores"]:
            counts[t] = cnt(f"SELECT COUNT(*) FROM {t} WHERE class_id IN ({in_clause})", params)
        counts["exams"] = cnt("SELECT COUNT(*) FROM exams WHERE title LIKE :p", {"p": "%" + DEMO_PREFIX + "%"})
        counts["users"] = cnt("SELECT COUNT(*) FROM users WHERE email LIKE :p", {"p": "demo_%" + DEMO_USER_DOMAIN})

        # D10：学校锚点 + 班级 school 归属 + demo 管理员学校绑定
        counts["schools"] = cnt("SELECT COUNT(*) FROM schools WHERE name = :n", {"n": DEMO_SCHOOL_NAME})
        counts["classes_total"] = cnt("SELECT COUNT(*) FROM classes")
        counts["classes_no_school"] = cnt("SELECT COUNT(*) FROM classes WHERE school_id IS NULL OR school_id = ''")
        demo_school_id = conn.execute(text("SELECT id FROM schools WHERE name = :n"), {"n": DEMO_SCHOOL_NAME}).scalar()
        counts["classes_with_school"] = cnt(
            "SELECT COUNT(*) FROM classes WHERE school_id = :sid", {"sid": demo_school_id}
        ) if demo_school_id else 0
        counts["demo_admin_school_bindings"] = cnt(
            "SELECT COUNT(*) FROM user_roles ur JOIN users u ON u.id = ur.user_id "
            "WHERE u.email = :e AND ur.school_id IS NOT NULL AND ur.school_id != ''",
            {"e": DEMO_ADMIN_EMAIL},
        )
        counts["demo_users_total"] = cnt(
            "SELECT COUNT(*) FROM users WHERE email = :e OR email LIKE :p",
            {"e": DEMO_ADMIN_EMAIL, "p": "demo_%" + DEMO_USER_DOMAIN},
        )
        counts["demo_user_school_bindings"] = cnt(
            "SELECT COUNT(*) FROM user_roles ur JOIN users u ON u.id = ur.user_id "
            "WHERE (u.email = :e OR u.email LIKE :p) "
            "AND ur.school_id IS NOT NULL AND ur.school_id != ''",
            {"e": DEMO_ADMIN_EMAIL, "p": "demo_%" + DEMO_USER_DOMAIN},
        )

        # 智能组卷试卷 / 学科题型模板：按 demo 管理员 user_id 统计
        demo_admin_id = conn.execute(
            text("SELECT id FROM users WHERE email = :e"), {"e": DEMO_ADMIN_EMAIL}
        ).scalar()
        if demo_admin_id:
            counts["smart_exam_papers"] = cnt(
                "SELECT COUNT(*) FROM smart_exam_papers WHERE user_id = :uid", {"uid": demo_admin_id}
            )
            counts["exam_question_templates"] = cnt(
                "SELECT COUNT(*) FROM exam_question_templates WHERE user_id = :uid", {"uid": demo_admin_id}
            )
            counts["grading_daily_stats"] = cnt(
                "SELECT COUNT(*) FROM grading_daily_stats WHERE user_id = :uid", {"uid": demo_admin_id}
            )
            counts["health_checks"] = cnt(
                "SELECT COUNT(*) FROM health_checks WHERE recorded_by = :uid", {"uid": demo_admin_id}
            )
            counts["redemption_records"] = cnt(
                "SELECT COUNT(*) FROM redemption_records WHERE operator_id = :uid", {"uid": demo_admin_id}
            )
            counts["credit_transactions"] = cnt(
                "SELECT COUNT(*) FROM credit_transactions WHERE operator_id = :uid", {"uid": demo_admin_id}
            )
            counts["reward_products"] = cnt(
                "SELECT COUNT(*) FROM reward_products WHERE created_by = :uid", {"uid": demo_admin_id}
            )
        else:
            counts["smart_exam_papers"] = 0
            counts["exam_question_templates"] = 0
            counts["grading_daily_stats"] = 0
            counts["health_checks"] = 0
            counts["redemption_records"] = 0
            counts["credit_transactions"] = 0
            counts["reward_products"] = 0
    return counts


def verify_report_json():
    """抽查 1 个班的 class_analysis_reports / class_review_sessions JSON 结构字段齐全。"""
    import json
    problems = []
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT c.id, c.name, c.student_count, r.subject, r.exam_names_json, r.source_summary_json, r.analysis_json "
            "FROM class_analysis_reports r JOIN classes c ON c.id = r.class_id "
            "WHERE c.name LIKE :p LIMIT 1"
        ), {"p": DEMO_PREFIX + "%"}).first()
        if not row:
            return ["未找到演示班级的 class_analysis_reports"], None
        cls_id, cls_name, class_size, subject, en_json, ss_json, an_json = row
        exam_names = json.loads(en_json)
        ss = json.loads(ss_json)
        an = json.loads(an_json)

        # 报表 student_count 必须等于班级真实人数（classes.student_count）
        ss_class = ss.get("class") or {}
        if ss_class.get("student_count") != class_size:
            problems.append(f"source_summary.class.student_count 应为 {class_size}: {ss_class.get('student_count')}")

        # exam_names 必须 3 个且为固定考试名
        if exam_names != EXAM_NAMES:
            problems.append(f"exam_names 不一致: {exam_names}")
        summaries = ss.get("exam_summaries") or []
        if len(summaries) != 3:
            problems.append(f"exam_summaries 应为 3 条, 实为 {len(summaries)}")
        for s in summaries:
            for key in ["exam_name", "average_score", "median_score", "highest_score", "lowest_score", "rankings"]:
                if key not in s:
                    problems.append(f"exam_summaries 缺字段 {key}")
            for r in s.get("rankings") or []:
                for key in ["student_id", "student_name", "student_number", "score", "grade", "rank"]:
                    if key not in r:
                        problems.append(f"rankings 缺字段 {key}")

        # 四者考试名一致：exam_names / exam_summaries[].exam_name / heatmap / student_warnings
        for s in summaries:
            if s["exam_name"] not in exam_names:
                problems.append(f"exam_summaries 考试名不在 exam_names: {s['exam_name']}")
        heatmap_exams = set()
        for h in an.get("knowledge_heatmap") or []:
            for v in h.get("values") or []:
                heatmap_exams.add(v.get("exam_name"))
                if "risk_score" not in v or "evidence_count" not in v:
                    problems.append("knowledge_heatmap values 缺 risk_score/evidence_count")
        if heatmap_exams and heatmap_exams != set(exam_names):
            problems.append(f"knowledge_heatmap 考试名与 exam_names 不一致: {heatmap_exams}")
        for w in an.get("student_warnings") or []:
            for we in w.get("warning_exams") or []:
                if we.get("exam_name") not in exam_names:
                    problems.append(f"student_warnings 考试名不在 exam_names: {we.get('exam_name')}")
        if len(an.get("student_warnings") or []) < 3:
            problems.append("student_warnings 少于 3 条")

        # class_review_sessions 抽查
        crs = conn.execute(text(
            "SELECT r.source_summary_json, r.pre_class_json FROM class_review_sessions r "
            "WHERE r.class_id = :c AND r.subject = :s"
        ), {"c": cls_id, "s": subject}).first()
        if not crs:
            problems.append("class_review_sessions 未找到对应行")
        else:
            rss = json.loads(crs[0])
            pre = json.loads(crs[1])
            hq = rss.get("high_risk_questions") or []
            if len(hq) < 3:
                problems.append(f"high_risk_questions 少于 3 题: {len(hq)}")
            for q in hq:
                for key in ["question_key", "display_title", "correct_count", "wrong_count", "blank_count", "ungraded_count", "reasons"]:
                    if key not in q:
                        problems.append(f"high_risk_questions 缺字段 {key}")
                total = q.get("correct_count", 0) + q.get("wrong_count", 0) + q.get("blank_count", 0) + q.get("ungraded_count", 0)
                eff = rss.get("valid_student_count")
                if eff is None or abs(total - eff) > 2:
                    problems.append(f"high_risk_question 计数总和不接近有效人数 {eff}: {q.get('display_title')} -> {total}")
            qcards = pre.get("question_cards") or []
            if not qcards:
                problems.append("pre_class.question_cards 为空")
            for c in qcards:
                for key in ["title", "knowledge_point", "error_patterns", "teaching_strategy"]:
                    if key not in c:
                        problems.append(f"question_cards 缺字段 {key}")
            vsc = rss.get("valid_student_count")
            if not (MIN_PRESENT_PER_EXAM <= (vsc or 0) <= class_size):
                problems.append(f"valid_student_count 应介于 {MIN_PRESENT_PER_EXAM}-{class_size}: {vsc}")

    return problems, (cls_id, cls_name, subject)


def print_header():
    print("=" * 70)
    print("演示数据造数脚本 demo_seed.py")
    print(f"数据库: {engine.url}")
    print("=" * 70)


def main():
    print_header()

    print("\n[第 1 轮] 开始造数 ...")
    counts1 = run_seed()
    rows1 = count_demo_rows()
    print_counts(rows1, "第 1 轮")

    print("\n[第 2 轮] 再次运行验证幂等 ...")
    counts2 = run_seed()
    rows2 = count_demo_rows()
    print_counts(rows2, "第 2 轮")

    # ── 幂等验证 ──
    print("\n[幂等验证]")
    same = rows1 == rows2
    for k in rows1:
        mark = "OK" if rows1[k] == rows2[k] else "DIFF"
        print(f"  {k:<26} 第1轮={rows1[k]:>7}  第2轮={rows2[k]:>7}  {mark}")
    if same:
        print("  => 幂等验证通过：连跑两遍各表行数完全一致")
    else:
        print("  => 幂等验证失败：两次行数不一致！")

    # ── 关键规模断言（expect 为 int 精确匹配，为 (lo,hi) 区间匹配）──
    print("\n[关键规模]")
    checks = [
        ("演示班级数", rows1["classes"], 24),
        ("演示学校数", rows1["schools"], 1),
        ("无 school_id 班级数", rows1["classes_no_school"], 0),
        ("归属演示小学班级数", rows1["classes_with_school"], rows1["classes_total"]),
        ("demo 用户学校绑定数", rows1["demo_user_school_bindings"], rows1["demo_users_total"]),
        ("demo 管理员学校绑定数", rows1["demo_admin_school_bindings"], 1),
        ("学生总数", rows1["students"], (1000, 1400)),
        ("exam_scores", rows1["exam_scores"], (rows1["students"] * 11, rows1["students"] * 12)),
        ("student_score_history", rows1["student_score_history"], (rows1["students"] * 11, rows1["students"] * 12)),
        ("class_analysis_reports", rows1["class_analysis_reports"], 96),
        ("class_review_sessions", rows1["class_review_sessions"], 96),
        ("smart_exam_papers", rows1["smart_exam_papers"], 8),
        ("exam_question_templates", rows1["exam_question_templates"], 13),
        ("grading_daily_stats", rows1["grading_daily_stats"], 2160),
        ("health_checks", rows1["health_checks"], (1440, 3600)),
        ("redemption_records", rows1["redemption_records"], (20, 40)),
    ]
    all_ok = same
    for label, val, expect in checks:
        if isinstance(expect, tuple):
            lo, hi = expect
            ok = lo <= val <= hi
            expect_txt = f"[{lo},{hi}]"
        else:
            ok = val == expect
            expect_txt = str(expect)
        all_ok = all_ok and ok
        print(f"  {label}: {val} (期望 {expect_txt})  {'OK' if ok else 'FAIL'}")

    # ── JSON 结构抽查 ──
    print("\n[JSON 结构抽查]")
    problems, info = verify_report_json()
    if info:
        print(f"  抽查班级: {info[1]} / {info[2]}")
    if problems:
        all_ok = False
        for p in problems:
            print(f"  [FAIL] {p}")
    else:
        print("  => class_analysis_reports / class_review_sessions JSON 结构字段齐全，考试名四者一致")

    print()
    if all_ok:
        print("全部验收通过 ✅")
    else:
        print("存在验收失败项 ❌，请检查上方输出")


def print_counts(rows, label):
    print(f"[{label}] 各演示表新增行数：")
    for k in ["classes", "students", "users", "schools", "classes_total",
              "classes_no_school", "classes_with_school",
              "demo_users_total", "demo_user_school_bindings", "demo_admin_school_bindings",
              "student_analysis", "student_score_history",
              "student_wrong_questions", "class_analysis_reports", "class_review_sessions",
              "exams", "exam_scores", "class_teachers", "smart_exam_papers", "exam_question_templates",
              "grading_daily_stats", "health_checks", "redemption_records",
              "credit_transactions", "reward_products"]:
        if k in rows:
            print(f"  {k:<26} {rows[k]:>7}")


if __name__ == "__main__":
    main()
