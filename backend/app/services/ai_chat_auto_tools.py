# -*- coding: utf-8 -*-
"""AI 助教：问句模式识别（意图执行见 ai_chat_intent_queries）。"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.ai_chat_intent_queries import run_intent_queries


def extract_exam_hint_from_text(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"[「\"']([^「」\"']{2,30})[」\"'].*?(?:考试|测验|统考|月考|期中|期末)",
        r"(.{2,24}?)(?:这次|本场|此次|那场|哪次)?(?:的)?(?:考试|测验|月考|统考)(?:中|里|的)?",
        r"(期中|期末|单元|月考|模拟|联考)[^\s，,。?？]{0,12}",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        hint = (m.group(1) or "").strip()
        hint = re.sub(r"(最高|最低|平均|分数|得分|成绩|多少|是谁|哪一位|排名|名次).*$", "", hint).strip()
        hint = re.sub(r"^[0-9]{3,4}班?", "", hint).strip()
        if len(hint) >= 2 and hint not in {"这次", "那场", "哪次", "某次"}:
            return hint
    return ""


def looks_like_score_question(text: str) -> bool:
    if not text:
        return False
    from app.services.ai_chat_access import looks_like_grading_exam_stats_question

    if looks_like_grading_exam_stats_question(text):
        return True
    return bool(
        re.search(
            r"最高|最低|平均|均分|满分|多少分|得分|分数|考了多少|排第|前几名|谁最高|谁考得最好|"
            r"排名|名次|排行|成绩怎么样|成绩情况|分数情况",
            text,
        )
    )


def run_auto_tool_calls(db: Session, user_id: str, user_text: str) -> list[dict[str, Any]]:
    """兼容旧名：服务端按语义自动查数。"""
    return run_intent_queries(db, user_id, user_text)
