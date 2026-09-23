# -*- coding: utf-8 -*-
"""为 demo@grade.local 造「试卷生成」多知识点 + 题型模板演示数据（幂等，只动 demo 用户）。

背景：智能组卷（ExamGenPage）的「知识点多选」和「题型模板一键成卷」依赖
  - subject_units + knowledge_points（按 subject=「小学语文/初中数学」、semester=「三年级上册/七年级下册」规范）
  - exam_question_templates（type_name 用标准题型名：选择题/填空题/…）

此前云端 xuyue 库里的知识数据属于旧账号 aepnb@pgj.com，且用旧规范（「语文/2026上」），
demo@grade.local 名下为空 → 前端多选列表空。本脚本只删/建 demo 用户自己的数据，不动其他用户。

用法（在云端后端目录执行，自动读 .env）：
  /opt/gradebuddy_venv311/bin/python scripts/seed_exam_gen_demo_data.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.subject_unit import SubjectUnit  # noqa: E402
from app.models.knowledge_point import KnowledgePoint  # noqa: E402
from app.models.exam_question_template import ExamQuestionTemplate  # noqa: E402

# ── 知识点数据：{(subject, semester): [(单元名, [知识点名, ...]), ...]} ──
# 初中部分沿用前端 subjectConfigData.ts 的 mock 单元/知识点（七年级下册 / 物理八年级下册）。
KNOWLEDGE = {
    ("初中语文", "七年级下册"): [
        ("群星闪耀", ["人物描写方法", "细节描写的作用", "传记文学的特点"]),
        ("家国情怀", ["抒情方式", "意象的象征意义", "情感基调的把握"]),
        ("凡人小事", ["叙事线索的梳理", "人物形象的分析", "细节描写的品味", "作者情感的体悟"]),
        ("中华美德", ["文言文实词", "文言文虚词", "古诗文鉴赏"]),
        ("写景状物", ["说明顺序", "说明方法"]),
        ("科幻探险", ["想象的合理性", "情节构思技巧"]),
    ],
    ("初中数学", "七年级下册"): [
        ("整式的乘除", ["同底数幂的乘法", "幂的乘方与积的乘方", "整式的乘法"]),
        ("因式分解", ["提取公因式法", "公式法"]),
        ("分式", ["分式的基本性质", "分式的运算", "分式方程"]),
        ("平行线与相交线", ["平行线的性质与判定", "三角形的内角和"]),
        ("数据的收集与整理", ["统计图表", "平均数、中位数、众数"]),
    ],
    ("初中英语", "七年级下册"): [
        ("Daily Life", ["一般现在时", "一般过去时", "日常交际用语"]),
        ("Travel & Transport", ["现在进行时与过去进行时", "there be句型"]),
        ("School Life", ["一般将来时", "情态动词"]),
        ("Reading Skills", ["阅读理解策略", "词汇猜测技巧"]),
        ("Writing Workshop", ["英语写作框架", "连接词的使用"]),
    ],
    ("初中物理", "八年级下册"): [
        ("力", ["力的概念与表示", "弹力与弹簧测力计", "重力"]),
        ("运动和力", ["牛顿第一定律", "二力平衡", "摩擦力"]),
        ("压强", ["压强的概念", "液体压强", "大气压强"]),
        ("浮力", ["阿基米德原理", "物体的浮沉条件"]),
    ],
    ("初中历史", "七年级下册"): [
        ("隋唐时期", ["隋朝的统一与灭亡", "贞观之治与开元盛世", "唐朝的对外交往"]),
        ("宋元时期", ["北宋的政治", "宋元的经济与科技", "蒙古的兴起与元朝的建立"]),
        ("明清时期", ["明朝的统治", "清朝前期的兴盛", "闭关锁国政策"]),
        ("中国近代史开端", ["鸦片战争", "第二次鸦片战争"]),
    ],
    ("小学语文", "三年级上册"): [
        ("字词积累", ["多音字辨析", "形近字辨析", "近义词与反义词"]),
        ("句子训练", ["比喻句", "拟人句", "把字句与被字句"]),
        ("课文理解", ["概括段落大意", "体会文章情感"]),
    ],
    ("小学语文", "三年级下册"): [
        ("字词积累", ["词语搭配", "成语积累"]),
        ("阅读与理解", ["读短文回答问题", "找出中心句"]),
        ("习作表达", ["写话入门", "看图写话"]),
    ],
    ("小学数学", "三年级上册"): [
        ("万以内的加减法", ["三位数加减法", "加减法估算"]),
        ("乘除法", ["表内乘除法", "有余数的除法"]),
        ("图形与测量", ["周长计算", "长方形与正方形"]),
    ],
    ("小学数学", "三年级下册"): [
        ("除数是一位数的除法", ["口算除法", "笔算除法"]),
        ("两位数乘两位数", ["口算乘法", "笔算乘法"]),
        ("面积", ["面积单位", "长方形正方形面积"]),
        ("小数的初步认识", ["小数的读写", "小数加减法"]),
    ],
    ("小学英语", "三年级上册"): [
        ("字母与语音", ["26个字母", "字母发音"]),
        ("词汇", ["颜色词汇", "数字词汇", "文具词汇"]),
        ("日常用语", ["问候与介绍", "简单指令"]),
    ],
    ("小学英语", "三年级下册"): [
        ("词汇", ["动物词汇", "食物词汇", "身体部位词汇"]),
        ("句型", ["一般疑问句", "There be句型"]),
        ("日常用语", ["购物用语", "时间表达"]),
    ],
}

# ── 题型模板：{subject: [(type_name, default_count, default_score_each), ...]} ──
# type_name 必须命中前端 TYPE_NAME_TO_QUESTION_TYPE（选择题/填空题/判断题/简答题/作文/阅读理解/完形填空/计算题/应用题…）
TYPE_TEMPLATES = {
    "小学语文": [("选择题", 10, 2), ("填空题", 10, 2), ("阅读理解", 3, 10), ("简答题", 4, 5), ("作文", 1, 30)],
    "小学数学": [("选择题", 10, 3), ("填空题", 10, 2), ("判断题", 5, 1), ("计算题", 6, 5), ("应用题", 4, 8)],
    "小学英语": [("选择题", 10, 2), ("完形填空", 2, 10), ("阅读理解", 3, 10), ("简答题", 3, 5), ("作文", 1, 20)],
    "小学科学": [("选择题", 10, 3), ("填空题", 8, 2), ("判断题", 5, 1), ("简答题", 3, 8)],
    "初中语文": [("选择题", 10, 2), ("填空题", 10, 2), ("阅读理解", 3, 10), ("简答题", 4, 5), ("作文", 1, 30)],
    "初中数学": [("选择题", 10, 3), ("填空题", 10, 2), ("判断题", 5, 1), ("计算题", 6, 5), ("应用题", 4, 8)],
    "初中英语": [("选择题", 10, 2), ("完形填空", 2, 10), ("阅读理解", 3, 10), ("简答题", 3, 5), ("作文", 1, 20)],
    "初中物理": [("选择题", 10, 3), ("填空题", 8, 2), ("判断题", 5, 1), ("计算题", 3, 6), ("简答题", 3, 8)],
    "初中历史": [("选择题", 15, 2), ("填空题", 8, 2), ("判断题", 8, 1), ("简答题", 3, 8)],
}


def main() -> None:
    db = SessionLocal()
    try:
        demo = db.query(User).filter(User.email == "demo@grade.local").first()
        if not demo:
            raise SystemExit("未找到 demo@grade.local 用户，终止")
        uid = demo.id

        # 1. 幂等清理 demo 用户既有数据（先子表后父表，避免 FK 约束）
        db.query(KnowledgePoint).filter(KnowledgePoint.user_id == uid).delete()
        db.query(SubjectUnit).filter(SubjectUnit.user_id == uid).delete()
        db.query(ExamQuestionTemplate).filter(ExamQuestionTemplate.user_id == uid).delete()
        db.commit()

        # 2. 插入知识点数据
        unit_count = kp_count = 0
        for (subject, semester), units in KNOWLEDGE.items():
            for uidx, (unit_name, kp_names) in enumerate(units, start=1):
                u = SubjectUnit(
                    user_id=uid, subject=subject, semester=semester,
                    unit_index=uidx, name=unit_name, subtitle=None,
                )
                db.add(u)
                db.flush()  # 拿 u.id 供知识点引用
                unit_count += 1
                for kidx, kp_name in enumerate(kp_names, start=1):
                    db.add(KnowledgePoint(
                        user_id=uid, unit_id=u.id,
                        code=f"{uidx}.{kidx}", name=kp_name, level="理解",
                        mastery=70.0, is_weak=False, hours=1,
                    ))
                    kp_count += 1

        # 3. 插入题型模板
        tpl_count = 0
        for subject, rows in TYPE_TEMPLATES.items():
            for order, (type_name, count, score) in enumerate(rows):
                db.add(ExamQuestionTemplate(
                    user_id=uid, subject=subject, type_name=type_name,
                    default_count=count, default_score_each=score, sort_order=order,
                ))
                tpl_count += 1

        db.commit()

        print(f"== 完成：用户 {demo.email} (id={uid}) ==")
        print(f"   subject_units      : +{unit_count}")
        print(f"   knowledge_points   : +{kp_count}")
        print(f"   exam_question_templates: +{tpl_count}")

        # 4. 回读校验
        n_u = db.query(SubjectUnit).filter(SubjectUnit.user_id == uid).count()
        n_k = db.query(KnowledgePoint).filter(KnowledgePoint.user_id == uid).count()
        n_t = db.query(ExamQuestionTemplate).filter(ExamQuestionTemplate.user_id == uid).count()
        print(f"== 校验（demo 用户现存量）：units={n_u}, kps={n_k}, templates={n_t} ==")
    finally:
        db.close()


if __name__ == "__main__":
    main()
