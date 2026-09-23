"""种子题组 —— B0 契约 §3.3 完整 21 题（对齐参考实现 seed_assessment_definition）。

题组标识：self_learning_survey_v1
domain：self_built_survey
grade_range：all（小学3年级+ / 初中 / 高中通用措辞）
consent_required：true
题目数：21 题（5 维 × 4-5 题）
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.assessment_definition import AssessmentDefinition

logger = logging.getLogger(__name__)

SEED_DEFINITION_NAME = "班级自我认识轻量问卷（自研）"
SEED_DEFINITION_DOMAIN = "self_built_survey"
SEED_DEFINITION_KEY = "self_learning_survey_v1"

SEED_QUESTIONS: list[dict] = [
    {"id": "ls_q1", "dim": "learning_style", "text": "学习新内容时，你更习惯哪种方式？",
     "options": [{"key": "a", "text": "先看老师演示或例题", "dim": "ls_watch_example"},
                 {"key": "b", "text": "自己先试着做一做", "dim": "ls_try_self"},
                 {"key": "c", "text": "边做边翻书查资料", "dim": "ls_mixed"}]},
    {"id": "ls_q2", "dim": "learning_style", "text": "记住新知识时，你更习惯怎么做？",
     "options": [{"key": "a", "text": "读几遍文字来记住", "dim": "ls_read"},
                 {"key": "b", "text": "听别人讲一遍记住", "dim": "ls_listen"},
                 {"key": "c", "text": "动手写一遍或做一遍记住", "dim": "ls_handson"}]},
    {"id": "ls_q3", "dim": "learning_style", "text": "遇到一道新题时，你通常先做什么？",
     "options": [{"key": "a", "text": "先看例题模仿做法", "dim": "ls_watch_example"},
                 {"key": "b", "text": "自己先想办法试试", "dim": "ls_try_self"},
                 {"key": "c", "text": "和同学讨论一下", "dim": "ls_discuss"}]},
    {"id": "ls_q4", "dim": "learning_style", "text": "小组讨论时，你更愿意怎么参与？",
     "options": [{"key": "a", "text": "先听别人讲，再提问", "dim": "ls_listen"},
                 {"key": "b", "text": "自己发言讲想法", "dim": "ls_discuss"},
                 {"key": "c", "text": "边听边记笔记", "dim": "ls_read"}]},
    {"id": "ls_q5", "dim": "learning_style", "text": "做手工或实验时，你更喜欢？",
     "options": [{"key": "a", "text": "照着步骤一步步来", "dim": "ls_watch_example"},
                 {"key": "b", "text": "自己琢磨新做法", "dim": "ls_try_self"},
                 {"key": "c", "text": "边做边改进", "dim": "ls_handson"}]},
    {"id": "int_q1", "dim": "interest", "text": "空闲时间，你更想做什么？",
     "options": [{"key": "a", "text": "动手做手工、画画或拼装", "dim": "int_making"},
                 {"key": "b", "text": "看书或想事情", "dim": "int_reading"},
                 {"key": "c", "text": "出去跑跳运动", "dim": "int_sports"},
                 {"key": "d", "text": "找朋友聊天一起玩", "dim": "int_social"}]},
    {"id": "int_q2", "dim": "interest", "text": "学校社团如果有这些，你最想选哪个？",
     "options": [{"key": "a", "text": "手工或科学实验社", "dim": "int_making"},
                 {"key": "b", "text": "阅读或写作社", "dim": "int_reading"},
                 {"key": "c", "text": "田径或球类社", "dim": "int_sports"},
                 {"key": "d", "text": "合唱或演讲社", "dim": "int_social"}]},
    {"id": "int_q3", "dim": "interest", "text": "周末你更愿意怎么安排？",
     "options": [{"key": "a", "text": "做一件小制作", "dim": "int_making"},
                 {"key": "b", "text": "读一本书", "dim": "int_reading"},
                 {"key": "c", "text": "去户外活动", "dim": "int_sports"},
                 {"key": "d", "text": "和家人朋友聚会", "dim": "int_social"}]},
    {"id": "int_q4", "dim": "interest", "text": "上课时，哪类课最能让你提起精神？",
     "options": [{"key": "a", "text": "美术、劳动或科学课", "dim": "int_making"},
                 {"key": "b", "text": "语文、阅读课", "dim": "int_reading"},
                 {"key": "c", "text": "体育课", "dim": "int_sports"},
                 {"key": "d", "text": "班会或交流多的课", "dim": "int_social"}]},
    {"id": "ss_q1", "dim": "social_style", "text": "班里组织活动时，你更常扮演什么角色？",
     "options": [{"key": "a", "text": "主动出主意、组织大家", "dim": "ss_organize"},
                 {"key": "b", "text": "配合大家、完成任务", "dim": "ss_participate"},
                 {"key": "c", "text": "有时组织、有时配合", "dim": "ss_mixed"}]},
    {"id": "ss_q2", "dim": "social_style", "text": "和同学一起做任务时，你更喜欢？",
     "options": [{"key": "a", "text": "带头分工、安排步骤", "dim": "ss_organize"},
                 {"key": "b", "text": "认真完成分到的部分", "dim": "ss_participate"},
                 {"key": "c", "text": "大家一起商量决定", "dim": "ss_mixed"}]},
    {"id": "ss_q3", "dim": "social_style", "text": "班里要选一个活动负责人，你会？",
     "options": [{"key": "a", "text": "主动报名", "dim": "ss_organize"},
                 {"key": "b", "text": "觉得别人做更合适", "dim": "ss_participate"},
                 {"key": "c", "text": "有人推选我就做", "dim": "ss_mixed"}]},
    {"id": "ss_q4", "dim": "social_style", "text": "参加集体游戏时，你更愿意？",
     "options": [{"key": "a", "text": "当队长给大家分工", "dim": "ss_organize"},
                 {"key": "b", "text": "认真玩好自己这一份", "dim": "ss_participate"},
                 {"key": "c", "text": "随大家一起玩", "dim": "ss_mixed"}]},
    {"id": "er_q1", "dim": "emotion_regulation", "text": "心情不好的时候，你更愿意？",
     "options": [{"key": "a", "text": "一个人待一会儿", "dim": "er_alone"},
                 {"key": "b", "text": "找人说一说", "dim": "er_talk"},
                 {"key": "c", "text": "做点别的事分散注意", "dim": "er_mixed"}]},
    {"id": "er_q2", "dim": "emotion_regulation", "text": "遇到委屈的事，你会？",
     "options": [{"key": "a", "text": "自己消化，慢慢就好", "dim": "er_alone"},
                 {"key": "b", "text": "告诉信任的人", "dim": "er_talk"},
                 {"key": "c", "text": "过一会儿就忘了", "dim": "er_mixed"}]},
    {"id": "er_q3", "dim": "emotion_regulation", "text": "考试没考好，你通常？",
     "options": [{"key": "a", "text": "自己安静想一想", "dim": "er_alone"},
                 {"key": "b", "text": "找老师或朋友聊聊", "dim": "er_talk"},
                 {"key": "c", "text": "去跑一跑、活动一下", "dim": "er_mixed"}]},
    {"id": "er_q4", "dim": "emotion_regulation", "text": "感到有压力时，哪种方式对你最有用？",
     "options": [{"key": "a", "text": "独处放松一下", "dim": "er_alone"},
                 {"key": "b", "text": "说出来心里好受些", "dim": "er_talk"},
                 {"key": "c", "text": "用兴趣爱好转移注意", "dim": "er_mixed"}]},
    {"id": "cc_q1", "dim": "challenge_coping", "text": "遇到很难的题目，你通常？",
     "options": [{"key": "a", "text": "坚持想办法解出来", "dim": "cc_persist"},
                 {"key": "b", "text": "先跳过，做完其他再回来", "dim": "cc_skip_then_back"},
                 {"key": "c", "text": "请老师或同学讲解", "dim": "cc_ask_help"}]},
    {"id": "cc_q2", "dim": "challenge_coping", "text": "任务做到一半发现很难，你会？",
     "options": [{"key": "a", "text": "坚持做完再休息", "dim": "cc_persist"},
                 {"key": "b", "text": "休息一下再继续", "dim": "cc_mixed"},
                 {"key": "c", "text": "换个任务，之后再说", "dim": "cc_skip_then_back"}]},
    {"id": "cc_q3", "dim": "challenge_coping", "text": "一道题做错了，你会？",
     "options": [{"key": "a", "text": "马上找原因改过来", "dim": "cc_persist"},
                 {"key": "b", "text": "对照答案看一遍", "dim": "cc_mixed"},
                 {"key": "c", "text": "记下来问别人", "dim": "cc_ask_help"}]},
    {"id": "cc_q4", "dim": "challenge_coping", "text": "新学的知识有点难懂，你会？",
     "options": [{"key": "a", "text": "反复看直到弄懂", "dim": "cc_persist"},
                 {"key": "b", "text": "先记下来慢慢理解", "dim": "cc_skip_then_back"},
                 {"key": "c", "text": "找老师或同学讲解", "dim": "cc_ask_help"}]},
]

SEED_DESCRIPTION = "本问卷帮助你了解自己的学习和交往习惯，没有对错，请按真实情况选择。"


def seed_assessment_definition(db: Session) -> dict:
    """幂等写入种子题组（B0 附录 A：先查再插）。

    判定键：(domain='self_built_survey', status='active', version=1) 已存在则不重复插入。
    返回 {"created": bool, "definition_id": str}。
    """
    existing = (
        db.query(AssessmentDefinition)
        .filter(
            AssessmentDefinition.domain == SEED_DEFINITION_DOMAIN,
            AssessmentDefinition.status == "active",
            AssessmentDefinition.version == 1,
        )
        .first()
    )
    if existing:
        return {"created": False, "definition_id": existing.id}

    definition = AssessmentDefinition(
        name=SEED_DEFINITION_NAME,
        domain=SEED_DEFINITION_DOMAIN,
        grade_range="all",
        version=1,
        status="active",
        consent_required=True,
        questions=SEED_QUESTIONS,
        description=SEED_DESCRIPTION,
    )
    db.add(definition)
    db.commit()
    db.refresh(definition)
    logger.info("[assessment] 种子题组已写入: %s (%s)", definition.id, SEED_DEFINITION_KEY)
    return {"created": True, "definition_id": definition.id}
