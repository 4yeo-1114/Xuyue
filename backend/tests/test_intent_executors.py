# -*- coding: utf-8 -*-
"""P2-4 批 3：INTENT_EXECUTORS 意图执行器注册表行为契约测试。

覆盖（与任务分条要求对应）：
- 完整性不变量：注册表 key 与 detect_intent_calls 能产出的全部静态 intent 一一对应
  （动态 query_* / list_grading_exams 除外，它们无法静态注册）。
- 已注册 intent 走注册表返回正常 payload；未知 intent 返回 fallback error dict（不 500）。
- query_* 前缀 intent 与 list_grading_exams 仍走 execute_grading_data_tool 原分派。
- 抽样 3 个执行器（intent_student_profile / intent_knowledge_weak / intent_question_bank）
  用 monkeypatch 注入依赖，逐参断言 args 解包与目标函数参数的映射（行为契约）。
"""

import re
from pathlib import Path

from app.services import ai_chat_intent_queries as intent_queries
from app.services.ai_chat_intent_queries import INTENT_EXECUTORS, execute_intent_call

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "ai_chat_intent_queries.py"
)
_SOURCE = _MODULE_PATH.read_text(encoding="utf-8")


def _detect_produced_intents() -> set[str]:
    """提取 detect_intent_calls 能产出的全部静态 intent。

    只取 add("intent_...") 的首参（真正会派发到 execute_intent_call 的意图），
    排除条件里引用的意图（intent_students_roster / intent_student_class /
    intent_grading_scores / intent_grading_exams / intent_grading_wrong —— 它们
    会被重路由到别的 intent，不会出现在 detect 产出的结果里）。
    """
    m = re.search(r"def detect_intent_calls\b.*?(?=\ndef )", _SOURCE, re.S)
    body = m.group(0) if m else ""
    return set(re.findall(r'add\(\s*"(intent_[a-z_0-9]+)"', body))


class TestCompleteness:
    def test_registry_covers_all_static_intents_detect_can_produce(self):
        produced = _detect_produced_intents()
        assert produced, "detect_intent_calls 未提取到任何静态 intent"
        assert produced - set(INTENT_EXECUTORS) == set(), (
            f"detect 能产出但未注册: {sorted(produced - set(INTENT_EXECUTORS))}"
        )
        assert set(INTENT_EXECUTORS) - produced == set(), (
            f"注册表含 detect 不会产出的冗余 key: {sorted(set(INTENT_EXECUTORS) - produced)}"
        )
        assert set(INTENT_EXECUTORS) == produced

    def test_all_executors_are_functions(self):
        assert INTENT_EXECUTORS, "INTENT_EXECUTORS 不应为空"
        for intent, fn in INTENT_EXECUTORS.items():
            assert callable(fn), f"{intent} 的执行器不可调用"
            assert fn.__name__.startswith("_exec_"), f"{intent} 的执行器命名不符合 _exec_ 前缀"


class TestDispatch:
    def test_registered_intent_returns_payload(self, monkeypatch):
        sentinel = {"success": True, "class_count": 5}
        monkeypatch.setattr(
            intent_queries,
            "intent_query_class_count",
            lambda db, user_id, grade=None: sentinel,
        )
        result = execute_intent_call(None, "u1", "intent_class_count", {"grade": "一年级"})
        assert result is sentinel

    def test_unknown_intent_returns_fallback_error(self):
        result = execute_intent_call(None, "u1", "not_a_real_intent", {})
        assert result == {"success": False, "error": "未知意图: not_a_real_intent"}

    def test_unknown_intent_does_not_raise(self):
        # 任意乱写的 intent 都不应 500
        for bogus in ("", "   ", "intent_nope", "foo", "query"):
            result = execute_intent_call(None, "u1", bogus, {})
            assert result.get("success") is False
            assert "未知意图" in result.get("error", "")

    def test_query_prefix_still_forwards_to_grading_tool(self, monkeypatch):
        sentinel = {"success": True, "rows": []}
        captured = {}

        def fake_tool(user_id, tool_name, args, db=None):
            captured.update(user_id=user_id, tool_name=tool_name, args=args, db=db)
            return sentinel

        monkeypatch.setattr(intent_queries, "execute_grading_data_tool", fake_tool)
        args = {"student_name": "小明"}
        result = execute_intent_call(None, "u1", "query_student_exam_records", args)
        assert result is sentinel
        assert captured == {
            "user_id": "u1",
            "tool_name": "query_student_exam_records",
            "args": args,
            "db": None,
        }

    def test_list_grading_exams_still_forwards_to_grading_tool(self, monkeypatch):
        sentinel = {"success": True, "total": 0}
        captured = {}

        def fake_tool(user_id, tool_name, args, db=None):
            captured["tool_name"] = tool_name
            return sentinel

        monkeypatch.setattr(intent_queries, "execute_grading_data_tool", fake_tool)
        assert execute_intent_call(None, "u1", "list_grading_exams", {}) is sentinel
        assert captured["tool_name"] == "list_grading_exams"

    def test_args_none_treated_as_empty_dict(self, monkeypatch):
        captured = {}

        def fake_count(db, user_id, grade=None):
            captured["grade"] = grade
            return {"success": True}

        monkeypatch.setattr(intent_queries, "intent_query_class_count", fake_count)
        execute_intent_call(None, "u1", "intent_class_count", None)
        assert captured["grade"] is None


class TestParamUnpacking:
    """抽样执行器：验证 args 解包正确映射到目标函数参数（行为契约逐参断言）。"""

    def test_intent_student_profile_unpacks_args(self, monkeypatch):
        captured = {}

        def fake_profile(
            db,
            user_id,
            *,
            student_name=None,
            student_number=None,
            class_id=None,
            class_name=None,
            user_text="",
        ):
            captured.update(
                student_name=student_name,
                student_number=student_number,
                class_id=class_id,
                class_name=class_name,
                user_text=user_text,
            )
            return {"success": True, "found": True}

        monkeypatch.setattr(intent_queries, "intent_query_student_profile", fake_profile)
        result = execute_intent_call(
            None,
            "u1",
            "intent_student_profile",
            {
                "student_name": "小明",
                "student_number": "20230101",
                "class_id": "c1",
                "class_name": "一班",
                "user_text": "小明学号多少",
            },
        )
        assert result == {"success": True, "found": True}
        assert captured == {
            "student_name": "小明",
            "student_number": "20230101",
            "class_id": "c1",
            "class_name": "一班",
            "user_text": "小明学号多少",
        }

    def test_intent_student_profile_user_text_str_coercion(self, monkeypatch):
        captured = {}

        def fake_profile(
            db,
            user_id,
            *,
            student_name=None,
            student_number=None,
            class_id=None,
            class_name=None,
            user_text="",
        ):
            captured.update(student_name=student_name, user_text=user_text)
            return {"success": True}

        monkeypatch.setattr(intent_queries, "intent_query_student_profile", fake_profile)
        # user_text 非 str 会被 str() 强制转换
        execute_intent_call(None, "u1", "intent_student_profile", {"user_text": 123})
        assert captured == {"student_name": None, "user_text": "123"}
        # user_text 缺省时为 ""
        execute_intent_call(None, "u1", "intent_student_profile", {"student_name": "小红"})
        assert captured == {"student_name": "小红", "user_text": ""}

    def test_intent_knowledge_weak_unpacks_args(self, monkeypatch):
        captured = {}

        def fake_kw(db, user_id, *, subject=None):
            captured["subject"] = subject
            return {"success": True, "rows": []}

        monkeypatch.setattr(intent_queries, "intent_query_knowledge_weak", fake_kw)
        result = execute_intent_call(None, "u1", "intent_knowledge_weak", {"subject": "数学"})
        assert result == {"success": True, "rows": []}
        assert captured["subject"] == "数学"
        # 缺省 subject → None
        execute_intent_call(None, "u1", "intent_knowledge_weak", {})
        assert captured["subject"] is None

    def test_intent_question_bank_unpacks_args(self, monkeypatch):
        captured = {}

        def fake_qb(user_id, *, subject=None, grade=None):
            captured.update(subject=subject, grade=grade)
            return {"success": True, "rows": [], "row_count": 0}

        monkeypatch.setattr(intent_queries, "intent_query_asset_question_bank", fake_qb)
        result = execute_intent_call(
            None, "u1", "intent_question_bank", {"subject": "数学", "grade": "初中"}
        )
        assert result == {"success": True, "rows": [], "row_count": 0}
        assert captured == {"subject": "数学", "grade": "初中"}
        # 缺省 subject / grade → None
        execute_intent_call(None, "u1", "intent_question_bank", {})
        assert captured == {"subject": None, "grade": None}
