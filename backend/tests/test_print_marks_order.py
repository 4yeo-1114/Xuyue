# -*- coding: utf-8 -*-
"""打印留痕链路回归测试：双面排序、每人 P1/P2 不串、待确认留痕可见。

对应 2026-11-17 用户反馈：
1. 打印留痕数字顺序与页面显示不一致（38 38 28 36 32 36 → 38 28 38 36 32）
2. 每个学生 P1/P2 打印出来是相反的
3. 选择题「待确认」在留痕图上没有任何痕迹，看起来像漏批
"""
from __future__ import annotations

import pytest
from PIL import Image

import app.grading.print_marks as pm
import app.grading.pipeline as pipeline


# ── 1. 不跨学生配对 ────────────────────────────────────────────────────


def _base_of(p: str) -> str:
    return pm._student_base_from_marks_filename(p)


def test_duplex_job_paths_never_pairs_different_students():
    paths = [
        "marks_only_essay_cls_x_A_1.jpg",
        "marks_only_essay_cls_x_A_2.jpg",
        "marks_only_essay_cls_x_B_1.jpg",
        "marks_only_essay_cls_x_B_2.jpg",
    ]
    job = pm._duplex_job_paths(paths)
    for i in range(0, len(job) - 1, 2):
        assert _base_of(job[i]) == _base_of(job[i + 1]), f"第{i//2+1}张纸混了两个学生: {job[i:i+2]}"


def test_duplex_job_paths_keeps_student_order():
    """学生出现顺序不能被页码排序打乱（这会导致打印分数顺序与页面不一致）。"""
    paths = [
        "marks_only_essay_cls_x_A_1.jpg",
        "marks_only_essay_cls_x_A_2.jpg",
        "marks_only_essay_cls_x_B_1.jpg",
        "marks_only_essay_cls_x_B_2.jpg",
        "marks_only_essay_cls_x_C_1.jpg",
    ]
    job = pm._duplex_job_paths(paths)
    # 去重后学生顺序必须保持 A、B、C（每人内部可对调，但学生之间不能交叉）
    deduped = []
    for p in job:
        base = _base_of(p)
        if not deduped or deduped[-1] != base:
            deduped.append(base)
    assert [b.rsplit("_", 1)[-1] for b in deduped] == ["A", "B", "C"], f"学生顺序被打乱: {deduped}"


def test_duplex_job_paths_reverses_within_student_only():
    paths = ["marks_only_essay_cls_x_A_1.jpg", "marks_only_essay_cls_x_A_2.jpg"]
    job = pm._duplex_job_paths(paths)
    # 同一学生两页：送打顺序应为 P2、P1（反顺序逐对对调）
    assert [pm._page_no_from_marks_filename(p) for p in job] == [2, 1]


def test_duplex_swap_can_be_disabled(monkeypatch):
    monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", "0")
    paths = ["marks_only_essay_cls_x_A_1.jpg", "marks_only_essay_cls_x_A_2.jpg"]
    job = pm._duplex_job_paths(paths)
    assert [pm._page_no_from_marks_filename(p) for p in job] == [1, 2]


def test_duplex_submission_paths_same_rules():
    paths = [
        "marks_only_essay_cls_x_A_1.jpg",
        "marks_only_essay_cls_x_A_2.jpg",
        "marks_only_essay_cls_x_B_1.jpg",
        "marks_only_essay_cls_x_B_2.jpg",
    ]
    out = pm.duplex_submission_paths(paths)
    assert len(out) == 4
    for i in range(0, 4, 2):
        assert _base_of(out[i]) == _base_of(out[i + 1])


def test_group_by_student_handles_interleaved_input():
    """前端按「全部 P1 再全部 P2」提交时，也要重组回学生块。"""
    paths = [
        "marks_only_essay_cls_x_A_1.jpg",
        "marks_only_essay_cls_x_B_1.jpg",
        "marks_only_essay_cls_x_A_2.jpg",
        "marks_only_essay_cls_x_B_2.jpg",
    ]
    grouped = pm._group_by_student(paths)
    assert [pm._page_no_from_marks_filename(p) for p in grouped] == [1, 2, 1, 2]
    assert _base_of(grouped[0]) == _base_of(grouped[1])


def test_single_page_students_keep_input_order():
    paths = [f"marks_only_essay_cls_x_S{i}_img.jpg" for i in range(1, 7)]
    assert pm._group_by_student(paths) == paths


# ── 2. 待确认必须有可见痕迹 ─────────────────────────────────────────────


def _red_pixels(img: Image.Image) -> int:
    return sum(1 for px in img.convert("RGB").getdata() if px[0] > 150 and px[1] < 120 and px[2] < 120)


@pytest.mark.parametrize("result", ["对", "错", "未作答", "待确认", ""])
def test_every_status_leaves_a_visible_mark(tmp_path, result):
    src = tmp_path / "paper.jpg"
    Image.new("RGB", (800, 1000), "white").save(src)
    blocks = [{"is_question": True, "bbox": [100, 200, 300, 260], "result": result}]
    name = pipeline.draw_marks_only_and_save(str(src), blocks, str(tmp_path), f"t_{result or 'empty'}")
    img = Image.open(tmp_path / name)
    # 覆盖整个作答区及其右侧落点：√/×/? 画在右缘，○ 画在正中
    region = img.crop((90, 190, 420, 300))
    assert _red_pixels(region) > 20, f"result={result!r} 在留痕图上没有任何红色痕迹（老师会以为漏批）"


def test_pending_mark_differs_from_cross(tmp_path):
    """「待确认」画的是问号，不能与「错」的 × 混淆。"""
    src = tmp_path / "paper.jpg"
    Image.new("RGB", (800, 1000), "white").save(src)
    marks = {}
    for result in ("错", "待确认"):
        blocks = [{"is_question": True, "bbox": [100, 200, 300, 260], "result": result}]
        name = pipeline.draw_marks_only_and_save(str(src), blocks, str(tmp_path), f"d_{result}")
        marks[result] = pipeline._red_signature if False else None
        marks[result] = Image.open(tmp_path / name).crop((280, 180, 400, 300)).tobytes()
    assert marks["错"] != marks["待确认"], "待确认与错画成了同一个符号"


def test_manual_style_pending_also_visible(tmp_path):
    """自主阅卷（manual_style）路径同样要画问号。"""
    src = tmp_path / "paper.jpg"
    Image.new("RGB", (800, 1000), "white").save(src)
    blocks = [{"is_question": True, "bbox": [100, 200, 300, 260], "result": "待确认"}]
    name = pipeline.draw_marks_only_and_save(
        str(src), blocks, str(tmp_path), "m", manual_style=True
    )
    img = Image.open(tmp_path / name)
    assert _red_pixels(img.crop((280, 180, 400, 300))) > 20


# ── 3. 真实留痕文件名（_wa 变体后缀）解析 ───────────────────────────────
#
# 线上真实文件名形如：
#   marks_only_ref_cls_<uuid>__18班英语训练七_刘依璇_1_wa.jpg
# 旧 bug：页码正则 `_(\d+)$` 遇到末尾的 `_wa` 匹配不到 → 页码恒为 1、
# 同一学生的 P1/P2 被当成两个学生 → 双面配对跨学生、每人的 P1/P2 相反。

_CLS = "b9000000-0000-4000-8000-000000000018"
_REF_BASE = f"ref_cls_{_CLS}__18班英语训练七"


def _marks_wa(name: str, page: int, prefix: str = "marks_only_") -> str:
    return f"{prefix}{_REF_BASE}_{name}_{page}_wa.jpg"


@pytest.mark.parametrize(
    "filename, expected_page",
    [
        (_marks_wa("刘依璇", 1), 1),
        (_marks_wa("刘依璇", 2), 2),
    ],
)
def test_wa_page_no_from_real_filename(filename, expected_page):
    assert pm._page_no_from_marks_filename(filename) == expected_page


def test_wa_pages_share_student_base():
    """同一学生的 _1_wa 与 _2_wa 必须归到同一个学生分组键。"""
    b1 = pm._student_base_from_marks_filename(_marks_wa("刘依璇", 1))
    b2 = pm._student_base_from_marks_filename(_marks_wa("刘依璇", 2))
    assert b1 == b2, f"同一学生 P1/P2 被拆成两个学生: {b1!r} != {b2!r}"
    assert b1 == f"{_REF_BASE}_刘依璇"
    # 末尾页码被剥掉，变体后缀 _wa 也不进入分组键
    assert not b1.endswith("_1") and not b1.endswith("_wa")


def test_wa_different_students_different_base():
    b1 = pm._student_base_from_marks_filename(_marks_wa("刘依璇", 1))
    b2 = pm._student_base_from_marks_filename(_marks_wa("张三", 1))
    assert b1 != b2


def test_annotated_variant_matches_marks_only_page_and_base():
    """预览变体 annotated_ 与 marks_only_ 是同一页、同一学生：
    二者经 _marks_stem 剥前缀后 base 完全一致（不只是"可以不同"），
    关键断言：页码解析不能被前缀/变体后缀干扰。"""
    mo = _marks_wa("刘依璇", 2, prefix="marks_only_")
    an = _marks_wa("刘依璇", 2, prefix="annotated_")
    assert pm._page_no_from_marks_filename(mo) == 2
    assert pm._page_no_from_marks_filename(an) == 2
    assert pm._student_base_from_marks_filename(mo) == pm._student_base_from_marks_filename(an)


def test_marks_stem_strips_prefix_and_variant_suffix():
    p = _marks_wa("刘依璇", 2, prefix="annotated_")
    assert pm._marks_stem(p) == f"{_REF_BASE}_刘依璇_2"


# ── 4. _duplex_job_paths：每张纸只装同一学生（真实 _wa 文件名） ──────────


def _six_students_two_pages() -> list:
    names = ["刘依璇", "张三", "李四", "王五", "赵六", "钱七"]
    paths: list = []
    for name in names:
        paths.append(_marks_wa(name, 1))
        paths.append(_marks_wa(name, 2))
    return paths


def _paper_pairs(job: list) -> list:
    return [job[i : i + 2] for i in range(0, len(job) - len(job) % 2, 2)]


def test_duplex_job_paths_wa_each_sheet_single_student(monkeypatch):
    monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", "1")
    paths = _six_students_two_pages()
    job = pm._duplex_job_paths(paths)
    assert len(job) == len(paths)
    for idx, pair in enumerate(_paper_pairs(job)):
        assert _base_of(pair[0]) == _base_of(pair[1]), (
            f"第{idx + 1}张纸混了两个学生: {pair}"
        )
        # 反顺序送打：每张纸送打顺序是 [P2, P1]
        assert [pm._page_no_from_marks_filename(p) for p in pair] == [2, 1], pair


def test_duplex_job_paths_wa_student_order_matches_input():
    paths = _six_students_two_pages()
    job = pm._duplex_job_paths(paths)
    got = []
    for p in job:
        base = _base_of(p)
        if not got or got[-1] != base:
            got.append(base)
    want = []
    for p in paths:
        base = _base_of(p)
        if not want or want[-1] != base:
            want.append(base)
    assert got == want, f"学生顺序被打乱: {got}"


def test_duplex_job_paths_wa_swap_disabled_pairs_p1_then_p2(monkeypatch):
    monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", "0")
    paths = _six_students_two_pages()
    job = pm._duplex_job_paths(paths)
    assert len(job) == len(paths)
    for pair in _paper_pairs(job):
        assert _base_of(pair[0]) == _base_of(pair[1])
        assert [pm._page_no_from_marks_filename(p) for p in pair] == [1, 2]
    assert job == paths


def test_duplex_job_paths_wa_interleaved_input_regroups(monkeypatch):
    """前端按「全部 P1 再全部 P2」提交真实 _wa 文件名时也要重组回学生块。"""
    monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", "0")
    names = ["刘依璇", "张三", "李四"]
    paths = [_marks_wa(n, 1) for n in names] + [_marks_wa(n, 2) for n in names]
    job = pm._duplex_job_paths(paths)
    want = []
    for n in names:
        want.extend([_marks_wa(n, 1), _marks_wa(n, 2)])
    assert job == want


# ── 5. 单页学生（_img 结尾、无页码）不报错 ──────────────────────────────


@pytest.mark.parametrize("count", [5, 6, 7])
def test_duplex_job_paths_single_page_no_index_error(count):
    paths = [f"marks_only_essay_cls_x_S{i}_img.jpg" for i in range(1, count + 1)]
    job = pm._duplex_job_paths(paths)  # 奇偶都不能 IndexError
    assert job == paths
    assert all(pm._page_no_from_marks_filename(p) == 1 for p in job)
    # 单页学生的分组键互不相同（_img 不是页码，保留在 base 里区分学生）
    bases = [pm._student_base_from_marks_filename(p) for p in job]
    assert len(set(bases)) == count


def test_duplex_job_paths_single_page_wa_files_keep_order():
    """单页学生也走 _wa 形态（没有 _数字 页码后缀）。"""
    paths = [f"marks_only_{_REF_BASE}_S{i}_wa.jpg" for i in range(1, 6)]
    job = pm._duplex_job_paths(paths)
    assert job == paths
    assert all(pm._page_no_from_marks_filename(p) == 1 for p in job)


# ── 6. duplex_submission_paths 与 _duplex_job_paths 规则一致 ─────────────


def test_duplex_submission_paths_keep_p1_before_p2(monkeypatch):
    """PDF/云端打印按页序出纸，页面顺序必须是 P1、P2（2026-11-18 客户反馈）。

    不能套用 GDI 直打才需要的「反顺序对调」，否则 P2 会印到正面。
    """
    for swap in ("1", "0"):
        monkeypatch.setenv("GRADING_DUPLEX_SWAP_SIDES", swap)
        paths = _six_students_two_pages()
        out = pm.duplex_submission_paths(paths)
        assert [pm._page_no_from_marks_filename(p) for p in out] == [1, 2] * 6
        for pair in _paper_pairs(out):
            assert _base_of(pair[0]) == _base_of(pair[1]), "同一张纸上必须是同一个学生"


# ── 7. 兼容旧形态：无 _wa 后缀 ──────────────────────────────────────────


def test_legacy_filename_without_wa_still_parsed():
    p1 = "marks_only_essay_cls_1144_张三_1.jpg"
    p2 = "marks_only_essay_cls_1144_张三_2.jpg"
    assert pm._page_no_from_marks_filename(p1) == 1
    assert pm._page_no_from_marks_filename(p2) == 2
    assert pm._student_base_from_marks_filename(p1) == "essay_cls_1144_张三"
    assert pm._student_base_from_marks_filename(p1) == pm._student_base_from_marks_filename(p2)


def test_legacy_and_wa_forms_group_together():
    """同一学生在旧形态与 _wa 形态混用（如已重打印某一页）时仍归为同一学生分组键。"""
    legacy = "marks_only_essay_cls_1144_张三_1.jpg"
    wa = "annotated_essay_cls_1144_张三_2_wa.jpg"
    assert pm._student_base_from_marks_filename(legacy) == pm._student_base_from_marks_filename(wa)
    assert pm._page_no_from_marks_filename(wa) == 2
