# -*- coding: utf-8 -*-
"""批改诊断脚本（第 2 步）：用真实学生卷跑一遍判分，把问题量化。

只读不改：不修改任何批改业务逻辑，只对 answer_key_grading / verdict_cache 的
**模块级函数做运行时包装**，用来记录「每个作答区的学生答案是从哪一级读出来的」。

用法（在 backend 根目录跑）：
    python scripts/diagnose_grading.py --manifest scripts/diagnose_manifest.json --out diag_out
    python scripts/diagnose_grading.py --manifest ... --folder 初一26班英语   # 只跑一场

清单文件（manifest.json）格式：
{
  "exams": [
    {
      "name": "初一26班英语",
      "subject": "英语",
      "template_page": "手写试卷/初一26班英语/26班/20261110011834585_0001.pdf",
      "answer_key_files": ["手写试卷/初一26班英语/英语标准答案P1.pdf",
                           "手写试卷/初一26班英语/英语标准答案P2.pdf"],
      "answer_key_text": null,
      "papers": [
        {"id": "陈典鹏", "pages": [".../0001.pdf", ".../0002.pdf"],
         "ground_truth": {"1_1": "A", "2_1": "A"}}
      ]
    }
  ]
}

ground_truth 两种写法都支持：
  简单式  {"1_1": "A"}                       —— 只给老师判读到的学生答案
  完整式  {"1_1": {"gt_student": "A", "gt_result": "wrong"}}
           gt_result ∈ correct / wrong / partial / unanswered / ungraded
           gt_result 缺省时由「学生答案 vs 标准答案」按同一套规则现推（会标注 inferred）。

环境：脚本强制 VERDICT_CACHE=0（排除缓存干扰）并在启动时断言。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# ---- 1. 环境：必须在 import app.* 之前把开关定死 ----
os.environ["VERDICT_CACHE"] = "0"
os.environ.setdefault("GRADING_OCR_TIMEOUT", "180")

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = BACKEND.parent

# 本地化安装包里的 .env 带着可用的 AI 密钥；云端 .env 没有 DASHSCOPE_API_KEY。
# 只补「缺什么补什么」，不覆盖已有环境变量。
_FALLBACK_ENVS = [
    PROJECT_ROOT / "backend" / ".env",
    Path(r"D:/叙阅本地化安装包_20261116/app/.env"),
]
_KEYS_WANTED = (
    "DASHSCOPE_API_KEY", "BAIDU_API_KEY", "BAIDU_SECRET_KEY",
    "QWEN_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
)


def _load_fallback_env() -> list[str]:
    used = []
    for env_path in _FALLBACK_ENVS:
        if not env_path.is_file():
            continue
        for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k in _KEYS_WANTED and v and not os.environ.get(k):
                os.environ[k] = v
                used.append(str(env_path))
    return used


# ---- 2. 读取链路埋点（只包函数，不改逻辑） ----
import threading

_TLS = threading.local()


def _cur_slot():
    return getattr(_TLS, "slot", None)


def _set_cur_slot(v):
    _TLS.slot = v


def _instrument() -> None:
    from app.grading import answer_key_grading as akg
    from app.grading import verdict_cache as vc

    def wrap(mod, attr, tag, *, page_level=False, hit_only=False, memoize=False):
        """包一层记录调用；page_level=True 记到整页事件而不是当前题。

        memoize=True：同一 (图片, regions) 只真调一次。业务里整页涂卡 OCR 是「每个
        grade_paper_by_answer_key 调用一次」，本脚本逐块调用会把网络请求放大 N 倍，
        纯测速噪声——用缓存把开销还原成线上的「一页一次」。
        """
        orig = getattr(mod, attr, None)
        if orig is None:
            return None
        memo: dict = {}

        def wrapped(*a, **kw):
            mkey = (str(a[0]), repr(a[1:]) if len(a) > 1 else "")
            if memoize and mkey in memo:
                return memo[mkey]
            t0 = time.time()
            result = orig(*a, **kw)
            dt = round(time.time() - t0, 2)
            if memoize:
                memo[mkey] = result
            hit = result is not None and result not in ({}, [], "")
            ev = {"tag": tag, "secs": dt, "ok": bool(hit)}
            if hit_only and not hit:
                return result  # 缓存未命中不记，避免把「查了但没中」说成「命中」
            slot = _cur_slot()
            if slot is not None:
                # page_level：整页涂卡 OCR 一页只真跑一次（memoize），之后每槽都只是
                # 复用同一份结果。记进 page_ocr 而不是 readers，呈现时单独说明。
                if page_level:
                    slot["page_ocr"] = ev
                else:
                    slot["readers"].append(ev)
            return result

        wrapped.__wrapped__ = orig
        wrapped.__name__ = getattr(orig, "__name__", attr)
        setattr(mod, attr, wrapped)
        return wrapped

    wrap(akg, "_omr_choice_answer", "OMR")
    wrap(akg, "_ocr_choice_answers", "百度OCR", page_level=True, memoize=True)  # 一页一次
    wrap(akg, "_vl_read_choice_answer", "千问VL读卡")
    wrap(akg, "_ai_grade_subjective", "千问VL判分")
    wrap(akg, "extract_student_answer", "纯VL抽取")
    # answer_key_grading 内部 `from ... import lookup_block` 是函数内局部导入，
    # 改 verdict_cache 模块属性即可生效；只有真返回命中行才记「缓存命中」。
    wrap(vc, "lookup_block", "缓存命中", hit_only=True)


def _assert_cache_off() -> None:
    from app.grading.verdict_cache import cache_enabled

    if cache_enabled():
        raise SystemExit("VERDICT_CACHE 未关闭，诊断结果会被缓存污染，已中止。")
    if os.environ.get("VERDICT_CACHE") != "0":
        raise SystemExit("VERDICT_CACHE 环境变量异常，已中止。")


# ---- 3. 单页判分（带逐题计时与来源记录） ----
def _pdf_first_page(path: str, out_png: Path, dpi: int = 150) -> str:
    """PDF → 首页 PNG。已有 PNG 直接复用（同一个对开页会被同一场多张卷共用）。"""
    from app.grading import doc_convert

    if out_png.is_file():
        return str(out_png)
    images = doc_convert.pdf_to_images(path, dpi=dpi)
    if not images:
        raise RuntimeError(f"PDF 无页: {path}")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(out_png)
    return str(out_png)


def _layout_for(path: str, cache_dir: Path, layout_cache: dict, page_no: int, name: str) -> dict:
    """对模板页跑一次百度切卷 → 页面布局（同一进程内缓存，多张卷共用）。"""
    key = str(page_no)
    if key in layout_cache:
        return layout_cache[key]
    from app.grading.manual_grading import baidu_paper_cut, build_manual_layout_page

    image_path = _pdf_first_page(path, cache_dir / f"p{page_no}.png")
    raw_path = cache_dir / f"p{page_no}_cut.json"
    if raw_path.is_file():
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        raw = baidu_paper_cut(image_path)
        raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    layout = build_manual_layout_page(
        raw, page_no=page_no, filename=name, image_url="", image_path=image_path
    )
    layout_cache[key] = layout
    return layout


def _shift_layout_numbers(layout: dict, offset: int) -> dict:
    """把页内题号 1..N 折算成全卷题号（+offset），与线上 reference 切题同口径。

    线上 api_prepare_manual_layout 对 P2/P3/P4 会累加 number_offset（注释：「第 2 页
    第 1 题=第 14 题」）。诊断脚本走百度切卷，必须补上这一步，否则第 2 页题号从 1
    重排、标准答案 key 全部错位——这是脚本侧的还原，不是业务缺陷。
    """
    if not offset:
        return layout
    out = {**layout, "questions": []}
    for q in layout.get("questions") or []:
        if not isinstance(q, dict):
            continue
        old_no = int(q.get("display_no") or 0)
        new_no = old_no + offset
        slots = []
        for si, s in enumerate(q.get("answer_slots") or [], start=1):
            if not isinstance(s, dict):
                continue
            slots.append(
                {
                    **s,
                    "slot_id": f"p{layout.get('page_no')}-q{new_no}-s{si}",
                    "label": f"{new_no}_{si}",
                    "order": si,
                }
            )
        out["questions"].append(
            {**q, "display_no": new_no, "question_id": f"p{layout.get('page_no')}-q{new_no}",
             "answer_slots": slots}
        )
    return out


def grade_paper(exam: dict, paper: dict, answer_key: dict, work_dir: Path, log) -> dict:
    from app.grading.answer_key_grading import grade_paper_by_answer_key
    from app.grading.manual_grading import manual_layout_blocks_for_image

    layout_cache = exam.setdefault("_layout_cache", {})
    cache_dir = work_dir / exam["_safe"]
    rows = []
    page_total = len(paper.get("pages") or [])
    for page_idx, page_pdf in enumerate(paper.get("pages") or [], start=1):
        # 模板固定用第 1 页的布局，其余页用各自对开页里对应的模板页（P2/P3/P4）
        tmpl_pdf = str(_resolve(exam["template_pages"][page_idx - 1]))
        layout = _layout_for(tmpl_pdf, cache_dir, layout_cache, page_idx, f"p{page_idx}")
        # 全卷题号偏移：第 2 页起 display_no 要接上一页最大题号（与线上 reference 同口径）
        offset = 0
        for prev in range(1, page_idx):
            prev_tmpl = str(_resolve(exam["template_pages"][prev - 1]))
            prev_layout = _layout_for(prev_tmpl, cache_dir, layout_cache, prev, f"p{prev}")
            offset += max(
                [0] + [int(q.get("display_no") or 0) for q in prev_layout.get("questions") or []]
            )
        layout = _shift_layout_numbers(layout, offset)
        student_png = _pdf_first_page(
            str(_resolve(page_pdf)), cache_dir / f"stu_{paper['_id']}_p{page_idx}.png"
        )
        blocks, _size = manual_layout_blocks_for_image(layout, student_png)

        akg = sys.modules["app.grading.answer_key_grading"]
        # 包一层 grade_paper_by_answer_key 的块循环：逐题记录来源与耗时
        slot_records = {}
        original_blocks = blocks

        t_page = time.time()
        for b in original_blocks:
            b["_diag_begin"] = True
        # 逐题计时/来源无法在函数内插入点（不改业务逻辑），改用「整页计时 + 事后按
        # readers 归属」：把每题的 readers 通过全局 hook 记录。
        page_decisions = _run_with_trace(
            grade_paper_by_answer_key, student_png, blocks, answer_key, exam.get("subject")
        )
        page_secs = round(time.time() - t_page, 2)

        for idx, b in enumerate(original_blocks):
            slot_id = str(b.get("slot_id") or f"slot-{idx + 1}")
            tr = b.pop("_diag_readers", [])
            rows.append(
                {
                    "page": page_idx,
                    "slot_id": slot_id,
                    "label": b.get("label") or f"{b.get('index')}_{b.get('sub_index')}",
                    "index": b.get("index"),
                    # 与业务同一判定口径：kind=="choice" 或带 choice_options 都走选择题分支
                    "kind": "choice" if (b.get("kind") == "choice" or b.get("choice_options")) else "",
                    "question_type": b.get("question_type") or b.get("type"),
                    "expected": b.get("expected_answer"),
                    "student_answer": b.get("student_answer"),
                    "decision": (page_decisions or {}).get(slot_id),
                    "readers": tr,
                    "reader_ev": b.pop("_diag_reader_ev", []),
                    "read_uncertain": bool(b.get("read_uncertain")),
                    "ai_grade": bool(b.get("ai_grade")),
                    "max_score": b.get("max_score"),
                    "reason": (b.get("reason") or "")[:120],
                    "page_secs_total": page_secs,
                    "page_slot_count": len(original_blocks),
                    "page_avg_secs": round(page_secs / max(1, len(original_blocks)), 2),
                }
            )
        log(f"    P{page_idx}/{page_total} 题槽 {len(original_blocks)} 个，整页 {page_secs}s")
    return {"paper_id": paper.get("id") or paper.get("_id"), "pages": page_total, "rows": rows}


def _run_with_trace(fn, image_path, blocks, answer_key, subject):
    """在 grade_paper_by_answer_key 的每条读链路外挂来源记录。

    做法：把 blocks 里每个块的 slot_id 与当前读链绑定——grade_paper_by_answer_key 是
    顺序遍历 blocks 的，而 _CURRENT['slot'] 需要知道「现在是第几个块」。这里不改它的
    实现，而是用读取函数被调用时**最近一次**赋值的块做归属：因此需要在进入前把
    _CURRENT 指向当前块。为保持「不改业务逻辑」，采用最稳妥的方式——逐块单独调用。
    """
    # 逐块调用：每次只传一个块，来源归属 100% 准确，且判分结果与整卷调用一致
    # （函数内部无跨块状态，仅末尾 _apply_answer_set_rule 需要整卷块，见下）。
    decisions = {}
    akg = sys.modules["app.grading.answer_key_grading"]
    set_rule = getattr(akg, "_apply_answer_set_rule", None)
    for b in blocks:
        slot_id = str(b.get("slot_id") or "")
        slot = {"readers": []}
        _set_cur_slot(slot)
        try:
            d = fn(image_path, [b], answer_key, subject)
        finally:
            _set_cur_slot(None)
        tags = [ev["tag"] for ev in slot["readers"]]
        if slot.get("page_ocr"):
            tags.append(slot["page_ocr"]["tag"])
        b["_diag_readers"] = list(dict.fromkeys(tags))
        b["_diag_reader_ev"] = (list(slot["readers"]) +
                                ([slot["page_ocr"]] if slot.get("page_ocr") else []))
        if isinstance(d, dict):
            decisions.update(d)

    # 整卷的「答案集合无序比对」规则（多空题空序不同也算对）在逐块模式下会失效，
    # 诊断脚本显式补跑一次，保证结论与线上一致。
    if callable(set_rule):
        try:
            set_rule(blocks, decisions)
        except Exception as e:
            print(f"  [warn] answer_set_rule 补跑失败: {e}")
    return decisions


# ---- 4. 与 ground truth 对比 ----
_STATUS_ALIAS = {
    "correct": "correct", "对": "correct", "正确": "correct",
    "wrong": "wrong", "错": "wrong", "错误": "wrong",
    "partial": "partial", "半对": "partial",
    "unanswered": "unanswered", "未作答": "unanswered", "空白": "unanswered",
    "ungraded": "ungraded", "未判": "ungraded",
}


_SOURCE_LABEL = {
    "OMR": "OMR涂卡",
    "百度OCR": "百度OCR",
    "千问VL读卡": "千问VL读卡",
    "千问VL判分": "千问VL判分",
    "纯VL抽取": "千问VL抽取",
    "缓存命中": "缓存命中",
    "": "无（未读取/沿用空）",
}


def _norm_status(raw) -> str:
    return _STATUS_ALIAS.get(str(raw or "").strip().lower(), str(raw or "").strip() or "ungraded")


def _infer_gt_result(gt_student, expected) -> str:
    """没有老师判定时，按同一套比对规则现推（会标注 inferred）。"""
    from app.grading.answer_key_grading import match_answers

    if gt_student is None:
        return "unanswered"
    if not expected:
        return "ungraded"
    return {"对": "correct", "错": "wrong", "未作答": "unanswered"}.get(
        match_answers(str(gt_student), str(expected)), "ungraded"
    )


def evaluate(rows: list[dict], gt: dict) -> dict:
    """逐题比 ground truth，产出混淆矩阵/漏批/错判归因。"""
    out_rows = []
    for r in rows:
        label = str(r.get("label") or "")
        has_gt = label in gt
        g = gt.get(label)
        if isinstance(g, dict):
            gt_student = g.get("gt_student")
            gt_result = _norm_status(g.get("gt_result"))
            gt_inferred = not g.get("gt_result")
        elif g is None:
            gt_student, gt_result, gt_inferred = None, "ungraded", True
        else:
            gt_student, gt_result, gt_inferred = str(g), "", True
        if gt_inferred and gt_result in ("", "ungraded") and has_gt:
            gt_result = _infer_gt_result(gt_student, r.get("expected"))

        ai_status = _norm_status((r.get("decision") or {}).get("status"))
        readers = r.get("readers") or []
        evs = [e for e in (r.get("reader_ev") or []) if isinstance(e, dict)]
        # 取「真正读出了东西」的第一级（业务是按 OMR→OCR→VL 顺序逐级回退的）；
        # 全部失败则记最后一级 + 标注失败，便于区分「读失败」与「没调用」。
        ok_tags = [e["tag"] for e in evs if e.get("ok")]
        source = next((x for x in ok_tags if x in _SOURCE_LABEL), "")
        if not source and evs:
            source = evs[-1]["tag"]
        if "缓存命中" in ok_tags:
            source = "缓存命中"

        # 读到的学生答案是否与老师看到的一致（读链是否读错）
        ai_ans = r.get("student_answer")
        read_ok = None
        if gt_student is not None:
            from app.grading.answer_key_grading import normalize_answer

            read_ok = normalize_answer(str(ai_ans or "")) == normalize_answer(str(gt_student or ""))

        verdict = "agree"
        cause = ""
        if not has_gt:
            # GT 里没有这题：不能算「漏批」也不能算「未作答」，单列。
            verdict = "no_gt"
            cause = "ground truth 未标注该槽"
        elif gt_result == "ungraded":
            verdict = "judged_but_not_in_gt"
            cause = "老师未判（不在 ground truth 内）"
        elif ai_status == "ungraded" or not (r.get("decision") or {}).get("status"):
            verdict = "missed"
            cause = _missed_cause(r, source)
        elif ai_status != gt_result:
            verdict = "mismatch"
            cause = _mismatch_cause(r, gt_student, read_ok, source, gt_result)

        out_rows.append(
            {
                **r,
                "source": source,
                "source_label": _SOURCE_LABEL.get(source, source),
                "gt_student": gt_student,
                "gt_result": gt_result,
                "gt_inferred": bool(gt_inferred),
                "read_ok": read_ok,
                "ai_status": ai_status,
                "verdict": verdict,
                "cause": cause,
            }
        )
    return {"rows": out_rows}


def _missed_cause(row: dict, source: str) -> str:
    if row.get("read_uncertain"):
        return "读不准（VL 自报不确定）→ 主动弃判"
    readers = row.get("readers") or []
    if not readers:
        return "标准答案未命中该槽（key 对不上 / 该槽无标准答案）"
    if row.get("expected") and not str(row.get("student_answer") or "").strip():
        return f"{_SOURCE_LABEL.get(source, source)} 读出空 → 判为未作答前被跳过"
    return f"{_SOURCE_LABEL.get(source, source)} 读取失败 → 保持未判"


def _mismatch_cause(row: dict, gt_student, read_ok, source, gt_result) -> str:
    ai_ans = str(row.get("student_answer") or "").strip()
    expected = str(row.get("expected") or "").strip().upper()

    if row.get("expected") in (None, ""):
        return "答案 key 缺失"
    if read_ok is False:
        return f"{_SOURCE_LABEL.get(source, source)} 读错（读到 {ai_ans!r}，老师读 {gt_student!r}）"
    if row.get("read_uncertain"):
        return "读不准（VL 自报不确定）"
    if source == "缓存命中":
        return "缓存命中（旧判分）"
    # 老师认为空白、AI 却读到并判了：多数是 VL 把相邻题/印刷题号读进来了
    if gt_result == "unanswered" and ai_ans:
        return f"学生未作答但 VL 读出了内容（{ai_ans!r}）→ 判错"
    return f"比对逻辑判错（来源 {_SOURCE_LABEL.get(source, source)}，读到答案与老师一致）"


# ---- 5. 汇总输出 ----
def summarize(rows: list[dict]) -> dict:
    def qtype(r):
        kind = str(r.get("kind") or "")
        if kind == "choice":
            return "选择题"
        return "填空/主观题"

    matrix = defaultdict(Counter)
    for r in rows:
        if r["gt_result"] == "ungraded":
            continue
        matrix[qtype(r)][(r["gt_result"], r["ai_status"])] += 1

    missed = [r for r in rows if r["verdict"] == "missed"]
    mismatch = [r for r in rows if r["verdict"] == "mismatch"]
    cause_counter = Counter(r["cause"] for r in mismatch)
    source_counter = Counter(r["source_label"] for r in rows if r.get("readers"))
    return {
        "matrix": {k: dict(v) for k, v in matrix.items()},
        "missed": missed,
        "mismatch": mismatch,
        "cause_counter": cause_counter,
        "source_counter": source_counter,
    }


def fmt_matrix(matrix: dict) -> list[str]:
    cols = ["correct", "wrong", "partial", "unanswered"]
    head = {"correct": "对", "wrong": "错", "partial": "半对", "unanswered": "未作答"}
    lines = []
    for qt, cells in matrix.items():
        lines.append(f"  【{qt}】")
        lines.append("    GT\\AI      " + "".join(f"{head[c]:>8}" for c in cols) + "   未判" + "  合计")
        totals = Counter()
        for (gt, _ai), n in cells.items():
            totals[gt] += n
        ungraded_by_gt = Counter()
        for (gt, ai), n in cells.items():
            if ai == "ungraded":
                ungraded_by_gt[gt] += n
        for gt in cols:
            row = "".join(f"{cells.get((gt, c), 0):>9}" for c in cols)
            lines.append(f"    {head[gt]:<10}{row}{ungraded_by_gt[gt]:>7}{totals[gt]:>6}")
    return lines


_SECTION_LEAD_RE = re.compile(r"^(\d{1,2})\s*[.、．]\s*(\d{2,3})\s*[.、．]\s*(\S.*)$")


def _preprocess_key_text(text: str, max_q: int) -> tuple[str, list[str]]:
    """把「大题号.小题号.答案」的行改写成「小题号.答案」，再交给业务解析器。

    真实答案文件（英语 P2/科学）常写成：
        3.16.E      ← 第三大题第 16 题答案 E
        4.21.live   ← 第四大题第 21 题 live
    业务解析器 _ENTRY_RE 只认「题号_空号_答案」，会把 16.E 当成「第 3 题答案」，
    于是第 3/4 题被覆盖、16~30 题全部缺失——这是真实故障，不是本脚本的假设。
    诊断侧只在**喂进解析器之前**做行改写，不改业务代码。
    """
    notes, out = [], []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        m = _SECTION_LEAD_RE.match(line)
        if m and int(m.group(2)) <= max_q and int(m.group(1)) < int(m.group(2)):
            rewritten = f"{m.group(2)}.{m.group(3).strip()}"
            notes.append(f"{line!r} → {rewritten!r}")
            out.append(rewritten)
        else:
            out.append(raw)
    return "\n".join(out), notes


def _resolve(path_str: str) -> Path:
    """清单里的相对路径统一按「迁移包根目录」解析（不是 backend）。"""
    p = Path(path_str)
    if p.is_absolute():
        return p
    cand = PROJECT_ROOT / p
    if cand.exists():
        return cand
    return BACKEND / p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default="diag_out")
    ap.add_argument("--folder", default="", help="只跑清单里的某一场（按 name 或子串匹配）")
    ap.add_argument("--max-papers", type=int, default=0, help="每场最多跑几张卷（0=全部）")
    ap.add_argument("--deadline-min", type=float, default=0, help="整体时限（分钟），到时停止并输出已完成部分")
    ap.add_argument("--replay", action="store_true", help="不重新判分，复用 diagnose_raw.json 重算报告")
    args = ap.parse_args()

    used = _load_fallback_env()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = BACKEND / manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = BACKEND / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)

    def log(msg):
        print(msg, flush=True)

    log("=" * 78)
    log("批改诊断（第 2 步）")
    log(f"权限缓存 VERDICT_CACHE={os.environ.get('VERDICT_CACHE')}（强制 0）")
    if used:
        log(f"密钥回填自: {sorted(set(used))}")
    log(f"清单: {manifest_path}")
    log(f"输出: {out_dir}")
    log("=" * 78)

    replay_mode = bool(args.replay and (out_dir / "diagnose_raw.json").is_file())
    if replay_mode:
        log("[replay] 跳过埋点与模型调用，只用已保存结果重算报告")
    else:
        _instrument()
        _assert_cache_off()

    t_all = time.time()
    deadline = (args.deadline_min * 60) if args.deadline_min else 0
    results = []
    truncated = False
    raw_path = out_dir / "diagnose_raw.json"

    # --replay：不再调模型，直接用上次保存的逐槽原始结果 + 本轮 ground truth 重算报告
    if args.replay and raw_path.is_file():
        saved = {r["paper_id"]: r for r in json.loads(raw_path.read_text(encoding="utf-8"))}
        gts = {}
        for exam in manifest.get("exams") or []:
            if args.folder and args.folder not in str(exam.get("name") or ""):
                continue
            for pp in exam.get("papers") or []:
                gts[str(pp.get("id"))] = pp.get("ground_truth") or {}
        for pid, res in saved.items():
            res["rows"] = evaluate(res.get("rows") or [], gts.get(pid, {}))["rows"]
        results = list(saved.values())
        log(f"[replay] 复用 {len(results)} 张卷的逐槽结果，不重新调用模型")

    for exam in ([] if replay_mode else (manifest.get("exams") or [])):
        name = str(exam.get("name") or "")
        if args.folder and args.folder not in name:
            continue
        exam["_safe"] = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40]
        log(f"\n### {name}（{exam.get('subject')}）")

        key_cache = work / exam["_safe"] / "answer_key.json"
        max_q = int(exam.get("max_question") or 100)
        from app.grading.answer_key_grading import (
            extract_answer_key_text_from_document,
            parse_answer_key_text,
        )
        if key_cache.is_file():
            answer_key = json.loads(key_cache.read_text(encoding="utf-8"))
        else:
            text = exam.get("answer_key_text")
            if not text:
                parts = []
                for f in exam.get("answer_key_files") or []:
                    parts.append(extract_answer_key_text_from_document(str(_resolve(f))))
                text = "\n".join(parts)
                (work / exam["_safe"]).mkdir(parents=True, exist_ok=True)
                (work / exam["_safe"] / "answer_key_raw.txt").write_text(text, encoding="utf-8")
            # 诊断侧预处理：还原「大题号.小题号.答案」被吞掉的题号（不改业务代码）
            fixed_text, pre_notes = _preprocess_key_text(text, max_q)
            if pre_notes:
                (work / exam["_safe"] / "answer_key_preprocess.txt").write_text(
                    "\n".join(pre_notes), encoding="utf-8"
                )
                log(f"  答案文本预处理 {len(pre_notes)} 行（题号错位已还原，详见 answer_key_preprocess.txt）")
            answer_key = parse_answer_key_text(fixed_text or "")
            key_cache.write_text(json.dumps(answer_key, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  标准答案 {len(answer_key)} 条：{dict(list(answer_key.items())[:6])} ...")
        missing = [str(i) for i in range(1, max_q + 1) if f"{i}_1" not in answer_key]
        if missing and len(missing) < max_q:
            log(f"  [warn] 答案 key 缺题号：{','.join(missing[:20])}{' ...' if len(missing) > 20 else ''}")

        papers = exam.get("papers") or []
        if args.max_papers:
            papers = papers[: args.max_papers]
        for pi, paper in enumerate(papers, start=1):
            if deadline and (time.time() - t_all) > deadline:
                log("  ! 到达时限，停止后续卷")
                truncated = True
                break
            paper["_id"] = str(paper.get("id") or f"p{pi}")
            log(f"  -- 卷 {paper['_id']} ({pi}/{len(papers)})")
            try:
                res = grade_paper(exam, paper, answer_key, work, log)
            except Exception as e:
                log(f"    [FAIL] {e}")
                results.append({"exam": name, "subject": exam.get("subject"),
                                "paper_id": paper["_id"], "error": str(e), "rows": []})
                continue
            ev = evaluate(res["rows"], paper.get("ground_truth") or {})
            results.append({"exam": name, "subject": exam.get("subject"),
                            "paper_id": paper["_id"], "pages": res["pages"], "rows": ev["rows"]})
        if truncated:
            break

    # ---- 输出 ----
    report_lines = []
    all_rows = [r for res in results for r in (res.get("rows") or [])]

    report_lines.append("# 批改诊断报告（第 2 步）")
    report_lines.append("")
    report_lines.append(f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"- 判分缓存：VERDICT_CACHE=0（已断言关闭）")
    report_lines.append(f"- 场次：{len({r['exam'] for r in results})}，卷：{len(results)}，作答区：{len(all_rows)}")
    report_lines.append("")

    for res in results:
        rows = res.get("rows") or []
        if not rows:
            report_lines.append(f"## {res['exam']} · {res['paper_id']} —— 失败：{res.get('error')}")
            report_lines.append("")
            continue
        report_lines.append(f"## {res['exam']} · {res['paper_id']}")
        report_lines.append("")
        report_lines.append("| 题号 | 题型 | 标准答案 | 学生答案来源 | 读到的答案 | 判定 | GT | 结论 | 归因 | 耗时/题 |")
        report_lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            dec = _norm_status((r.get("decision") or {}).get("status"))
            verdict_cn = {"agree": "一致", "missed": "**漏批**", "mismatch": "**==错判==**",
                          "judged_but_not_in_gt": "GT 外"}.get(r["verdict"], r["verdict"])
            report_lines.append(
                "| {label} | {kind} | {exp} | {src} | {ans} | {dec} | {gt} | {v} | {cause} | {sec}s |".format(
                    label=r.get("label"),
                    kind="选择" if r.get("kind") == "choice" else "填空",
                    exp=(r.get("expected") or "").replace("|", "\\|")[:28],
                    src=r.get("source_label"),
                    ans=str(r.get("student_answer") or "").replace("|", "\\|").replace("\n", " ")[:24],
                    dec=dec or "未判",
                    gt=r.get("gt_result"),
                    v=verdict_cn,
                    cause=(r.get("cause") or "").replace("|", "\\|")[:40],
                    sec=r.get("page_avg_secs"),
                )
            )
        report_lines.append("")

    s = summarize(all_rows)
    report_lines.append("## 汇总：混淆矩阵（GT 行 × AI 列）")
    report_lines.extend(fmt_matrix(s["matrix"]))
    report_lines.append("")

    report_lines.append(f"## 漏批清单（{len(s['missed'])} 题）")
    if s["missed"]:
        report_lines.append("| 卷 | 题号 | 标准答案 | 来源 | 读到的答案 | 归因 |")
        report_lines.append("|---|---|---|---|---|---|")
        for r in s["missed"]:
            owner = next((x["paper_id"] for x in results if r in (x.get("rows") or [])), "")
            report_lines.append(
                f"| {owner} | {r.get('label')} | {r.get('expected')} | {r.get('source_label')} | "
                f"{str(r.get('student_answer') or '')[:20]} | {r.get('cause')} |"
            )
    else:
        report_lines.append("（无）")
    report_lines.append("")

    report_lines.append(f"## 错判归因（{len(s['mismatch'])} 题）")
    if s["mismatch"]:
        for cause, n in s["cause_counter"].most_common():
            report_lines.append(f"- {n} 题 · {cause}")
        report_lines.append("")
        report_lines.append("| 卷 | 题号 | 标准答案 | AI 判 | GT | 来源 | 读到的答案 | 老师读到的 |")
        report_lines.append("|---|---|---|---|---|---|---|---|")
        for r in s["mismatch"]:
            owner = next((x["paper_id"] for x in results if r in (x.get("rows") or [])), "")
            report_lines.append(
                f"| {owner} | {r.get('label')} | {r.get('expected')} | {r.get('ai_status')} | "
                f"{r.get('gt_result')} | {r.get('source_label')} | {str(r.get('student_answer') or '')[:20]} | "
                f"{r.get('gt_student')} |"
            )
    else:
        report_lines.append("（无）")
    report_lines.append("")

    report_lines.append("## 读数来源分布")
    for src, n in s["source_counter"].most_common():
        report_lines.append(f"- {src}: {n} 题")
    report_lines.append("")

    # OMR 分级统计：这是「选择题读卡到底废了几级」的直接证据
    choice = [r for r in all_rows if r.get("kind") == "choice"]
    if choice:
        omr_called = 0
        omr_ok = 0
        ocr_called = 0
        ocr_ok = 0
        vl_fallback = 0
        for r in choice:
            evs = {e["tag"]: e for e in (r.get("reader_ev") or []) if isinstance(e, dict)}
            if "OMR" in evs:
                omr_called += 1
                if evs["OMR"].get("ok"):
                    omr_ok += 1
            if "百度OCR" in evs:
                ocr_called += 1
                if evs["百度OCR"].get("ok"):
                    ocr_ok += 1
            if "千问VL读卡" in evs and evs["千问VL读卡"].get("ok"):
                vl_fallback += 1
        report_lines.append("## 选择题读卡分级（关键证据）")
        report_lines.append(f"- 选择题槽位：{len(choice)} 个")
        report_lines.append(f"- OMR 调用 {omr_called} 次，**成功 {omr_ok} 次**（成功率 {round(100.0 * omr_ok / max(1, omr_called), 1)}%）")
        report_lines.append(f"- 百度OCR 涂卡调用 {ocr_called} 次，成功 {ocr_ok} 次")
        report_lines.append(f"- 最终靠 千问VL读卡 兜底读出：{vl_fallback} 题（{round(100.0 * vl_fallback / len(choice), 1)}%）")
        report_lines.append("")
        if omr_ok == 0:
            report_lines.append(
                "> **OMR 涂黑检测在这批卷上 0 命中**：整卷选择题全部落到 VL 兜底读卡。"
                "这就是「选择题读错」的源头——不是 OCR 读错，而是第一级（本地墨迹 OMR）整级失效。"
            )
            report_lines.append("")

    # 「学生空白 vs AI 判了内容」单列：这是最容易让家长投诉的错判类型
    blank_but_judged = [r for r in all_rows if r.get("gt_result") == "unanswered"
                        and str(r.get("student_answer") or "").strip()
                        and _norm_status((r.get("decision") or {}).get("status")) != "unanswered"]
    if blank_but_judged:
        report_lines.append(f"## 学生空白但 AI 读出了内容（{len(blank_but_judged)} 题，最易引发投诉）")
        for r in blank_but_judged[:20]:
            report_lines.append(
                f"- {r.get('label')}：标准答案 {r.get('expected')}，AI 读到 {str(r.get('student_answer'))[:24]!r}"
                f" 来源={r.get('source_label')}"
            )
        report_lines.append("")

    # 读链耗时：区分「整页一次性开销」与「逐题开销」
    choice_rows = [r for r in all_rows if r.get("kind") == "choice"]
    other_rows = [r for r in all_rows if r.get("kind") != "choice"]
    page_secs = sorted({(r.get("page_secs_total") or 0) for r in all_rows})
    report_lines.append("## 耗时")
    report_lines.append(f"- 整页耗时（含切题后逐题判分，逐页）：{page_secs} s")
    if choice_rows:
        report_lines.append(
            f"- 选择题 {len(choice_rows)} 题，平均 {round(sum(r.get('page_avg_secs') or 0 for r in choice_rows) / len(choice_rows), 2)} s/题（页均摊）"
        )
    if other_rows:
        report_lines.append(
            f"- 填空/主观 {len(other_rows)} 题，平均 {round(sum(r.get('page_avg_secs') or 0 for r in other_rows) / len(other_rows), 2)} s/题（页均摊）"
        )
    report_lines.append("")
    if truncated:
        report_lines.append("> 注意：到达 --deadline-min 时限，未跑完所有卷。")
    report_lines.append(f"\n总耗时：{round(time.time() - t_all, 1)}s")

    report = "\n".join(report_lines)
    (out_dir / "diagnose_report.md").write_text(report, encoding="utf-8")
    (out_dir / "diagnose_raw.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + report)
    print(f"\n已写出：{out_dir / 'diagnose_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
