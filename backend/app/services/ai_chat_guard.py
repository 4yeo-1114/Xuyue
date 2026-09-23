# -*- coding: utf-8 -*-
"""AI 助教：基于查询结果的服务端 Prompt 守卫，防止模型编造数据。"""

from __future__ import annotations

import json
from typing import Any


def format_prefetch_block(prefetch: list[dict[str, Any]]) -> str:
    if not prefetch:
        return (
            "\n\n【系统已为您核实】本次未查到任何相关记录。"
            "请根据该结果用自然语言告知用户未查询到数据，可建议核对班级编号、姓名或考试名称；"
            "禁止编造学生姓名、班级编号、考试分数、排名等任何信息。"
        )
    lines = [
        "\n\n【系统已为您核实】以下为工具查询到的真实数据。",
        "**硬性规则**：",
        "1. 只能使用下方 JSON 中出现的姓名、班级、分数、排名；禁止补充、推测或举例。",
        "2. 若 found 为 false 或 students/rankings 为空，须如实说明未查到，不得捏造。",
        "3. 问学生班级/学号/班干部/座位等时，只能使用 students[] 或 student 中的 class_name、"
        "student_number、cadre_role 等字段；同名多人时须分别说明各班记录，禁止张冠李戴。",
        "4. 若预查结果含 diagnosis_text、plan_text、report 等字段，须据此总结具体内容，"
        "禁止改讲操作流程或功能介绍。",
        "5. 问课堂讲评时，只能使用 session/sessions 中的 consolidation、pre_class、"
        "source_summary、post_feedback、exam_names；found 为 false 时须说明该班该学科尚未生成讲评，禁止编造。",
        "6. 用户问句中若指定了班级（requested_class_label / class_id），"
        "只能使用该班级 exams 中的数据，禁止引用其他班级的成绩或排名。",
        "7. 列出学生名单或排名时，只能使用 JSON 中的字段，不得增减。",
        "8. 用自然、完整的口语化中文回答，勿照搬固定模板，勿出现 MySQL、JSON、数据库、工具等技术用语。",
        "查询结果：\n",
        json.dumps(prefetch, ensure_ascii=False),
    ]
    return "".join(lines)
