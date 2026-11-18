# -*- coding: utf-8 -*-
"""配图出题（1026 口径：要图就画真图，要么就出没图的题）单元测试。"""
import base64

import pytest

from app.utils.figure_render import (
    FigureRenderError,
    eval_math_expr,
    process_question_figures,
    render_figure_data_url,
    render_figure_png,
)

PNG_SIG = b"\x89PNG\r\n\x1a\n"

FUNC_SPEC = {"kind": "function", "exprs": ["x^2-4*x+3"], "x_min": -1, "x_max": 5, "y_min": -2, "y_max": 10}
GEO_SPEC = {
    "kind": "geometry",
    "points": {"A": [0, 0], "B": [4, 0], "C": [2, 3.4]},
    "segments": [["A", "B"], ["B", "C"], ["C", "A"]],
    "angles": [{"vertex": "A", "p1": "B", "p2": "C", "label": "60°"}],
}
BAR_SPEC = {"kind": "bar", "categories": ["一月", "二月", "三月"], "values": [12, 20, 15]}
LINE_SPEC = {"kind": "line", "categories": ["一月", "二月", "三月"], "values": [12, 20, 15]}
PIE_SPEC = {"kind": "pie", "items": [["优", 30], ["良", 40], ["及格", 30]]}


class TestRenderKinds:
    @pytest.mark.parametrize("spec", [FUNC_SPEC, GEO_SPEC, BAR_SPEC, LINE_SPEC, PIE_SPEC])
    def test_all_kinds_render_png(self, spec):
        png = render_figure_png(spec)
        assert png[:8] == PNG_SIG
        assert len(png) > 1000

    def test_function_multi_curves_and_implicit_mult(self):
        png = render_figure_png({"kind": "function", "exprs": ["2x+1", "sin(x)"], "x_min": -3, "x_max": 3})
        assert png[:8] == PNG_SIG

    def test_geometry_shadow_circle_dashed(self):
        png = render_figure_png(
            {
                "kind": "geometry",
                "points": {"A": [0, 0], "B": [4, 0], "C": [4, 3], "D": [0, 3]},
                "segments": [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]],
                "dashed": [["A", "C"]],
                "circles": [{"center": "B", "r": 2.0}],
                "polygons": [{"points": ["A", "B", "C"], "fill": True}],
            }
        )
        assert png[:8] == PNG_SIG

    def test_bar_multi_series(self):
        png = render_figure_png(
            {"kind": "bar", "categories": ["甲", "乙"], "series": [[1, 2], [3, 4]], "series_labels": ["a", "b"]}
        )
        assert png[:8] == PNG_SIG

    def test_data_url_prefix(self):
        url = render_figure_data_url(FUNC_SPEC)
        assert url.startswith("data:image/png;base64,")
        assert base64.b64decode(url.split(",", 1)[1])[:8] == PNG_SIG


class TestBadSpecs:
    @pytest.mark.parametrize(
        "spec",
        [
            None,
            "not a dict",
            {"kind": "nope"},
            {"kind": "function"},  # 无表达式
            {"kind": "function", "exprs": ["x"]},  # 无 x 范围
            {"kind": "function", "exprs": ["x"], "x_min": 5, "x_max": 1},  # 范围反
            {"kind": "geometry", "points": {"A": [0, 0]}},  # 点不够
            {"kind": "geometry", "points": {"A": [0, 0], "B": [1, 1]}},  # 无任何线/圆
            {"kind": "bar", "categories": ["一"], "values": [1]},  # 类别 <2
            {"kind": "bar", "categories": ["一", "二"], "values": [1]},  # 长度不齐
            {"kind": "pie", "items": [["优", 30]]},
        ],
    )
    def test_bad_specs_raise(self, spec):
        with pytest.raises(FigureRenderError):
            render_figure_png(spec)

    def test_expression_whitelist(self):
        # 有害/越权表达式一律拒
        for bad in ["__import__('os')", "open('x')", "x if 1 else 2", "[1][0]", "lambda:1"]:
            with pytest.raises(FigureRenderError):
                eval_math_expr(bad, 0)

    def test_eval_basics(self):
        assert eval_math_expr("x^2-4*x+3", 1) == pytest.approx(0)
        assert eval_math_expr("2x+1", 2) == pytest.approx(5)
        assert eval_math_expr("(x+1)(x-1)", 2) == pytest.approx(3)
        import math

        assert eval_math_expr("1/x", 0) != eval_math_expr("1/x", 0)  # nan
        assert eval_math_expr("sin(pi/2)", 0) == pytest.approx(1)
        assert math.isnan(eval_math_expr("sqrt(x)", -1))


class TestProcessGate:
    def test_figure_question_rendered_and_kept(self):
        qs = [{"stem": "如图所示，求 AB 长。", "content": "", "figure": GEO_SPEC}]
        out = process_question_figures(qs)
        assert len(out) == 1
        assert out[0]["figure_img"].startswith("data:image/png;base64,")
        assert out[0]["figure"] == GEO_SPEC

    def test_ref_without_figure_dropped(self):
        qs = [{"stem": "如图所示，求面积。", "content": ""}]
        assert process_question_figures(qs) == []

    def test_clean_text_kept(self):
        qs = [{"stem": "若 |m|=2，求 m。", "content": ""}]
        out = process_question_figures(qs)
        assert len(out) == 1 and "figure_img" not in out[0]

    def test_bad_figure_with_ref_dropped(self):
        qs = [{"stem": "如图所示，求面积。", "content": "", "figure": {"kind": "geometry", "points": {"A": [0, 0]}}}]
        assert process_question_figures(qs) == []

    def test_bad_figure_without_ref_kept_stripped(self):
        qs = [{"stem": "求 1+1。", "content": "", "figure": {"kind": "nope"}}]
        out = process_question_figures(qs)
        assert len(out) == 1
        assert "figure" not in out[0] and "figure_img" not in out[0]

    def test_leading_ref_stripped_when_conditions_in_text(self):
        qs = [{"stem": "如图，在△ABC 中，AB=AC，∠A=40°，求 ∠B。", "content": ""}]
        out = process_question_figures(qs)
        assert len(out) == 1
        assert out[0]["stem"].startswith("在△ABC")

    def test_mixed_batch(self):
        qs = [
            {"stem": "如图所示的抛物线…", "content": "", "figure": FUNC_SPEC},
            {"stem": "如图所示，下列说法正确的是（ ）", "content": ""},
            {"stem": "计算：(-2)+3。", "content": ""},
        ]
        out = process_question_figures(qs)
        assert len(out) == 2
        assert out[0].get("figure_img") and "figure_img" not in out[1]


class TestWorksheetPdfEmbed:
    def test_pdf_with_figure_img(self):
        from app.utils.worksheet_pdf import build_worksheet_pdf

        url = render_figure_data_url(FUNC_SPEC)
        pdf = build_worksheet_pdf(
            title="配图测试",
            subject="数学",
            question_items=[
                {"type": "short_answer", "stem": "", "content": "如图所示，求顶点坐标。", "score": 8, "figure_img": url},
                {"type": "choice", "stem": "", "content": "无图纯文字题（ ）", "score": 3, "options": ["A项", "B项", "C项", "D项"]},
            ],
        )
        assert pdf[:5] == b"%PDF-"

    def test_pdf_without_figure_unchanged(self):
        from app.utils.worksheet_pdf import build_worksheet_pdf

        pdf = build_worksheet_pdf(
            title="无图测试",
            question_items=[{"type": "fill", "content": "1+1=＿＿", "score": 2}],
        )
        assert pdf[:5] == b"%PDF-"

    def test_broken_figure_img_ignored(self):
        from app.utils.worksheet_pdf import build_worksheet_pdf

        pdf = build_worksheet_pdf(
            title="坏图测试",
            question_items=[{"type": "fill", "content": "1+1=＿＿", "score": 2, "figure_img": "data:image/png;base64,!!!"}],
        )
        assert pdf[:5] == b"%PDF-"
