# -*- coding: utf-8 -*-
"""draw_wrong_annotations_variant 落点规则单测：

2026-10-16 用户要求「批注在这道题目的右下角」：错因/批注首选本题自己的题框
右下角空带（可压本题印刷内容，不压任何作答区/留痕/别题框）；框内放不下才按
2026-10-12 规则作答区正下方起排、再沉画布底白带（加题号前缀）。右半页批注
不许飞到左半页（双页拼版）；能原位的不许被沉底批注挤跑。
像素级断言：#e60000 红字不得落入任何作答框/别题题框禁区。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.grading.pipeline import draw_wrong_annotations_variant


def _is_red(px) -> bool:
    r, g, b = px
    return r > 180 and g < 80 and b < 80


def _red_bbox(img: Image.Image):
    w, h = img.size
    px = img.load()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if _is_red(px[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def _has_red(img: Image.Image, rect) -> bool:
    x1, y1, x2, y2 = (int(v) for v in rect)
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(img.size[0], x2)
    y2 = min(img.size[1], y2)
    if x2 <= x1 or y2 <= y1:
        return False
    region = img.crop((x1, y1, x2, y2))
    return any(_is_red(p) for p in region.getdata())


def _run(tmp_path: Path, blocks: list, wrong: dict, size=(1600, 1200)):
    src = Path(tmp_path) / "marks_only.png"
    Image.new("RGB", size, "white").save(src)
    out = Path(tmp_path) / "wa.png"
    ok = draw_wrong_annotations_variant(str(src), str(out), blocks, wrong)
    assert ok is True
    return Image.open(out).convert("RGB")


def _blk(index, bbox, qbox):
    return {"index": index, "sub_index": 1, "bbox": bbox, "baidu_question_bbox": qbox}


def test_no_red_on_stems_two_page(tmp_path):
    # 双页拼版复刻用户实卷：右半页第5题挤不下（下方被第6题题框占）会沉底；
    # 第1题正下方被第2题题框占也会沉底。任何红字都不得进题框/作答框。
    blocks = [
        _blk(1, [230, 217, 714, 421], [120, 164, 753, 434]),
        _blk(2, [130, 700, 500, 760], [115, 442, 675, 889]),
        _blk(3, [157, 1080, 764, 1162], [117, 887, 785, 1172]),
        _blk(5, [1319, 405, 1347, 439], [1130, 350, 1550, 500]),
        _blk(5, [1463, 455, 1494, 492], [1130, 350, 1550, 500]),
        _blk(6, [980, 700, 1100, 760], [960, 520, 1620, 1120]),
    ]
    wrong = {
        "1": {"text": "错因：袜子、短裙和冰淇淋连错啦，想想它们该放哪儿？按生活常识重新连线试试。", "source": "ai"},
        "3": {"text": "错因：铅笔和橡皮数错啦，再仔细数数，形状都对了，加油！", "source": "ai"},
        "5": {"text": "错因：数漏啦，长方形卡片一共有5个，再仔细找找看？", "source": "ai"},
    }
    img = _run(tmp_path, blocks, wrong)
    assert _red_bbox(img) is not None, "错因应已画出"
    for blk in blocks:
        assert not _has_red(img, blk["bbox"]), f"红字压了作答区 {blk['index']}"
        assert not _has_red(img, blk["baidu_question_bbox"]), f"红字压了题干 {blk['index']}"


def test_right_page_note_never_teleports_left(tmp_path):
    # 右半页的错因，无论原位还是沉底，都不许飞到左半页（旧 bug：锚太靠右→左飞压 Q2 题干）
    blocks = [
        _blk(2, [130, 700, 500, 760], [115, 442, 675, 889]),
        _blk(5, [1319, 405, 1347, 439], [1130, 350, 1550, 500]),
        _blk(6, [980, 700, 1100, 760], [960, 520, 1620, 1120]),
    ]
    wrong = {"5": {"text": "错因：数漏啦，长方形卡片一共有5个，再仔细找找看？", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong)
    assert _red_bbox(img) is not None
    assert not _has_red(img, (0, 0, img.size[0] // 2, img.size[1])), "右页批注飞到了左半页"


def test_sinks_below_content_when_no_room(tmp_path):
    # 正下方被下一题题框占死 → 沉到全部内容之下
    blocks = [
        _blk(1, [230, 217, 714, 421], [120, 164, 753, 434]),
        _blk(2, [130, 700, 500, 760], [115, 442, 675, 889]),
    ]
    wrong = {"1": {"text": "错因：袜子、短裙和冰淇淋连错啦，想想它们该放哪儿？", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong)
    rb = _red_bbox(img)
    assert rb is not None
    excl_bottom = max(max(b["bbox"][3], b["baidu_question_bbox"][3]) for b in blocks)
    assert rb[1] > excl_bottom - 2, f"沉底批注 y={rb[1]} 未过内容底线 {excl_bottom}"


def test_in_place_kept_when_room(tmp_path):
    # 下方有空白：原位画在作答区正下方，不被挤去沉底
    blocks = [_blk(3, [157, 1080, 764, 1162], [117, 887, 785, 1172])]
    wrong = {"3": {"text": "错因：铅笔和橡皮数错啦，再仔细数数，形状都对了，加油！", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong, size=(1600, 1247))
    rb = _red_bbox(img)
    assert rb is not None
    assert 1162 <= rb[1] < 1162 + 80, f"错因未紧跟作答区下方 (y={rb[1]})"
    assert not _has_red(img, blocks[0]["bbox"])
    assert not _has_red(img, blocks[0]["baidu_question_bbox"])


def test_in_place_not_pushed_by_sinking(tmp_path):
    # 一条能原位、一条必须沉底：原位的不许被沉底的挤跑（沉底须避开已就位批注）
    blocks = [
        _blk(1, [230, 217, 714, 421], [120, 164, 753, 434]),
        _blk(2, [130, 700, 500, 760], [115, 442, 675, 889]),
        _blk(3, [157, 1080, 764, 1162], [117, 887, 785, 1172]),
    ]
    wrong = {
        "1": {"text": "错因：袜子、短裙和冰淇淋连错啦，想想它们该放哪儿？", "source": "ai"},
        "3": {"text": "错因：铅笔和橡皮数错啦，再仔细数数，形状都对了，加油！", "source": "ai"},
    }
    img = _run(tmp_path, blocks, wrong, size=(1600, 1247))
    # 第3题：错因紧跟 3 的作答区正下方（原位）
    assert _has_red(img, (157, 1165, 764, 1240)), "第3题错因应原位在作答区下方"
    # 第1题：沉底但不得压任何禁区
    for blk in blocks:
        assert not _has_red(img, blk["bbox"])
        assert not _has_red(img, blk["baidu_question_bbox"])


def test_corner_placement_inside_question_frame(tmp_path):
    # 2026-10-16 用户要求：错因优先写在本题自己的题框右下角（红笔旁批，不加白底）；
    # 不压作答区、不压别题题框。框内底带够高（≥一行）就必走候选A，不沉底。
    blocks = [
        _blk(3, [200, 400, 800, 450], [150, 150, 900, 700]),
        _blk(4, [200, 800, 800, 950], [150, 750, 900, 1100]),
    ]
    wrong = {"3": {"text": "错因：C项读音全对，再看看题干要求选读音有误的一项。", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong, size=(1600, 1200))
    rb = _red_bbox(img)
    assert rb is not None, "错因应已画出"
    qx1, qy1, qx2, qy2 = blocks[0]["baidu_question_bbox"]
    # 红字应落在第3题题框内右下角（框内底带 450→700）
    assert _has_red(img, (qx2 - 500, qy2 - 250, qx2, qy2)), f"错因未落在题框右下角 (rb={rb})"
    assert _has_red(img, blocks[0]["baidu_question_bbox"]), "错因应在第3题题框内"
    # 不压作答区、不压邻题题框/作答区、也不沉底
    assert not _has_red(img, blocks[0]["bbox"]), "错因压了作答区"
    for blk in blocks[1:]:
        assert not _has_red(img, blk["bbox"])
        assert not _has_red(img, blk["baidu_question_bbox"])
    assert not _has_red(img, (0, 1100, img.size[0], img.size[1])), "不该沉到画布底"


def test_corner_lifts_above_answer_box(tmp_path):
    # 框内底带被邻题作答区压住一角：贴带上移避开，仍留在框内右下，不逃去沉底
    blocks = [
        _blk(3, [200, 300, 800, 350], [150, 150, 900, 700]),
        _blk(4, [200, 640, 700, 690], [150, 750, 900, 1100]),
    ]
    wrong = {"3": {"text": "错因：这道题的单位写错啦，补上单位再算一遍。", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong, size=(1600, 1200))
    assert _has_red(img, blocks[0]["baidu_question_bbox"]), "错因应留在第3题题框内"
    assert not _has_red(img, blocks[0]["bbox"]), "错因压了第3题作答区"
    for blk in blocks[1:]:
        assert not _has_red(img, blk["bbox"]), "错因压了邻题作答区"
        assert not _has_red(img, blk["baidu_question_bbox"])
