import os
import tempfile
import unittest

from PIL import Image, ImageDraw

from app.grading.form_guard import (
    EMPTY_INK_RATIO,
    SUSPICIOUS_INK_RATIO,
    apply_form_guard,
    ink_ratio,
)


def _save(img: Image.Image) -> str:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    return path


class InkRatioTests(unittest.TestCase):
    def test_white_crop_has_zero_ink(self):
        img = Image.new("L", (400, 200), 255)
        self.assertLess(ink_ratio(img, [50, 50, 350, 150]), EMPTY_INK_RATIO)

    def test_handwritten_stroke_counts_as_ink(self):
        img = Image.new("L", (400, 200), 255)
        d = ImageDraw.Draw(img)
        d.line([(60, 100), (340, 100)], fill=0, width=6)
        self.assertGreater(ink_ratio(img, [50, 50, 350, 150]), SUSPICIOUS_INK_RATIO)

    def test_ink_outside_bbox_is_ignored(self):
        img = Image.new("L", (400, 200), 255)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 30, 30], fill=0)  # 笔迹在 bbox 外
        self.assertLess(ink_ratio(img, [100, 100, 300, 180]), EMPTY_INK_RATIO)


class FormGuardStrongTests(unittest.TestCase):
    def test_empty_slot_wrong_becomes_unanswered(self):
        """强矛盾：空作答区无笔迹却被判错 → 自动降级未作答并清评语。"""
        img_path = _save(Image.new("L", (400, 200), 255))
        try:
            blocks = [
                {
                    "index": 2,
                    "sub_index": 2,
                    "baidu_is_slot": True,
                    "bbox": [50, 50, 350, 150],
                    "result": "错",
                    "comment": "茄子不属于同一类",
                    "baidu_correct_result": 2,
                }
            ]
            changes = apply_form_guard(img_path, blocks)
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["action"], "downgraded")
            self.assertEqual(blocks[0]["result"], "未作答")
            self.assertEqual(blocks[0]["comment"], "")
            self.assertIsNone(blocks[0]["partial_ratio"])
            self.assertEqual(blocks[0]["baidu_correct_result"], 3)
            self.assertEqual(blocks[0]["form_guard"]["action"], "downgraded")
            self.assertEqual(blocks[0]["form_guard"]["was_result"], "错")
        finally:
            os.unlink(img_path)

    def test_empty_slot_partial_with_ratio_label_downgraded(self):
        """「半对（0.6）」展示形态的块同样会被强矛盾降级。"""
        img_path = _save(Image.new("L", (400, 200), 255))
        try:
            blocks = [
                {
                    "index": 1,
                    "sub_index": 1,
                    "baidu_is_slot": True,
                    "bbox": [50, 50, 350, 150],
                    "result": "半对（0.6）",
                    "partial_ratio": 0.6,
                    "comment": "部分正确",
                }
            ]
            changes = apply_form_guard(img_path, blocks)
            self.assertEqual(changes[0]["action"], "downgraded")
            self.assertEqual(blocks[0]["result"], "未作答")
            self.assertIsNone(blocks[0]["partial_ratio"])
        finally:
            os.unlink(img_path)

    def test_inked_correct_block_untouched(self):
        """有笔迹的正确块不动。"""
        img = Image.new("L", (400, 200), 255)
        ImageDraw.Draw(img).line([(60, 100), (340, 100)], fill=0, width=6)
        img_path = _save(img)
        try:
            blocks = [
                {
                    "index": 1,
                    "sub_index": 1,
                    "baidu_is_slot": True,
                    "bbox": [50, 50, 350, 150],
                    "result": "对",
                    "comment": "答案正确",
                }
            ]
            changes = apply_form_guard(img_path, blocks)
            self.assertEqual(changes, [])
            self.assertEqual(blocks[0]["result"], "对")
            self.assertNotIn("form_guard", blocks[0])
        finally:
            os.unlink(img_path)


class FormGuardWeakTests(unittest.TestCase):
    def test_unanswered_with_ink_only_flagged(self):
        """弱矛盾：有笔迹却被判未作答 → 只标 suspicious，不改判。"""
        img = Image.new("L", (400, 200), 255)
        ImageDraw.Draw(img).line([(60, 100), (340, 100)], fill=0, width=6)
        img_path = _save(img)
        try:
            blocks = [
                {
                    "index": 3,
                    "sub_index": 1,
                    "baidu_is_slot": True,
                    "bbox": [50, 50, 350, 150],
                    "result": "未作答",
                    "comment": "",
                }
            ]
            changes = apply_form_guard(img_path, blocks)
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["action"], "flagged")
            self.assertEqual(blocks[0]["result"], "未作答")  # 不改判
            self.assertTrue(blocks[0]["form_guard"]["suspicious"])
            self.assertEqual(blocks[0]["form_guard"]["reason"], "有笔迹判未作答")
        finally:
            os.unlink(img_path)

    def test_wrong_without_comment_only_flagged(self):
        """弱矛盾：判错却无理由 → 只标 suspicious，不改判。"""
        img = Image.new("L", (400, 200), 255)
        ImageDraw.Draw(img).line([(60, 100), (340, 100)], fill=0, width=6)
        img_path = _save(img)
        try:
            blocks = [
                {
                    "index": 4,
                    "sub_index": 1,
                    "baidu_is_slot": True,
                    "bbox": [50, 50, 350, 150],
                    "result": "错",
                    "comment": "  ",
                }
            ]
            changes = apply_form_guard(img_path, blocks)
            self.assertEqual(changes[0]["action"], "flagged")
            self.assertEqual(blocks[0]["result"], "错")
            self.assertEqual(blocks[0]["form_guard"]["reason"], "判错无理由")
        finally:
            os.unlink(img_path)


class FormGuardScopeTests(unittest.TestCase):
    def test_non_slot_question_block_skipped(self):
        """题干大块（questionArea 含印刷内容）跳过 ink 检查，空也不降级。"""
        img_path = _save(Image.new("L", (400, 200), 255))
        try:
            blocks = [
                {
                    "index": 5,
                    "sub_index": 1,
                    "baidu_is_slot": False,
                    "bbox": [20, 20, 380, 180],
                    "result": "错",
                    "comment": "",
                }
            ]
            changes = apply_form_guard(img_path, blocks)
            self.assertEqual(changes, [])
            self.assertEqual(blocks[0]["result"], "错")
        finally:
            os.unlink(img_path)

    def test_reference_vlm_answer_bbox_counts_as_slot(self):
        """reference_vlm 的作答区块（有 reference_vlm_answer_bbox）参与检查。"""
        img_path = _save(Image.new("L", (400, 200), 255))
        try:
            blocks = [
                {
                    "index": 1,
                    "sub_index": 1,
                    "baidu_is_slot": False,
                    "has_handwriting_location": True,
                    "reference_vlm_answer_bbox": [50, 50, 350, 150],
                    "bbox": [10, 10, 390, 190],
                    "result": "对",
                    "comment": "答案正确",
                }
            ]
            changes = apply_form_guard(img_path, blocks)
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["action"], "downgraded")
        finally:
            os.unlink(img_path)

    def test_missing_image_is_noop(self):
        blocks = [{"index": 1, "sub_index": 1, "baidu_is_slot": True, "bbox": [0, 0, 10, 10], "result": "错", "comment": ""}]
        self.assertEqual(apply_form_guard("Z:\\not\\exist.png", blocks), [])
        self.assertEqual(blocks[0]["result"], "错")

    def test_empty_blocks_is_noop(self):
        self.assertEqual(apply_form_guard("whatever", []), [])


if __name__ == "__main__":
    unittest.main()
