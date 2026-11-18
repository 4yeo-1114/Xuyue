# -*- coding: utf-8 -*-
"""draw_wrong_annotations_variant 落点规则单测：

2026-10-26 用户要求「批注放相关题目旁边的空白处」+硬规则「没有空白你就缩小字
放旁边，反正现在就是不能放在下面」：错因/批注落点——
⓪ 本题旁的空白通道（右优先、左次之，题顶对齐，不跨装订线；缩字阶 1.0→0.45
每阶配最少每行字数；密排卷的页边白条也是「旁边的空白处」，贴页缘的通道允许
向下流淌、挤离本题行加题号前缀）→ 1 本题题框右下角（2026-10-16 红笔旁批）→
2（终兜底）页外加宽白条侧栏仍放本题行旁（缩字 0.7/0.55/0.45，画布向左/右加宽）。
⛔ 作答区正下方/沉画布底两级已删——批注绝不画到题目下面。
像素级断言：红字不得落入任何作答框/别题题框禁区（画布加宽后坐标平移校正）。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.grading.pipeline import draw_manual_annotations, draw_wrong_annotations_variant


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
    # 双页拼版复刻用户实卷：右半页第5题挤不下（下方被第6题题框占）走题旁；
    # 第1、3题的侧向只剩窄页边（每行 <5 字），缩字进页边或沉底。
    # 任何红字都不得进题框/作答框。
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
    # 右半页的错因，无论题旁、原位还是沉底，都不许飞到左半页（旧 bug：锚太靠右→左飞压 Q2 题干）
    blocks = [
        _blk(2, [130, 700, 500, 760], [115, 442, 675, 889]),
        _blk(5, [1319, 405, 1347, 439], [1130, 350, 1550, 500]),
        _blk(6, [980, 700, 1100, 760], [960, 520, 1620, 1120]),
    ]
    wrong = {"5": {"text": "错因：数漏啦，长方形卡片一共有5个，再仔细找找看？", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong)
    assert _red_bbox(img) is not None
    assert not _has_red(img, (0, 0, img.size[0] // 2, img.size[1])), "右页批注飞到了左半页"


def test_no_room_grows_side_strip_never_below(tmp_path):
    # 侧通道被旁题占死（含页边）+ 题框右下角底带不够高 → 页外加宽白条放本题行旁
    #（2026-10-26 硬规则「不能放在下面」：不许沉底/画到题下）
    blocks = [
        _blk(1, [230, 217, 714, 421], [120, 164, 753, 434]),
        _blk(2, [130, 700, 500, 760], [115, 442, 675, 889]),
        # 旁题占住第1题右侧通道（与 Q1 同高层）
        _blk(8, [820, 180, 1500, 420], [800, 150, 1540, 450]),
        # 页边也被占死（密排卷页边有内容时题旁通道同样不成立）
        _blk(9, [10, 150, 110, 470], [5, 140, 115, 480]),
    ]
    wrong = {"1": {"text": "错因：袜子、短裙和冰淇淋连错啦，想想它们该放哪儿？", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong)
    dx = img.size[0] - 1600
    assert dx > 0, "无处可放应向页外加宽画布放侧栏，而不是沉到题目下面"
    assert img.size[1] == 1200, "不许向下加高沉底"
    rb = _red_bbox(img)
    assert rb is not None
    # 错因整体在左白条、贴本题行旁（不进页面、不画到题下）
    assert rb[2] <= dx, f"错因应整体在页外白条 (rb={rb}, dx={dx})"
    assert rb[1] < 434, f"错因应与本题行平行，不得画到题下 (rb={rb})"
    assert _has_red(img, (0, 150, dx, 500)), "错因应进页外白条、贴本题行"
    # 不压原卷任何内容（坐标随左加宽整体右移 dx）
    for blk in blocks:
        assert not _has_red(img, (blk["bbox"][0] + dx, blk["bbox"][1], blk["bbox"][2] + dx, blk["bbox"][3]))
        q = blk["baidu_question_bbox"]
        assert not _has_red(img, (q[0] + dx, q[1], q[2] + dx, q[3]))


def test_shrink_into_narrow_side_channel(tmp_path):
    # 侧通道窄到全尺寸每行放不下 5 个字 → 缩字塞进题旁（2026-10-26「没有空白你就
    # 缩小字放旁边」），不许因此画到题下/沉底，画布也不用加宽/加高
    blocks = [
        _blk(3, [157, 1080, 560, 1162], [117, 887, 600, 1172]),
        # 左页边占死（逼右侧窄道）；右侧只留 ~46px 窄道（600 → 邻题 690）
        _blk(9, [10, 880, 110, 1190], [5, 870, 115, 1200]),
        _blk(8, [710, 900, 1500, 1150], [690, 870, 1540, 1170]),
    ]
    wrong = {"3": {"text": "错因：铅笔和橡皮数错啦，再仔细数数，形状都对了，加油！", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong, size=(1600, 1247))
    assert img.size == (1600, 1247), f"缩字进得去就不该加宽/加高画布 (size={img.size})"
    rb = _red_bbox(img)
    assert rb is not None
    assert rb[0] >= 605 and rb[2] <= 680, f"错因应缩字进第3题右侧窄道 (rb={rb})"
    assert rb[1] < 1172, f"错因应贴本题行旁起排，不得画到题下 (rb={rb})"
    for blk in blocks:
        assert not _has_red(img, blk["bbox"])
        assert not _has_red(img, blk["baidu_question_bbox"])


def test_side_kept_when_other_grows_strip(tmp_path):
    # 一条缩字进题旁窄道、一条只能页外白条：白条的不许把题旁的挤跑；
    # 两条都不许画到题目下面（2026-10-26 硬规则）
    blocks = [
        _blk(1, [230, 217, 714, 421], [120, 164, 753, 434]),
        _blk(2, [130, 700, 500, 760], [115, 442, 675, 889]),
        _blk(3, [157, 1080, 764, 1162], [117, 887, 785, 1172]),
        # 第1题右/左同高层全占死 → 页外白条（Q8/Q9 只压第1题层，不碰第3题行）
        _blk(8, [820, 180, 1500, 420], [800, 150, 1540, 450]),
        _blk(9, [10, 150, 110, 470], [5, 140, 115, 480]),
    ]
    wrong = {
        "1": {"text": "错因：袜子、短裙和冰淇淋连错啦，想想它们该放哪儿？", "source": "ai"},
        "3": {"text": "错因：铅笔和橡皮数错啦，再仔细数数，形状都对了，加油！", "source": "ai"},
    }
    img = _run(tmp_path, blocks, wrong, size=(1600, 1247))
    dx = img.size[0] - 1600
    assert dx > 0, "第1题应走页外白条（画布左加宽）"
    assert img.size[1] == 1247, "不许向下加高沉底"
    # 第3题：缩字留在自己题旁左窄道（坐标随左加宽右移 dx），没被挤跑
    assert _has_red(img, (0 + dx, 887, 115 + dx, 1172)), "第3题错因应留在题旁窄道"
    # 第1题：进左白条、贴本题行旁
    assert _has_red(img, (0, 150, dx, 500)), "第1题错因应进页外白条、贴本题行"
    # 两条都不在题下/内容底下
    assert not _has_red(img, (dx, 1172, img.size[0], img.size[1])), "错因不许画到题目下面"
    for blk in blocks:
        assert not _has_red(img, (blk["bbox"][0] + dx, blk["bbox"][1], blk["bbox"][2] + dx, blk["bbox"][3]))
        q = blk["baidu_question_bbox"]
        assert not _has_red(img, (q[0] + dx, q[1], q[2] + dx, q[3]))


def test_corner_placement_inside_question_frame(tmp_path):
    # 2026-10-16 用户要求：错因优先写在本题自己的题框右下角（红笔旁批，不加白底）；
    # 不压作答区、不压别题题框。框内底带够高（≥一行）就必走候选1，不沉底。
    blocks = [
        _blk(3, [200, 400, 800, 450], [150, 150, 900, 700]),
        _blk(4, [200, 800, 800, 950], [150, 750, 900, 1100]),
        # 旁题占住第3题右侧通道（左侧留白太窄每行放不下5字），逼出题框右下角
        _blk(8, [950, 100, 1560, 720], [930, 80, 1580, 740]),
        # 页边也占死：题旁通道全灭才轮到题框右下角
        _blk(9, [10, 120, 130, 730], [5, 110, 135, 740]),
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
        # 旁题占住第3题右侧通道，逼出题框右下角
        _blk(8, [950, 100, 1560, 720], [930, 80, 1580, 740]),
        # 页边也占死：题旁通道全灭才轮到题框右下角
        _blk(9, [10, 120, 130, 730], [5, 110, 135, 740]),
    ]
    wrong = {"3": {"text": "错因：这道题的单位写错啦，补上单位再算一遍。", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong, size=(1600, 1200))
    assert _has_red(img, blocks[0]["baidu_question_bbox"]), "错因应留在第3题题框内"
    assert not _has_red(img, blocks[0]["bbox"]), "错因压了第3题作答区"
    for blk in blocks[1:]:
        assert not _has_red(img, blk["bbox"]), "错因压了邻题作答区"
        assert not _has_red(img, blk["baidu_question_bbox"])


# ── 2026-10-26 题旁空白处（落点⓪） ──


def test_side_placement_right_channel(tmp_path):
    # 孤题右侧整片留白：错因画在题旁右通道、题顶对齐起排，不压内容、不沉底
    blocks = [_blk(1, [230, 217, 714, 421], [120, 164, 753, 434])]
    wrong = {"1": {"text": "错因：袜子、短裙和冰淇淋连错啦，想想它们该放哪儿？", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong)
    rb = _red_bbox(img)
    assert rb is not None
    assert rb[0] >= 760, f"错因应画在题框右侧 (rb={rb})"
    assert rb[1] < 450, f"错因应与题平行起排，不是画到题下面 (rb={rb})"
    assert _has_red(img, (760, 150, 1560, 500)), "错因应落在题旁右通道"
    assert not _has_red(img, (0, 440, img.size[0], img.size[1])), "不该沉到题下/画布底"
    assert not _has_red(img, blocks[0]["bbox"])
    assert not _has_red(img, blocks[0]["baidu_question_bbox"])


def test_side_placement_spread_gutter(tmp_path):
    # 双页拼版：右页第5题的错因落右页左侧（装订线旁空白通道），不跨到左页
    blocks = [
        _blk(2, [130, 700, 500, 760], [115, 442, 675, 889]),
        _blk(5, [1319, 405, 1347, 439], [1130, 350, 1550, 500]),
        _blk(6, [980, 700, 1100, 760], [960, 520, 1620, 1120]),
    ]
    wrong = {"5": {"text": "错因：数漏啦，长方形卡片一共有5个，再仔细找找看？", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong)
    rb = _red_bbox(img)
    assert rb is not None
    assert rb[0] >= 800, f"错因应落右页装订线旁通道 (rb={rb})"
    assert rb[2] <= 1130, f"错因应在第5题题框左侧通道 (rb={rb})"
    assert _has_red(img, (800, 300, 1130, 550)), "错因应落在第5题旁的空白通道"
    assert not _has_red(img, (0, 0, img.size[0] // 2, img.size[1])), "不许跨装订线到左页"
    for blk in blocks:
        assert not _has_red(img, blk["bbox"])
        assert not _has_red(img, blk["baidu_question_bbox"])


def test_side_not_sink_when_side_fits(tmp_path):
    # 下方被下一题题框占死，但题旁有空白 → 画题旁（用户要求：不要全沉底）
    blocks = [
        _blk(1, [230, 217, 714, 421], [120, 164, 753, 434]),
        _blk(2, [130, 700, 500, 760], [115, 442, 675, 889]),
    ]
    wrong = {"1": {"text": "错因：袜子、短裙和冰淇淋连错啦，想想它们该放哪儿？", "source": "ai"}}
    img = _run(tmp_path, blocks, wrong)
    rb = _red_bbox(img)
    assert rb is not None
    assert rb[0] >= 760, f"错因应画在题旁 (rb={rb})"
    assert _has_red(img, (760, 150, 1560, 500)), "错因应落在题旁右通道"
    assert not _has_red(img, (0, 889, img.size[0], img.size[1])), "题旁放得下就不该沉底"
    for blk in blocks:
        assert not _has_red(img, blk["bbox"])
        assert not _has_red(img, blk["baidu_question_bbox"])


def test_manual_note_beside_question(tmp_path):
    # draw_manual_annotations 同样题旁优先（老师批注，#d62727 红）
    img = Image.new("RGB", (1600, 1200), "white")
    draw = ImageDraw.Draw(img)
    blocks = [_blk(1, [230, 217, 714, 421], [120, 164, 753, 434])]
    draw_manual_annotations(
        draw, 1600, 1200, blocks,
        {"1": "错因：袜子、短裙和冰淇淋连错啦，想想它们该放哪儿？"}, "",
    )
    rb = _red_bbox(img)
    assert rb is not None
    assert rb[0] >= 760, f"批注应画在题旁右侧 (rb={rb})"
    assert _has_red(img, (760, 150, 1560, 500)), "批注应落在题旁右通道"
    assert not _has_red(img, (0, 440, 1600, 1200)), "批注不该沉到题下面/画布底"
    assert not _has_red(img, blocks[0]["bbox"])
    assert not _has_red(img, blocks[0]["baidu_question_bbox"])


def test_dense_paper_margin_sides(tmp_path):
    # 密排双页卷（李雪梅_1 实测几何 1810×1280）：题排满页宽、行间零缝、
    # 答案嵌在行尾——唯一的「题目旁边的空白处」是左右页边白条。
    # 错因必须进页边、贴本题行起排，画布不许加高、不许沉底。
    size = (1810, 1280)
    blocks = [
        _blk(3, [664, 528, 707, 559], [161, 500, 856, 566]),
        _blk(4, [300, 590, 360, 620], [164, 564, 859, 628]),
        _blk(6, [300, 720, 360, 750], [166, 694, 862, 761]),
        _blk(12, [1200, 300, 1260, 330], [930, 249, 1640, 377]),
        _blk(15, [1200, 580, 1260, 610], [936, 558, 1637, 658]),
        _blk(17, [961, 913, 1179, 989], [910, 785, 1654, 1114]),
    ]
    wrong = {
        "3": {"text": "错因：长方体棱长总和公式用错啦，应该是(长+宽+高)×4，再仔细算算看？", "source": "ai"},
        "4": {"text": "错因：你算的是两个苹果的总体积360，记得除以2，单个体积应该是180cm³哦。", "source": "ai"},
        "6": {"text": "错因：没把2.4升换算成2400立方厘米，直接用2.4除底面积了，记得先统一单位再算深度哦。", "source": "ai"},
        "12": {"text": "错因：找相对面要隔一个格子，所以它们相对，应该选A哦。", "source": "ai"},
        "15": {"text": "错因：甲乙体积不同但表面积相等，要分开计算面数哦。", "source": "ai"},
        "17": {"text": "错因：表面积不能简单相加，要算长方体整体，记得补上哦。", "source": "ai"},
    }
    img = _run(tmp_path, blocks, wrong, size=size)
    assert img.size == size, f"错因都进页边时画布不该加高 (size={img.size})"
    # 左页边白条有错因（Q3/Q4/Q6 旁），右页边白条有错因（Q12/Q15/Q17 旁）
    assert _has_red(img, (0, 480, 158, 1280)), "左页边应有错因（贴 Q3/Q4/Q6 行）"
    assert _has_red(img, (1656, 230, 1810, 1280)), "右页边应有错因（贴 Q12/Q15/Q17 行）"
    # 不压任何作答区/题框；页面中带底部没有沉底条
    for blk in blocks:
        assert not _has_red(img, blk["bbox"]), f"错因压了作答区 {blk['index']}"
        assert not _has_red(img, blk["baidu_question_bbox"]), f"错因压了题干 {blk['index']}"
    assert not _has_red(img, (158, 1120, 1656, 1280)), "错因不许沉到页面底部中带"
