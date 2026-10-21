# -*- coding: utf-8 -*-
"""整卷总分持久化（正反面语义）· 客户清单 #7 — 纯函数测试。

覆盖：
  1. 卷盒名/页号解析（与 router._paper_box_display_name 同口径）
  2. 正反面语义：1=正面、2=反面、3+=附页
  3. 合并口径：智能/参照/自主=逐页累加；作文=整卷取最大
  4. build_box_totals：正反面明细 + total/merge 持久化字段结构
  5. auto_class_sync.extract_scores_from_completed 的作文语义（不乘页数、作文权威）
"""
from app.grading import box_totals as bt
from app.services.auto_class_sync import extract_scores_from_completed


def test_paper_box_name_and_page_no():
    assert bt.paper_box_display_name("张三_1.jpg") == "张三"
    assert bt.paper_box_display_name("张三_2.png") == "张三"
    assert bt.paper_box_display_name("李四_1_2.jpg") == "李四_1"  # 贪婪：只去最后一页号
    assert bt.paper_box_display_name("王五.jpg") == "王五"
    assert bt.paper_box_display_name("") == ""
    assert bt.paper_box_page_no("张三_1.jpg") == 1
    assert bt.paper_box_page_no("张三_2.jpg") == 2
    assert bt.paper_box_page_no("李四_1_2.jpg") == 2
    assert bt.paper_box_page_no("王五.jpg") == 1
    assert bt.paper_box_page_no("王五_0.jpg") == 1  # 页号下限 1


def test_page_side_semantics():
    assert bt.page_side(1) == "front"
    assert bt.page_side(2) == "back"
    assert bt.page_side(3) == "extra"
    assert bt.page_side_label(1) == "正面"
    assert bt.page_side_label(2) == "反面"
    assert bt.page_side_label(5) == "附页"


def test_merge_mode_for_engine():
    assert bt.merge_mode_for_engine("essay") == "max"
    assert bt.merge_mode_for_engine("ESSAY") == "max"
    assert bt.merge_mode_for_engine("smart") == "sum"
    assert bt.merge_mode_for_engine(None) == "sum"
    assert bt.merge_mode_for_engine("") == "sum"


def test_merge_score_values():
    assert bt.merge_score_values([40, 60], "sum") == 100.0
    assert bt.merge_score_values([40, 60], "max") == 60.0
    assert bt.merge_score_values([40, 60, 20], "sum") == 120.0
    assert bt.merge_score_values([None, 55], "sum") == 55.0
    assert bt.merge_score_values([], "sum") is None
    assert bt.merge_score_values([None, None], "max") is None
    assert bt.merge_score_values([1.005, 2.004], "sum") == 3.01  # 2 位小数


def test_build_box_totals_front_back_sum():
    """智能/参照/自主：正反面两页独立计分 → 累加，明细带正反面标签。"""
    totals = bt.build_box_totals(
        [
            ("张三_1.jpg", 40, "sum"),
            ("张三_2.jpg", 60, "sum"),
            ("李四_1.jpg", 55, "sum"),
        ]
    )
    assert set(totals) == {"张三", "李四"}
    zhang = totals["张三"]
    assert zhang["total"] == 100.0
    assert zhang["merge"] == "sum"
    assert [p["side_label"] for p in zhang["pages"]] == ["正面", "反面"]
    assert [p["score"] for p in zhang["pages"]] == [40.0, 60.0]
    assert zhang["pages"][0]["name"] == "张三_1.jpg"
    assert zhang["pages"][1]["page_no"] == 2
    # 单页只有「正面」，无拆分
    assert totals["李四"]["total"] == 55.0
    assert [p["side_label"] for p in totals["李四"]["pages"]] == ["正面"]


def test_build_box_totals_essay_max_not_sum():
    """作文：多页重复写同一整卷总分 → 取最大，不乘页数。"""
    totals = bt.build_box_totals(
        [
            ("王五_1.jpg", 82, "max"),
            ("王五_2.jpg", 82, "max"),
        ]
    )
    assert totals["王五"]["total"] == 82.0  # 不是 164
    assert totals["王五"]["merge"] == "max"


def test_build_box_totals_essay_authoritative_over_sum():
    """同一卷盒两种通道都批过：作文整卷总分权威。"""
    totals = bt.build_box_totals(
        [
            ("赵六_1.jpg", 40, "sum"),
            ("赵六_2.jpg", 60, "sum"),
            ("赵六_1.jpg", 88, "max"),  # 同名覆盖 + 作文口径
        ]
    )
    # 赵六_1 变成 max 条目，赵六_2 仍是 sum 条目 → 有 max 分则只取 max
    assert totals["赵六"]["total"] == 88.0
    assert totals["赵六"]["merge"] == "max"


def test_build_box_totals_no_scores():
    totals = bt.build_box_totals(
        [
            ("孙七_1.jpg", None, "sum"),
            ("孙七_2.jpg", "abc", "sum"),  # 坏值当无分
        ]
    )
    assert totals["孙七"]["total"] is None
    assert totals["孙七"]["pages"][0]["score"] is None
    assert bt.build_box_totals([]) == {}


def test_extract_scores_smart_sum_and_essay_max():
    """auto_class_sync 口径：智能逐页累加；作文取最大不乘页数；作文覆盖同名卷盒。"""
    smart = {
        "张三_1.jpg": {"score_total": 40},
        "张三_2.jpg": {"score_total": 60},
        "李四_1.jpg": {"score_total": 55},
    }
    essay = {
        "王五_1.jpg": {"score_total": 82},
        "王五_2.jpg": {"score_total": 82},
        "赵六_2.jpg": {"score_total": 90},  # 与智能同卷盒 → 作文权威
    }
    smart_with_zhao = dict(smart)
    smart_with_zhao["赵六_1.jpg"] = {"score_total": 40}
    smart_with_zhao["赵六_2.jpg"] = {"score_total": 50}

    scores = extract_scores_from_completed(smart, essay)
    assert scores["张三"] == 100.0
    assert scores["李四"] == 55.0
    assert scores["王五"] == 82.0  # 作文多页不求和
    assert scores["赵六"] == 90.0  # 纯作文卷盒取最大

    # 强断言「作文权威」：智能 40+50=90，作文改 70 → 必须 70 而不是 160/90
    essay2 = {"赵六_2.jpg": {"score_total": 70}}
    scores2 = extract_scores_from_completed(smart_with_zhao, essay2)
    assert scores2["赵六"] == 70.0

    # 纯作文 / 纯智能 兼容旧调用
    assert extract_scores_from_completed(smart) == {"张三": 100.0, "李四": 55.0}
    assert extract_scores_from_completed(None, essay)["王五"] == 82.0
