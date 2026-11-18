# -*- coding: utf-8 -*-
"""填空题链路 A/B 诊断（只读业务代码，产物写 %TEMP%\\xuyue_probe）。

"修复前" 用 git HEAD 版本的 answer_key_grading.py（工作区改动未提交），
"修复后" 用工作区当前版本，跑同一批真实试卷 blocks，对比漏批/待确认/对/错。
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

OUT = Path(tempfile.gettempdir()) / "xuyue_probe"
OUT.mkdir(parents=True, exist_ok=True)
ENV_FILE = Path(r"D:\叙阅本地化安装包_20261116\app\.env")

PAPER = Path(
    r"D:\叙阅源码包_20261115\叙阅迁移包_20260920\手写试卷\初一21班地理\地理\20261110035410351_0001.pdf"
)


def load_keys() -> None:
    txt = ENV_FILE.read_text(encoding="utf-8")
    for key in ("BAIDU_ACCESS_TOKEN", "BAIDU_API_KEY", "BAIDU_SECRET_KEY", "DASHSCOPE_API_KEY"):
        m = re.search(rf"^{key}=(.*)$", txt, re.M)
        if m and m.group(1).strip():
            os.environ[key] = m.group(1).strip()


def load_old_module():
    """从 git HEAD 取出修复前的 answer_key_grading.py 作为独立模块。"""
    src = subprocess.run(
        ["git", "show", "HEAD:backend/app/grading/answer_key_grading.py"],
        cwd=str(BACKEND.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    target = OUT / "old_answer_key_grading.py"
    target.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("old_answer_key_grading", target)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["old_answer_key_grading"] = mod
    spec.loader.exec_module(mod)
    return mod


def render_page() -> Path:
    png = OUT / "geog_page.png"
    if png.is_file():
        return png
    import fitz
    from PIL import Image

    doc = fitz.open(str(PAPER))
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
    Image.frombytes("RGB", [pix.width, pix.height], pix.samples).save(png)
    doc.close()
    return png


def build_blocks(png: Path) -> list:
    from app.grading.reference_vlm_grading import (
        _printed_number_candidates,
        build_reference_layout_page,
        recognize_reference_vlm_batch,
    )
    from app.grading.manual_grading import (
        _baidu_ocr_text,
        build_manual_layout_page_from_reference_layout,
        manual_layout_blocks_for_image,
    )

    cache, errors = recognize_reference_vlm_batch([("geo", "地理", str(png))], allow_empty=True)
    if errors:
        raise RuntimeError(f"切题失败: {errors}")
    doc = cache["geo"]
    pns = _printed_number_candidates(_baidu_ocr_text(str(png)))
    ref = build_reference_layout_page(doc, page_no=1, filename=png.name, image_url="", printed_numbers=pns)
    page = build_manual_layout_page_from_reference_layout(
        ref, page_no=1, filename=png.name, image_url="", image_path=str(png), number_offset=0
    )
    blocks, _size = manual_layout_blocks_for_image(page, str(png))
    (OUT / "geo_blocks.json").write_text(json.dumps(blocks, ensure_ascii=False, indent=1), encoding="utf-8")
    return blocks


def build_answer_key(blocks: list) -> dict:
    """给每个 block 造标准答案：含多空题与小数答案，覆盖解析/多空两条修复点。"""
    key: dict[str, str] = {}
    for i, b in enumerate(blocks):
        q = int(b.get("index") or 0)
        if i == 0:
            # 多空题：同题两个空
            key[f"{q}_1"] = "海拔"
            key[f"{q}_2"] = "相对高度"
        elif i == 1:
            key[f"{q}_1"] = "0.5"
        elif i == 2:
            key[f"{q}_1"] = "1.08×10^5"
        else:
            key[f"{q}_1"] = "鞍部"
    # 特意留最后 2 个 block 不给标准答案，验证「无答案」也留痕
    for b in blocks[-2:]:
        key.pop(f"{b.get('index')}_1", None)
    return key


def run(ak_module, tag: str, png: Path, blocks: list, answer_key: dict) -> dict:
    import copy

    blocks_copy = copy.deepcopy(blocks)
    decisions = ak_module.grade_paper_by_answer_key(str(png), blocks_copy, answer_key)

    rows = []
    for b in blocks_copy:
        idx = b.get("index")
        slot = str(b.get("slot_id") or "")
        dec = decisions.get(slot) or {}
        status = str(dec.get("status") or "ungraded")
        trace = bool(b.get("reason") or b.get("analysis")) or bool(b.get("read_uncertain")) or bool(b.get("needs_review"))
        rows.append(
            {
                "题号": idx,
                "label": b.get("label"),
                "标准": b.get("expected_answer"),
                "读取": b.get("student_answer"),
                "判定": status,
                "有痕迹": trace,
                "原因": str(b.get("reason") or "")[:36],
            }
        )
    silent = [r for r in rows if r["判定"] not in ("correct", "wrong", "partial", "unanswered") and not r["有痕迹"]]
    review = [r for r in rows if r["判定"] not in ("correct", "wrong", "partial", "unanswered") and r["有痕迹"]]
    judged = [r for r in rows if r["判定"] in ("correct", "wrong", "partial")]

    print(f"\n{'='*100}\n[{tag}] 块数={len(rows)}  有判定={len(judged)}  显式待确认={len(review)}  ★静默漏批={len(silent)}")
    print(f"{'='*100}")
    print(f"{'题':>3} {'label':<6} {'标准':<22} {'读取':<14} {'判定':<10} 痕迹 原因")
    for r in rows:
        print(
            f"{r['题号']:>3} {str(r['label']):<6} {str(r['标准'])[:20]:<22} {str(r['读取'])[:12]:<14} "
            f"{r['判定']:<10} {'Y' if r['有痕迹'] else '-':<4} {r['原因']}"
        )
    result = {
        "tag": tag,
        "blocks": len(rows),
        "judged": len(judged),
        "review": len(review),
        "silent_missed": len(silent),
        "correct": sum(1 for r in rows if r["判定"] == "correct"),
        "wrong": sum(1 for r in rows if r["判定"] == "wrong"),
        "rows": rows,
    }
    (OUT / f"geog_fillin_{tag}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main() -> None:
    load_keys()
    png = render_page()
    blocks = build_blocks(png)
    answer_key = build_answer_key(blocks)

    import app.grading.answer_key_grading as new_ak

    old_ak = load_old_module()
    before = run(old_ak, "before", png, blocks, answer_key)
    after = run(new_ak, "after", png, blocks, answer_key)

    print("\n" + "#" * 100)
    print("# 填空题前后对比")
    print("#" * 100)
    print(f"{'指标':<16}{'修复前':>10}{'修复后':>10}")
    print(f"{'块数':<16}{before['blocks']:>10}{after['blocks']:>10}")
    print(f"{'有判定':<16}{before['judged']:>10}{after['judged']:>10}")
    print(f"{'显式待确认':<16}{before['review']:>10}{after['review']:>10}")
    print(f"{'静默漏批':<16}{before['silent_missed']:>10}{after['silent_missed']:>10}")
    print(f"{'判对':<16}{before['correct']:>10}{after['correct']:>10}")
    print(f"{'判错':<16}{before['wrong']:>10}{after['wrong']:>10}")
    denom_b = before["blocks"] or 1
    denom_a = after["blocks"] or 1
    print(
        f"{'判对率(含待确认作分母)':<16}{before['correct']/denom_b:>10.1%}{after['correct']/denom_a:>10.1%}"
    )


if __name__ == "__main__":
    main()
