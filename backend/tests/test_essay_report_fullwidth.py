# -*- coding: utf-8 -*-
"""11.11-7 作文报告「习作提升」全宽排版 + 段首缩进格式。

台账原话：「英语作文报告写作提升部分格式不正确，可不可以书写在蓝色框内」——
截图里那段文字被挤在窄栏里、右边大片空白（蓝框是老师画的期望区域）。
病根：折行按「字数」裁，英语半角字只算 1 个字宽，一行 46 个字母只占半幅宽。
"""

import textwrap

from app.grading.essay_grading import (
    _apply_rewrite_paragraph_indent,
    normalize_essay_result_text,
)
from app.grading.essay_pdf import (
    _chars_per_line,
    _display_units,
    _split_body_lines,
    _wrap_mixed_line,
)


def test_display_units_cjk_full_half_width():
    assert _display_units("中文") == 2.0
    assert _display_units("ab") == 1.0
    assert _display_units("中a") == 1.5
    # 全角标点按全角折算
    assert _display_units("，。") == 2.0


def test_english_paragraph_fills_full_width():
    # 200 个字母的老行为：一行 46 字母 ≈ 23 全角字宽 = 半幅窄栏
    para = (
        "The little girl walked slowly through the garden "
        "and found a beautiful butterfly sitting on a flower"
    ) * 2
    budget = _chars_per_line(515.0, 10.5)  # ≈46 全角字宽
    lines = _split_body_lines(para, width=budget)
    assert len(lines) >= 2
    for line in lines[:-1]:
        units = _display_units(line)
        # 不越界
        assert units <= budget + 1.0
        # 排满整幅宽（窄栏病：以前每行只有 ~23 个字宽）
        assert units >= budget * 0.8
    # 拉丁词不被从中间硬拆
    words = " ".join(lines).split()
    for w in words:
        assert w.strip(".,!?;:'\"") in para.replace(".", "").split()


def test_cjk_wrapping_unchanged():
    para = "汉字折行行为保持原样" * 10  # 100 个全角字
    budget = 46
    lines = _split_body_lines(para, width=budget)
    expected = textwrap.wrap(para, width=budget, break_long_words=True)
    assert lines == expected


def test_wrap_mixed_line_keeps_indent_on_first_line_only():
    para = "　　First line of the paragraph with many english words to wrap around the column width limit"
    budget = 46.0
    lines = _wrap_mixed_line(para, width=budget)
    assert lines[0].startswith("　　")
    for line in lines[1:]:
        assert not line.startswith(("　", " "))


def test_long_word_hard_split_no_overflow():
    para = "x" * 200
    lines = _wrap_mixed_line(para, width=46.0)
    assert all(_display_units(l) <= 46.0 for l in lines)
    assert "".join(lines) == para


def test_punctuation_line_start_still_fixed():
    para = "这是一个测试句号" * 10
    lines = _split_body_lines(para, width=10)
    # 折行后行首不应出现标点（避头标点仍在生效）
    for line in lines[1:]:
        assert not line or line[0] not in "，。！？；：、）】》」』"


def test_rewrite_indent_only_paragraph_starts():
    text = "First hard wrapped line\ncontinuation of the same paragraph\n\nSecond paragraph here"
    out = _apply_rewrite_paragraph_indent(text)
    lines = out.split("\n")
    assert lines[0] == "　　First hard wrapped line"
    # 续行不再缩进（11.11-7 格式修正）
    assert lines[1] == "continuation of the same paragraph"
    assert lines[2] == ""
    assert lines[3] == "　　Second paragraph here"


def test_normalize_essay_result_accepts_writing_improve_alias():
    text = "【作文得分】\n85分\n【写作提升】\nHard wrapped line\ncontinuation line\n【写作指导】\n指导内容"
    out = normalize_essay_result_text(text)
    assert "【写作提升】\n　　Hard wrapped line\ncontinuation line" in out
    assert "【写作指导】\n指导内容" in out


def test_normalize_essay_result_canonical_marker_still_works():
    text = "【习作提升】\n第一段内容\n\n第二段内容\n【写作指导】\n指导"
    out = normalize_essay_result_text(text)
    assert "【习作提升】\n　　第一段内容\n\n　　第二段内容" in out


def test_build_report_pdf_bytes_smoke_english():
    from app.grading.essay_pdf import EssayPdfItem, build_essay_report_pdf_bytes

    english_rewrite = "【习作提升】\n" + (
        "The little girl walked slowly through the garden "
        "and found a beautiful butterfly sitting on a flower. "
    ) * 12
    item = EssayPdfItem(name="english_essay_1.jpg", result=english_rewrite)
    data = build_essay_report_pdf_bytes(folder_name="test", items=[item])
    assert data[:5] == b"%PDF-"
