import unittest

from PIL import Image, ImageDraw

from app.grading.pipeline import _draw_manual_result_mark, _draw_result_mark, _mark_check_x


class ManualMarkRenderingTests(unittest.TestCase):
    def test_unanswered_mark_draws_circle(self):
        """未作答画空心圆（2026-10-16 用户要求：没填答案不能什么都不标）。

        2026-10-19：圈必须画在答题区（bbox）内——右缘落点会圈到题干上。
        """
        image = Image.new("RGB", (1000, 600), "white")

        _draw_manual_result_mark(
            ImageDraw.Draw(image),
            image.width,
            image.height,
            {"bbox": [100, 100, 500, 300], "result": "未作答"},
        )

        colors = set(image.getdata())
        self.assertIn((255, 0, 0), colors)
        # 空心圆：中心应是白的（不是实心红点）
        self.assertEqual(image.getpixel((300, 200)), (255, 255, 255))
        # 圈落在答题区内：红像素不得越出 bbox（描边宽容差 8px）
        reds = [(px, py) for py in range(image.height) for px in range(image.width)
                if image.getpixel((px, py)) == (255, 0, 0)]
        self.assertTrue(reds)
        for px, py in reds:
            self.assertTrue(100 - 8 <= px <= 500 + 8 and 100 - 8 <= py <= 300 + 8,
                            f"红圈跑出答题区: ({px},{py})")

    def test_correct_mark_uses_the_smart_grading_red(self):
        image = Image.new("RGB", (1000, 600), "white")

        _draw_manual_result_mark(
            ImageDraw.Draw(image),
            image.width,
            image.height,
            {"bbox": [100, 100, 500, 300], "result": "对"},
        )

        colors = set(image.getdata())
        self.assertIn((255, 0, 0), colors)
        self.assertNotIn((220, 38, 38), colors)

    def test_pending_mark_draws_nothing(self):
        """待确认仍不画任何标记（交老师拍板，别被当成已判）。"""
        image = Image.new("RGB", (1000, 600), "white")

        _draw_manual_result_mark(
            ImageDraw.Draw(image),
            image.width,
            image.height,
            {"bbox": [100, 100, 500, 300], "result": "待确认"},
        )

        self.assertEqual(set(image.getdata()), {(255, 255, 255)})

    def test_unanswered_result_draws_circle(self):
        image = Image.new("RGB", (400, 200), "white")

        _draw_result_mark(
            ImageDraw.Draw(image),
            200,
            60,
            48,
            {"result": "未作答"},
            None,
            "#CC0000",
            "#FF0000",
            [(0, 0)],
            check_cross_scale=0.2,
        )

        self.assertIn((255, 0, 0), set(image.getdata()))

    def test_unanswered_circle_lands_inside_the_answer_bbox(self):
        """带 bbox 时空心圆画在答题区正中，不得落到右缘外的题干上。"""
        image = Image.new("RGB", (400, 200), "white")
        bbox = [80, 60, 180, 120]

        _draw_result_mark(
            ImageDraw.Draw(image),
            220,  # 旧右缘落点（框外）：圆不该用它
            60,
            48,
            {"result": "未作答", "bbox": bbox},
            None,
            "#CC0000",
            "#FF0000",
            [(0, 0)],
            check_cross_scale=0.2,
            bbox=bbox,
        )

        reds = [(px, py) for py in range(image.height) for px in range(image.width)
                if image.getpixel((px, py)) == (255, 0, 0)]
        self.assertTrue(reds)
        for px, py in reds:
            self.assertTrue(80 - 8 <= px <= 180 + 8 and 60 - 8 <= py <= 120 + 8,
                            f"红圈跑出答题区: ({px},{py})")
        # 旧落点（check_x=220 附近）必须是空白的
        self.assertEqual(image.getpixel((235, 90)), (255, 255, 255))

    def test_pending_result_draws_nothing(self):
        image = Image.new("RGB", (400, 200), "white")

        _draw_result_mark(
            ImageDraw.Draw(image),
            200,
            60,
            48,
            {"result": "待确认"},
            None,
            "#CC0000",
            "#FF0000",
            [(0, 0)],
            check_cross_scale=0.2,
        )

        self.assertEqual(set(image.getdata()), {(255, 255, 255)})


def test_reference_vlm_unanswered_slot_draws_circle(tmp_path):
    """参照批改留痕：未作答空也要画圈（2026-10-16），待确认仍不画。"""
    from app.grading.reference_vlm_grading import draw_reference_vlm_marks_and_save

    # PNG 源图 → 留痕输出也是 PNG（无损），JPEG 会把纯红糊成暗红导致断言误报
    src = tmp_path / "paper.png"
    Image.new("RGB", (1200, 800), "white").save(src)
    blocks = [
        {
            "baidu_correct_result": 3,
            "result": "未作答",
            "is_question": True,
            "bbox": [200, 300, 600, 360],
            "has_mark_anchor": True,
            "has_handwriting_location": False,
            "baidu_is_slot": True,
            "baidu_question_bbox": [150, 250, 900, 700],
            "index": 1,
            "sub_index": 1,
        },
        {
            "baidu_correct_result": 5,
            "result": "待确认",
            "is_question": True,
            "bbox": [200, 500, 600, 560],
            "has_mark_anchor": True,
            "has_handwriting_location": False,
            "baidu_is_slot": True,
            "baidu_question_bbox": [150, 450, 900, 700],
            "index": 2,
            "sub_index": 1,
        },
    ]
    _orig, ann_name, marks_name = draw_reference_vlm_marks_and_save(
        str(src), blocks, str(tmp_path), "stu"
    )
    ann_img = Image.open(tmp_path / ann_name).convert("RGB")
    assert (255, 0, 0) in set(ann_img.getdata()), "未作答应画出红圈"
    marks_img = Image.open(tmp_path / marks_name).convert("RGB")
    w_m, h_m = marks_img.size
    red_xy = [
        (px % w_m, px // w_m)
        for px, color in enumerate(marks_img.getdata())
        if color == (255, 0, 0)
    ]
    assert red_xy, "marks_only 里也应有未作答红圈"
    # 2026-10-19：红圈必须落在作答区 bbox 内（描边宽容差 8px），不圈到题干
    for px, py in red_xy:
        assert 200 - 8 <= px <= 600 + 8 and 300 - 8 <= py <= 360 + 8, f"红圈跑出答题区: ({px},{py})"


class MarkAnchorTests(unittest.TestCase):
    """√/× 的横坐标：中等宽度的作答区(slot)贴进右缘内侧，其余保持右缘外侧。"""

    def test_medium_slot_mark_lands_inside_the_answer_bbox(self):
        # font_size=48, check_cross_scale=0.2 → glyph_w = 36；宽120 在 [72, 126] 区间内
        x = _mark_check_x(
            {"baidu_is_slot": True}, 300, 420, 48, 0.2, 20, 28, 1675, 40
        )
        self.assertEqual(x, 420 - 36)

    def test_wide_slot_keeps_the_original_outside_anchor(self):
        # 宽607（整行作答区）超上限，仍用原公式，避免盖住整块手写
        x = _mark_check_x(
            {"baidu_is_slot": True}, 100, 707, 48, 0.2, 20, 28, 1675, 40
        )
        self.assertEqual(x, min(707 - 20 + 28, 1675 - 40 - int(48 * 0.4)))

    def test_non_slot_keeps_the_original_outside_anchor(self):
        # 题目级大块（无 baidu_is_slot）即使宽度落在区间内也不贴边
        x = _mark_check_x({}, 300, 420, 48, 0.2, 20, 28, 1675, 40)
        self.assertEqual(x, min(420 - 20 + 28, 1675 - 40 - int(48 * 0.4)))


if __name__ == "__main__":
    unittest.main()
