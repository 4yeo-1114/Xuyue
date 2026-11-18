# -*- coding: utf-8 -*-
"""只读复现：真实试卷 PDF → 框线切题 → 百度OCR → 选择题解析/OMR，打印中间结果。

不写项目数据目录，产物只落 %TEMP%\\xuyue_probe。
"""
import json
import os
import sys
import tempfile
import re
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = Path(tempfile.gettempdir()) / "xuyue_probe"
OUT.mkdir(parents=True, exist_ok=True)

PAPERS_ROOT = Path(r"D:\叙阅源码包_20261115\叙阅迁移包_20260920\手写试卷")


def load_env_into_module():
    """把本地安装包 .env 里的百度密钥读进 os.environ（app.config.settings 需要）。"""
    env_path = Path(r"D:\叙阅本地化安装包_20261116\app\.env")
    txt = env_path.read_text(encoding="utf-8")
    for key in ("BAIDU_ACCESS_TOKEN", "BAIDU_API_KEY", "BAIDU_SECRET_KEY", "DASHSCOPE_API_KEY"):
        m = re.search(rf"^{key}=(.*)$", txt, re.M)
        if m and m.group(1).strip():
            os.environ[key] = m.group(1).strip()
            print(f"[env] {key} loaded ({m.group(1).strip()[:8]}…)")


def pdf_first_page(pdf_path: Path, dpi: int = 150):
    import fitz
    from PIL import Image
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def probe_paper(pdf_path: Path, tag: str):
    print("\n" + "#" * 72)
    print(f"# {tag}  {pdf_path.name}")
    img = pdf_first_page(pdf_path)
    png = OUT / f"{tag}_page.png"
    img.save(png)
    print(f"[img] {img.size} -> {png}")

    from app.grading.manual_grading import _baidu_ocr_text, _choice_answer_tokens, _ocr_question_numbers
    from app.grading.answer_key_grading import _parse_choice_answers, _omr_choice_answer

    # 1) 百度全页 OCR
    words = _baidu_ocr_text(str(png))
    (OUT / f"{tag}_words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ocr] 词数={len(words)} 已存 {tag}_words.json")

    # 2) 题号词 & 涂卡词
    nums = _ocr_question_numbers(str(png), words=words)
    print(f"[numbers] {[(n['num'], n['bbox']) for n in nums][:30]}")
    toks = _choice_answer_tokens(words)
    print(f"[choice_tokens] {[{'num': t['num'], 'filled': t['filled'], 'bbox': t['bbox']} for t in toks]}")
    # 严格整串匹配失败的候选行（括号选项被拆词的）
    for w in words:
        if re.search(r"\[\s*[A-Z]\s*\]", w["words"]):
            print("   [bracket-word]", repr(w["words"]), w["bbox"])

    # 3) _parse_choice_answers（判分链路用的那个，含 9..14 白名单）
    parsed = _parse_choice_answers(words)
    print(f"[_parse_choice_answers] {parsed}")

    # 4) 框线切题
    from app.grading.answer_card_boxes import detect_answer_card_boxes
    res = detect_answer_card_boxes(str(png))
    print(f"[boxes] valid={res.get('valid')} reason={res.get('reason')!r} 区数={len(res.get('questions') or [])} 栏={res.get('columns')}")
    for q in (res.get("questions") or []):
        print("   ", q.get("kind"), q.get("bbox"))

    # 5) OMR 逐选择题块
    for q in (res.get("questions") or []):
        if q.get("kind") != "choice":
            continue
        bbox = q["bbox"]
        omr = _omr_choice_answer(str(png), bbox)
        print(f"[OMR] bbox={bbox} -> {omr!r}")

    # 6) 完整手动布局（这就是 manual_analyze blocks 的来源）
    try:
        from app.grading.manual_grading import build_manual_layout_page_from_boxes
        page = build_manual_layout_page_from_boxes(str(png), page_no=1, filename=png.name, image_url="")
        (OUT / f"{tag}_layout.json").write_text(json.dumps(page, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[layout] questions={len(page['questions'])} 已存 {tag}_layout.json")
        for q in page["questions"]:
            slots = q.get("answer_slots") or []
            print(f"   q{int(q.get('display_no') or 0):>2} kind={q.get('kind')!r:12} slots={[s.get('label') for s in slots]} bbox={slots[0].get('bbox') if slots else None}")
    except Exception as e:
        print(f"[layout] FAILED: {type(e).__name__}: {e}")


def main():
    load_env_into_module()
    todo = [
        (PAPERS_ROOT / "2105班科学期中试卷" / "2105班科学期中试卷" / "S22C-6i26111015220_0003.pdf", "kx_0003"),
        (PAPERS_ROOT / "初一26班语文11.16", "yuwen"),
        (PAPERS_ROOT / "数学", "math"),
    ]
    for arg in sys.argv[1:]:
        todo = [(p, p.stem) for p in PAPERS_ROOT.rglob(f"*{arg}*.pdf")]
        break
    for path, tag in todo:
        if path.is_file():
            try:
                probe_paper(path, tag)
            except Exception as e:
                import traceback
                print(f"[FAIL] {path}: {type(e).__name__}: {e}")
                traceback.print_exc()
        else:
            print(f"[skip] 不存在: {path}")


if __name__ == "__main__":
    main()
