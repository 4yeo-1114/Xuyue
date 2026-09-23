# -*- coding: utf-8 -*-
"""教材目录「多版本 + 高中段」补全 seed（textbook_catalogs 表）。

在既有 seed（人教版 · 小学 6 年级 + 初中 3 年级，占位单元）基础上，补齐：
  1. 缺失的教材版本：北师大版 / 苏教版 / 外研版 / 冀教版（按各版本实际开课的学科覆盖）；
  2. 高中段：人教版 + 其余版本的高一/高二/高三目录（前端原只有小学/初中）。

幂等：按 (subject, edition, grade, name) 自然键查重，已存在则跳过；可重复运行。
用法：python scripts/seed_textbook_catalogs_editions.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text  # noqa: E402

from app.database import engine, _ensure_textbook_catalogs_table  # noqa: E402
from app.models.user import gen_uuid  # noqa: E402

PRIMARY_GRADES = [
    "小学一年级", "小学二年级", "小学三年级",
    "小学四年级", "小学五年级", "小学六年级",
]
JUNIOR_GRADES = ["初一", "初二", "初三"]
SENIOR_GRADES = ["高一", "高二", "高三"]

# 各版本 × 学段 的学科覆盖（按真实开课范围，避免给不存在的组合造空目录）
EDITION_PLAN = {
    "人教版": {
        "primary": ["语文", "数学", "英语", "科学", "道德与法治"],
        "junior": ["语文", "数学", "英语", "道德与法治", "历史", "地理", "生物", "物理", "化学"],
        "senior": ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "政治"],
    },
    "北师大版": {
        "primary": ["数学"],
        "junior": ["数学", "语文"],
        "senior": ["数学"],
    },
    "苏教版": {
        "primary": ["语文", "数学"],
        "junior": ["语文", "数学"],
        "senior": ["语文"],
    },
    "外研版": {
        "primary": ["英语"],
        "junior": ["英语"],
        "senior": ["英语"],
    },
    "冀教版": {
        "primary": ["数学", "英语"],
        "junior": ["数学"],
        "senior": [],
    },
}

# 结构化兜底单元（各学科通用，保证目录页有真实可展开的单元；
# 真实章节在 REAL_UNITS 里按 (edition, subject, grade) 覆盖）
GENERIC_UNITS = {
    "语文": ["第一单元 阅读鉴赏", "第二单元 古诗文诵读", "第三单元 现代文阅读",
             "第四单元 写作指导", "第五单元 口语交际", "第六单元 整本书阅读"],
    "数学": ["第一章 数与代数", "第二章 图形与几何", "第三章 统计与概率",
             "第四章 函数与方程", "第五章 综合与实践", "第六章 复习与拓展"],
    "英语": ["Module 1 基础词汇", "Module 2 语法专题", "Module 3 阅读理解",
             "Module 4 听说训练", "Module 5 写作表达", "Module 6 综合复习"],
    "科学": ["第一单元 生命世界", "第二单元 物质世界", "第三单元 地球与宇宙",
             "第四单元 技术与工程", "第五单元 科学探究", "第六单元 综合应用"],
    "道德与法治": ["第一单元 成长的节拍", "第二单元 友谊的天空", "第三单元 师长情谊",
                   "第四单元 生命的思考", "第五单元 法治观念", "第六单元 责任担当"],
    "历史": ["第一单元 史前与古代", "第二单元 秦汉至隋唐", "第三单元 宋元至明清",
             "第四单元 近代探索", "第五单元 现代中国", "第六单元 世界历史"],
    "地理": ["第一单元 地球与地图", "第二单元 世界地理", "第三单元 中国地理",
             "第四单元 气候与环境", "第五单元 人口与城市", "第六单元 区域发展"],
    "生物": ["第一单元 细胞与分子", "第二单元 遗传与进化", "第三单元 稳态与环境",
             "第四单元 生物多样性", "第五单元 生物技术", "第六单元 实验探究"],
    "物理": ["第一章 运动与力", "第二章 声与光", "第三章 热现象",
             "第四章 电与磁", "第五章 能量与守恒", "第六章 综合应用"],
    "化学": ["第一单元 走进化学", "第二单元 物质结构", "第三单元 化学反应",
             "第四单元 元素及其化合物", "第五单元 有机化学", "第六单元 实验探究"],
    "政治": ["第一单元 生活与消费", "第二单元 生产劳动与经营", "第三单元 政治生活",
             "第四单元 文化与生活", "第五单元 哲学与人生", "第六单元 综合探究"],
}

# 真实章节（核心教材，按 (edition, subject, grade) 精确覆盖；其余走 GENERIC_UNITS）
REAL_UNITS = {
    # ── 人教版 · 高中（必修 / 选择性必修） ──
    ("人教版", "数学", "高一"): ["第一章 集合与常用逻辑用语", "第二章 一元二次函数、方程和不等式",
                                "第三章 函数的概念与性质", "第四章 指数函数与对数函数", "第五章 三角函数"],
    ("人教版", "数学", "高二"): ["第一章 平面向量及其应用", "第二章 复数", "第三章 立体几何初步",
                                "第四章 统计", "第五章 概率"],
    ("人教版", "数学", "高三"): ["专题一 函数与导数", "专题二 三角函数与解三角形", "专题三 数列",
                                "专题四 立体几何", "专题五 解析几何", "专题六 概率与统计"],
    ("人教版", "物理", "高一"): ["第一章 运动的描述", "第二章 匀变速直线运动的研究",
                                "第三章 相互作用——力", "第四章 运动和力的关系"],
    ("人教版", "物理", "高二"): ["第一章 抛体运动", "第二章 圆周运动", "第三章 万有引力与宇宙航行",
                                "第四章 机械能守恒定律", "第五章 静电场及其应用"],
    ("人教版", "物理", "高三"): ["专题一 力学综合", "专题二 电磁学", "专题三 热学",
                                "专题四 光学与原子物理", "专题五 实验探究", "专题六 高考冲刺"],
    ("人教版", "化学", "高一"): ["第一章 物质及其变化", "第二章 海水中的重要元素——钠和氯",
                                "第三章 铁 金属材料", "第四章 物质结构 元素周期律"],
    ("人教版", "化学", "高二"): ["第一章 化学反应与能量", "第二章 化学反应速率与化学平衡",
                                "第三章 水溶液中的离子反应与平衡", "第四章 有机化学基础"],
    ("人教版", "化学", "高三"): ["专题一 化学基本概念", "专题二 元素化合物", "专题三 化学反应原理",
                                "专题四 有机化学", "专题五 化学实验", "专题六 高考冲刺"],
    ("人教版", "生物", "高一"): ["第1章 走近细胞", "第2章 组成细胞的分子", "第3章 细胞的基本结构",
                                "第4章 细胞的物质输入和输出", "第5章 细胞的能量供应和利用"],
    ("人教版", "生物", "高二"): ["第1章 遗传因子的发现", "第2章 基因和染色体的关系",
                                "第3章 基因的本质", "第4章 生物的进化", "第5章 稳态与调节"],
    ("人教版", "生物", "高三"): ["专题一 分子与细胞", "专题二 遗传与进化", "专题三 稳态与环境",
                                "专题四 生物技术", "专题五 实验探究", "专题六 高考冲刺"],
    ("人教版", "英语", "高一"): ["Welcome Unit", "Unit 1 Teenage Life", "Unit 2 Travelling Around",
                                "Unit 3 Sports and Fitness", "Unit 4 Natural Disasters", "Unit 5 Languages Around the World"],
    ("人教版", "英语", "高二"): ["Unit 1 Science Fiction", "Unit 2 Iconic Attractions",
                                "Unit 3 Environmental Protection", "Unit 4 Adversity and Courage", "Unit 5 Launching Your Career"],
    ("人教版", "英语", "高三"): ["Module 1 阅读理解专项", "Module 2 完形填空专项", "Module 3 语法填空专项",
                                "Module 4 写作专项", "Module 5 听说专项", "Module 6 高考冲刺"],
    ("人教版", "语文", "高一"): ["第一单元 青春激扬", "第二单元 劳动光荣", "第三单元 生命的诗意",
                                "第四单元 家乡文化生活", "第五单元 整本书阅读", "第六单元 古诗词诵读"],
    ("人教版", "语文", "高二"): ["第一单元 中国革命传统", "第二单元 现当代文学", "第三单元 外国文学",
                                "第四单元 逻辑与思辨", "第五单元 整本书阅读", "第六单元 古诗词诵读"],
    ("人教版", "语文", "高三"): ["专题一 论述类文本阅读", "专题二 文学类文本阅读", "专题三 文言文阅读",
                                "专题四 古代诗歌鉴赏", "专题五 语言文字运用", "专题六 写作"],
    ("人教版", "历史", "高一"): ["第一单元 从中华文明起源到秦汉", "第二单元 三国至隋唐",
                                "第三单元 辽宋夏金多民族政权并立", "第四单元 明清中国版图的奠定"],
    ("人教版", "历史", "高二"): ["第一单元 政治制度与治理", "第二单元 经济与社会生活",
                                "第三单元 文化交流与传播", "第四单元 世界近代史"],
    ("人教版", "历史", "高三"): ["专题一 中国古代史", "专题二 中国近现代史", "专题三 世界史",
                                "专题四 史学素养", "专题五 综合训练", "专题六 高考冲刺"],
    ("人教版", "地理", "高一"): ["第一章 宇宙中的地球", "第二章 地球上的大气", "第三章 地球上的水",
                                "第四章 地貌", "第五章 植被与土壤"],
    ("人教版", "地理", "高二"): ["第一章 人口", "第二章 乡村和城镇", "第三章 产业区位因素",
                                "第四章 交通运输布局", "第五章 环境与发展"],
    ("人教版", "地理", "高三"): ["专题一 自然地理", "专题二 人文地理", "专题三 区域地理",
                                "专题四 综合应用", "专题五 高考冲刺"],
    ("人教版", "政治", "高一"): ["第一单元 中国特色社会主义", "第二单元 经济与社会",
                                "第三单元 政治与法治", "第四单元 哲学与文化"],
    ("人教版", "政治", "高二"): ["第一单元 当代国际政治与经济", "第二单元 法律与生活",
                                "第三单元 逻辑与思维", "第四单元 综合探究"],
    ("人教版", "政治", "高三"): ["专题一 经济生活", "专题二 政治生活", "专题三 文化生活",
                                "专题四 生活与哲学", "专题五 时政热点", "专题六 高考冲刺"],

    # ── 北师大版 · 初中数学（真实章节） ──
    ("北师大版", "数学", "初一"): ["第一章 丰富的图形世界", "第二章 有理数及其运算", "第三章 整式及其加减",
                                  "第四章 基本平面图形", "第五章 一元一次方程", "第六章 数据的收集与整理"],
    ("北师大版", "数学", "初二"): ["第一章 勾股定理", "第二章 实数", "第三章 位置与坐标",
                                  "第四章 一次函数", "第五章 二元一次方程组", "第六章 数据的分析"],
    ("北师大版", "数学", "初三"): ["第一章 特殊平行四边形", "第二章 一元二次方程", "第三章 概率的进一步认识",
                                  "第四章 图形的相似", "第五章 投影与视图", "第六章 反比例函数"],
    # 北师大版 高中数学（必修）
    ("北师大版", "数学", "高一"): ["第一章 集合", "第二章 函数", "第三章 指数函数与对数函数",
                                  "第四章 三角函数", "第五章 平面向量"],
    ("北师大版", "数学", "高二"): ["第一章 空间几何体", "第二章 解析几何初步", "第三章 统计",
                                  "第四章 概率", "第五章 数列"],
    ("北师大版", "数学", "高三"): ["专题一 函数与导数", "专题二 三角", "专题三 立体几何",
                                  "专题四 解析几何", "专题五 概率统计", "专题六 高考冲刺"],

    # ── 苏教版 · 初中数学（真实章节，七年级上） ──
    ("苏教版", "数学", "初一"): ["第1章 数学与我们同行", "第2章 有理数", "第3章 代数式",
                                "第4章 一元一次方程", "第5章 走进图形世界", "第6章 平面图形的认识"],
    ("苏教版", "数学", "初二"): ["第1章 全等三角形", "第2章 轴对称图形", "第3章 勾股定理",
                                "第4章 实数", "第5章 平面直角坐标系", "第6章 一次函数"],
    ("苏教版", "数学", "初三"): ["第1章 一元二次方程", "第2章 对称图形——圆", "第3章 数据的集中趋势和离散程度",
                                "第4章 等可能条件下的概率", "第5章 二次函数", "第6章 图形的相似"],
    # 苏教版 高中语文
    ("苏教版", "语文", "高一"): ["第一专题 向青春举杯", "第二专题 获得教养的途径", "第三专题 月是故乡明",
                                "第四专题 像山那样思考", "第五专题 寻觅文言津梁"],
    ("苏教版", "语文", "高二"): ["第一专题 祖国土", "第二专题 号角为你长鸣", "第三专题 文明的对话",
                                "第四专题 走进语言现场", "第五专题 综合阅读"],
    ("苏教版", "语文", "高三"): ["专题一 现代文阅读", "专题二 文言文阅读", "专题三 古代诗歌",
                                "专题四 写作", "专题五 高考冲刺"],

    # ── 外研版 · 初中英语（Module 结构） ──
    ("外研版", "英语", "初一"): ["Module 1 My classmates", "Module 2 My family", "Module 3 My school",
                                "Module 4 Healthy food", "Module 5 My school day", "Module 6 A trip to the zoo"],
    ("外研版", "英语", "初二"): ["Module 1 How to learn English", "Module 2 My hometown and my country",
                                "Module 3 Sports", "Module 4 Planes, ships and trains",
                                "Module 5 Cartoons", "Module 6 Animals in danger"],
    ("外研版", "英语", "初三"): ["Module 1 Wonders of the world", "Module 2 Public holidays",
                                "Module 3 Heroes", "Module 4 Home alone", "Module 5 Museums", "Module 6 Problems"],
    ("外研版", "英语", "高一"): ["Unit 1 A new start", "Unit 2 Exploring English", "Unit 3 On the move",
                                "Unit 4 Friends forever", "Unit 5 Into the wild", "Unit 6 At one with nature"],
    ("外研版", "英语", "高二"): ["Unit 1 Growing up", "Unit 2 Improving yourself", "Unit 3 Faster, higher, stronger",
                                "Unit 4 Meeting the muse", "Unit 5 What an adventure!", "Unit 6 Earth first"],
    ("外研版", "英语", "高三"): ["Module 1 阅读", "Module 2 完形", "Module 3 语法", "Module 4 写作",
                                "Module 5 听说", "Module 6 高考冲刺"],

    # ── 冀教版 · 初中数学（真实章节） ──
    ("冀教版", "数学", "初一"): ["第一章 有理数", "第二章 几何图形的初步认识", "第三章 代数式",
                                "第四章 整式的加减", "第五章 一元一次方程", "第六章 二元一次方程组"],
    ("冀教版", "数学", "初二"): ["第十三章 全等三角形", "第十四章 轴对称和中心对称", "第十五章 二次根式",
                                "第十六章 分式", "第十七章 特殊三角形", "第十八章 平面直角坐标系"],
    ("冀教版", "数学", "初三"): ["第二十六章 反比例函数", "第二十七章 相似", "第二十八章 圆",
                                "第二十九章 直线与圆的位置关系", "第三十章 二次函数", "第三十一章 随机事件的概率"],
}


def _units_for(edition: str, subject: str, grade: str):
    key = (edition, subject, grade)
    if key in REAL_UNITS:
        return REAL_UNITS[key]
    return GENERIC_UNITS.get(subject, ["第一单元 综合", "第二单元 综合", "第三单元 综合",
                                       "第四单元 综合", "第五单元 综合", "第六单元 综合"])


def seed():
    _ensure_textbook_catalogs_table()
    total = 0
    with engine.begin() as conn:
        for edition, plan in EDITION_PLAN.items():
            for level, subjects in plan.items():
                if level == "primary":
                    grades = PRIMARY_GRADES
                elif level == "junior":
                    grades = JUNIOR_GRADES
                else:
                    grades = SENIOR_GRADES
                for grade in grades:
                    for subject in subjects:
                        top_name = f"{edition}{subject}{grade}"
                        existing = conn.execute(
                            text(
                                "SELECT id FROM textbook_catalogs "
                                "WHERE subject=:s AND edition=:e AND grade=:g "
                                "AND level='edition' AND name=:n"
                            ),
                            {"s": subject, "e": edition, "g": grade, "n": top_name},
                        ).first()
                        if existing:
                            top_id = existing[0]
                        else:
                            top_id = gen_uuid()
                            conn.execute(
                                text(
                                    "INSERT INTO textbook_catalogs "
                                    "(id, name, subject, edition, grade, level, unit_index, parent_id) "
                                    "VALUES (:id, :n, :s, :e, :g, 'edition', NULL, NULL)"
                                ),
                                {"id": top_id, "n": top_name, "s": subject,
                                 "e": edition, "g": grade},
                            )
                            total += 1

                        for idx, name in enumerate(_units_for(edition, subject, grade), 1):
                            ex = conn.execute(
                                text(
                                    "SELECT id FROM textbook_catalogs "
                                    "WHERE subject=:s AND edition=:e AND parent_id=:p AND name=:n"
                                ),
                                {"s": subject, "e": edition, "p": top_id, "n": name},
                            ).first()
                            if ex:
                                continue
                            conn.execute(
                                text(
                                    "INSERT INTO textbook_catalogs "
                                    "(id, name, subject, edition, grade, level, unit_index, parent_id) "
                                    "VALUES (:id, :n, :s, :e, :g, 'unit', :idx, :p)"
                                ),
                                {"id": gen_uuid(), "n": name, "s": subject, "e": edition,
                                 "g": grade, "idx": idx, "p": top_id},
                            )
                            total += 1

    print(f"seed 完成：本次新增 {total} 行")
    with engine.connect() as conn:
        for edition in EDITION_PLAN:
            n = conn.execute(
                text("SELECT COUNT(*) FROM textbook_catalogs WHERE edition = :e"),
                {"e": edition},
            ).scalar()
            print(f"  {edition}: {n} 行")


if __name__ == "__main__":
    seed()
