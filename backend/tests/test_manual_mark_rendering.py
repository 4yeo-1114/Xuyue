import unittest

from PIL import Image, ImageDraw

from app.grading.pipeline import _draw_manual_result_mark


class ManualMarkRenderingTests(unittest.TestCase):
    def test_unanswered_mark_surrounds_the_complete_answer_bbox(self):
        image = Image.new("RGB", (1000, 600), "white")
        bbox = [100, 100, 500, 300]

        _draw_manual_result_mark(
            ImageDraw.Draw(image),
            image.width,
            image.height,
            {"bbox": bbox, "result": "未作答"},
        )

        changed = [
            (x, y)
            for y in range(image.height)
            for x in range(image.width)
            if image.getpixel((x, y)) != (255, 255, 255)
        ]
        xs = [point[0] for point in changed]
        ys = [point[1] for point in changed]
        self.assertLess(min(xs), bbox[0])
        self.assertGreater(max(xs), bbox[2])
        self.assertLess(min(ys), bbox[1])
        self.assertGreater(max(ys), bbox[3])

    def test_correct_mark_uses_the_smart_grading_red(self):
        image = Image.new("RGB", (1000, 600), "white")

        _draw_manual_result_mark(
            ImageDraw.Draw(image),
            image.width,
            image.height,
            {"bbox": [100, 100, 500, 300], "result": "对"},
        )

        colors = set(image.getdata())
        self.assertIn((255, 68, 68), colors)
        self.assertNotIn((220, 38, 38), colors)


if __name__ == "__main__":
    unittest.main()
