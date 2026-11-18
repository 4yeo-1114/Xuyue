import unittest
from unittest.mock import patch

from app.grading.wrong_annotations import (
    collect_wrong_question_groups,
    generate_wrong_annotations_for_blocks,
    normalize_wrong_annotations,
    question_key_of,
)


class NormalizeTests(unittest.TestCase):
    def test_normalize_filters_garbage_and_fills_defaults(self):
        raw = {
            "1": {"text": " 错因：看错单位 ", "source": "AI", "edited": False},
            "2": "not-a-dict",
            "": {"text": "x"},
            "3": {"text": "半对：步骤不全"},
        }
        out = normalize_wrong_annotations(raw)
        self.assertEqual(set(out), {"1", "3"})
        self.assertEqual(out["1"]["text"], "错因：看错单位")
        self.assertEqual(out["1"]["source"], "ai")
        self.assertFalse(out["1"]["edited"])
        self.assertEqual(out["3"]["source"], "manual")
        self.assertTrue(out["3"]["edited"])  # manual 默认视为老师手写
        self.assertIn("generated_at", out["3"])

    def test_normalize_empty_on_garbage_input(self):
        self.assertEqual(normalize_wrong_annotations(None), {})
        self.assertEqual(normalize_wrong_annotations([1, 2]), {})


class QuestionKeyTests(unittest.TestCase):
    def test_key_prefers_index_then_label_prefix_then_slot(self):
        self.assertEqual(question_key_of({"index": 12, "label": "第9题"}), "12")
        self.assertEqual(question_key_of({"label": "7(2)"}), "7")
        self.assertEqual(question_key_of({"label": "作文", "slot_id": "s3"}), "作文")
        self.assertEqual(question_key_of({"slot_id": "s3"}), "s3")
        self.assertEqual(question_key_of({"index": None, "label": "2(1)小问"}), "2")


class CollectGroupsTests(unittest.TestCase):
    def test_collects_only_wrong_and_partial(self):
        blocks = [
            {"index": 1, "result": "对", "student_answer": "A"},
            {"index": 2, "result": "错", "question_content": "Q2", "student_answer": "B"},
            {"index": 3, "status": "partial", "stem_text": "Q3", "answer_text": "C"},
            {"index": 4, "status": "unanswered"},
        ]
        groups = collect_wrong_question_groups(blocks)
        self.assertEqual(set(groups), {"2", "3"})
        self.assertEqual(groups["2"]["question_content"], "Q2")
        self.assertEqual(groups["2"]["result"], "错")
        # 手动卷字段映射：stem_text/answer_text → question_content/student_answer
        self.assertEqual(groups["3"]["question_content"], "Q3")
        self.assertEqual(groups["3"]["student_answer"], "C")
        self.assertEqual(groups["3"]["result"], "半对")

    def test_multi_slot_merges_and_partial_wins(self):
        blocks = [
            {"index": 5, "result": "错", "student_answer": "x", "comment": "不对"},
            {"index": 5, "result": "半对", "student_answer": "y", "comment": ""},
        ]
        groups = collect_wrong_question_groups(blocks)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups["5"]["result"], "半对")  # 半对优先，描述更准
        self.assertEqual(groups["5"]["comment"], "不对")


class GenerateTests(unittest.TestCase):
    def _patch_text(self, mapping):
        return patch(
            "app.grading.wrong_annotations.generate_wrong_annotation_text",
            side_effect=lambda **kw: mapping.get(kw.get("student_answer"), ""),
        )

    def test_skips_edited_and_manual_entries(self):
        blocks = [
            {"index": 1, "result": "错", "student_answer": "A"},
            {"index": 2, "result": "错", "student_answer": "B"},
            {"index": 3, "result": "错", "student_answer": "C"},
        ]
        existing = {
            "1": {"text": "老师改过", "source": "ai", "edited": True},
            "2": {"text": "老师手写", "source": "manual", "edited": True},
        }
        with self._patch_text({"A": "错因：不该覆盖", "B": "错因：不该覆盖", "C": "错因：新稿"}):
            generated = generate_wrong_annotations_for_blocks(blocks, existing=existing)
        self.assertEqual(set(generated), {"3"})
        self.assertEqual(generated["3"]["text"], "错因：新稿")
        self.assertEqual(generated["3"]["source"], "ai")
        self.assertFalse(generated["3"]["edited"])

    def test_only_keys_and_empty_existing_allows_overwrite(self):
        """老师点「重新生成」：only_keys 单题 + existing={} 覆盖旧稿。"""
        blocks = [
            {"index": 1, "result": "错", "student_answer": "A"},
            {"index": 2, "result": "错", "student_answer": "B"},
        ]
        with self._patch_text({"A": "错因：覆盖1", "B": "错因：覆盖2"}):
            generated = generate_wrong_annotations_for_blocks(
                blocks, existing={}, only_keys={"1"}
            )
        self.assertEqual(set(generated), {"1"})
        self.assertEqual(generated["1"]["text"], "错因：覆盖1")

    def test_generation_failure_falls_back_not_blank(self):
        """2026-10-27 保底：LLM/VL 全失败也不留空——错题必有批注（机器评语/通用话术）。"""
        blocks = [
            {"index": 1, "result": "错", "student_answer": "A", "comment": "计算错了"},
            {"index": 2, "result": "半对", "student_answer": "B"},
        ]
        with patch(
            "app.grading.wrong_annotations.generate_wrong_annotation_text",
            return_value="",
        ):
            generated = generate_wrong_annotations_for_blocks(blocks, existing={})
        self.assertEqual(set(generated), {"1", "2"})
        self.assertEqual(generated["1"]["text"], "错因：计算错了")
        self.assertTrue(generated["2"]["text"].startswith("半对："))
        for v in generated.values():
            self.assertTrue(v["text"].strip())

    def test_fill_missing_only_skips_existing_texts(self):
        """补齐模式：已有非空批注不重复生成，只补缺的（重试/改判后补齐路径）。"""
        blocks = [
            {"index": 1, "result": "错", "student_answer": "A"},
            {"index": 2, "result": "错", "student_answer": "B"},
        ]
        existing = {"1": {"text": "错因：已有", "source": "ai", "edited": False}}
        with self._patch_text({"A": "错因：不该覆盖", "B": "错因：补的新稿"}):
            generated = generate_wrong_annotations_for_blocks(
                blocks, existing=existing, fill_missing_only=True
            )
        self.assertEqual(set(generated), {"2"})
        self.assertEqual(generated["2"]["text"], "错因：补的新稿")


if __name__ == "__main__":
    unittest.main()
