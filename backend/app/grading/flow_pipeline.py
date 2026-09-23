# -*- coding: utf-8 -*-
"""流水阅卷切割归类流水线。

物理裁图 + 按题归类 + 「学号--题号」命名 + 完整卷按学号归档，全部基于
现有切题模板（.manual_layout.json）。在后台线程跑，进程内 job state 仿 _scan_state。
"""
from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from app.database import SessionLocal
from app.grading.flow_paths import (
    flow_crops_dir,
    flow_meta_path,
    flow_papers_dir,
    flow_template_dir,
    sanitize_identity,
)
from app.grading.manual_grading import load_manual_layout, manual_layout_blocks_for_image
from app.grading.reference_vlm_grading import _save_crop
from app.grading.router import _ensure_img_in_folder
from app.grading.user_paths import correct_docs_dir, run_with_grading_user
from app.grading.wrong_question_db import _load_class_context, _norm_identity
from app.models.flow_grading import (
    FlowArbitration,
    FlowAssignment,
    FlowBatch,
    FlowItem,
    FlowQuestion,
    FlowReview,
)

_SOURCE_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
_SOURCE_EXTS = _SOURCE_IMAGE_EXTS | {".pdf"}
_STANDARD_ANSWER_RE = re.compile(r"^标准答案(?:_\d+)?$")
_PAGE_SUFFIX_RE = re.compile(r"^(?P<name>.+)_(?P<page>\d+)$")

_cut_jobs: dict[str, dict] = {}
_cut_lock = threading.Lock()


def _natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def _stem(filename: str) -> str:
    return Path(str(filename or "")).stem


def _paper_page_no(filename: str) -> int:
    m = _PAGE_SUFFIX_RE.match(_stem(filename))
    if not m:
        return 1
    try:
        return max(1, int(m.group("page")))
    except Exception:
        return 1


def _paper_identity(filename: str) -> str:
    m = _PAGE_SUFFIX_RE.match(_stem(filename))
    return (m.group("name") if m else _stem(filename)).strip()


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


# ── 花名册 / 学号解析（可插拔：roster 默认，barcode 预留）────────────────

def build_roster(class_ids: list) -> list[dict]:
    """把若干班级合并为全局花名册（含 student_number）。"""
    merged: dict[str, dict] = {}
    for cid in class_ids or []:
        _, rows = _load_class_context(str(cid))
        for s in rows or []:
            if not isinstance(s, dict):
                continue
            key = str(s.get("id") or "") or f"{s.get('name')}@{s.get('student_number')}"
            merged.setdefault(key, s)
    return list(merged.values())


def _resolved(s: dict, matched_by: str) -> dict:
    return {
        "student_id": s.get("id"),
        "name": str(s.get("name") or "").strip(),
        "student_number": str(s.get("student_number") or "").strip(),
        "matched_by": matched_by,
        "matched": True,
    }


def resolve_student(paper_name: str, roster: list[dict]) -> dict:
    """按文件名主名匹配学生，返回含 student_number（区别于 _infer_student_from_paper_name 剥离学号）。"""
    identity = _paper_identity(paper_name)
    norm = _norm_identity(identity)
    fallback = {
        "student_id": None,
        "name": identity,
        "student_number": "",
        "matched_by": "paper_name",
        "matched": False,
    }
    if not norm or not roster:
        return fallback

    candidates: list[tuple[int, dict, str]] = []
    for s in roster:
        name_norm = _norm_identity(s.get("name"))
        num_norm = _norm_identity(s.get("student_number"))
        if name_norm and norm == name_norm:
            return _resolved(s, "name_exact")
        if num_norm and norm == num_norm:
            return _resolved(s, "student_number_exact")
        if name_norm and len(name_norm) >= 2 and name_norm in norm:
            candidates.append((len(name_norm), s, "name_contains"))
        elif num_norm and len(num_norm) >= 2 and num_norm in norm:
            candidates.append((len(num_norm), s, "student_number_contains"))

    if candidates:
        _, s, matched_by = sorted(candidates, key=lambda x: x[0], reverse=True)[0]
        return _resolved(s, matched_by)
    return fallback


def _identity_key(resolved: dict) -> str:
    num = str(resolved.get("student_number") or "").strip()
    name = str(resolved.get("name") or "").strip()
    return sanitize_identity(num or name or "unknown")


# ── 切割管线 ──────────────────────────────────────────────────────────────

def _flatten_questions(pages: dict) -> list[dict]:
    """把「按页」的切题模板 flatten 成题目列表，题号直接用卷面印刷题号（display_no），不再自编 1..N。"""
    result: list[dict] = []
    used: set[int] = set()
    for page_str in sorted(pages.keys(), key=lambda k: _int_key(k)):
        page = pages[page_str]
        if not isinstance(page, dict):
            continue
        layout_page = page.get("layout") if isinstance(page.get("layout"), dict) else page
        for q in layout_page.get("questions") or []:
            if not isinstance(q, dict):
                continue
            display_no = int(q.get("display_no") or 0)
            # 用原答题卡印刷题号；缺题号或跨页撞号时，退到「页号*1000+序号」保证唯一
            if display_no <= 0 or display_no in used:
                display_no = _int_key(page_str) * 1000 + len(result) + 1
            used.add(display_no)
            slots = [s for s in (q.get("answer_slots") or []) if isinstance(s, dict)]
            slot_ids = [str(s.get("slot_id") or "") for s in slots]
            max_score = round(sum(float(s.get("max_score") or 0) for s in slots), 2)
            result.append(
                {
                    "global_no": display_no,
                    "page_no": _int_key(page_str),
                    "display_no": display_no,
                    "slot_ids": slot_ids,
                    "max_score": max_score,
                    "crop_dir": f"q{display_no}",
                }
            )
    return result


def _int_key(k: Any) -> int:
    try:
        return int(k)
    except (TypeError, ValueError):
        return 0


def _union_bbox(blocks: list[dict]) -> Optional[list[int]]:
    boxes = [b.get("bbox") for b in blocks if isinstance(b.get("bbox"), (list, tuple)) and len(b["bbox"]) == 4]
    if not boxes:
        return None
    return [int(min(b[0] for b in boxes)), int(min(b[1] for b in boxes)),
            int(max(b[2] for b in boxes)), int(max(b[3] for b in boxes))]


def _archive_name(identity: str, page_no: int) -> str:
    return f"{identity}.jpg" if page_no <= 1 else f"{identity}_p{page_no}.jpg"


def _write_meta(batch: FlowBatch, source: str) -> None:
    data = {
        "batch_id": batch.id,
        "name": batch.name,
        "subject": batch.subject,
        "grade": batch.grade,
        "review_mode": batch.review_mode,
        "resolver": batch.resolver,
        "source_folder_safe": source,
        "class_ids": _as_list(batch.class_ids_json),
    }
    try:
        flow_meta_path(batch.id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _read_source_answer_key(source: str) -> dict[str, str]:
    """读取源文件夹在「答题卡（参照批改）」里保存的标准答案 {题号_空号: 答案}。"""
    from app.grading.user_paths import grading_history_dir

    path = grading_history_dir() / f"{source}__manual.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    ak = data.get("answer_key") if isinstance(data, dict) else None
    if not isinstance(ak, dict):
        return {}
    answers = ak.get("answers")
    return answers if isinstance(answers, dict) else {}


def _format_standard_answer(answer_key: dict[str, str], question_no: int) -> Optional[str]:
    """把某题的标准答案拼成展示串：单空「A」，多空「1.B 2.D」。"""
    pat = re.compile(rf"^{question_no}_(\d+)$")
    items = []
    for key, val in answer_key.items():
        m = pat.match(str(key))
        if m:
            items.append((int(m.group(1)), str(val).strip()))
    if not items:
        return None
    items.sort(key=lambda x: x[0])
    if len(items) == 1:
        return items[0][1]
    return " ".join(f"{sub}.{val}" for sub, val in items)


def sync_standard_answers(db, batch) -> bool:
    """把源文件夹最新保存的标准答案回填到 FlowQuestion.standard_answer。

    用于「标准答案在切割之后才保存」的场景：切割时 answer_key 尚未存在，
    FlowQuestion.standard_answer 因此为空；老师在批改端 / 管理员打开批次时据此
    自动补齐，无需重切批次。返回源文件夹是否已存在标准答案。
    """
    source = str(batch.source_folder_safe or "").strip()
    if not source:
        return False
    try:
        owner = batch.owner_user_id
        answer_key = (
            run_with_grading_user(owner, _read_source_answer_key, source)
            if owner
            else _read_source_answer_key(source)
        )
    except Exception:
        answer_key = {}
    questions = (
        db.query(FlowQuestion)
        .filter(FlowQuestion.batch_id == batch.id)
        .all()
    )
    changed = False
    for q in questions:
        want = _format_standard_answer(answer_key, q.question_no)
        if want != q.standard_answer:
            q.standard_answer = want
            changed = True
    if changed:
        try:
            db.commit()
        except Exception:
            db.rollback()
    return bool(answer_key)


def _do_cut(batch_id: str) -> None:
    state = _cut_jobs[batch_id]
    db = SessionLocal()
    try:
        batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
        if not batch:
            raise RuntimeError("批次不存在")
        source = str(batch.source_folder_safe or "").strip()
        class_ids = _as_list(batch.class_ids_json)
        if not source:
            raise RuntimeError("批次未设置源文件夹")

        # 幂等重切：先清掉本批次旧的题目/裁图条目/分配/评阅/仲裁，再按最新切题模板重建
        for _model in (FlowReview, FlowArbitration, FlowAssignment, FlowItem, FlowQuestion):
            db.query(_model).filter(_model.batch_id == batch_id).delete(synchronize_session=False)
        db.commit()
        for _dir in (flow_crops_dir(batch_id), flow_papers_dir(batch_id)):
            if _dir.is_dir():
                shutil.rmtree(str(_dir), ignore_errors=True)

        batch.status = "cutting"
        db.commit()

        # 1. 加载切题模板（源文件夹 .manual_layout.json）
        layout = load_manual_layout(source)
        pages = layout.get("pages") if isinstance(layout.get("pages"), dict) else {}
        if not pages:
            raise RuntimeError("源文件夹尚未完成切题（缺 .manual_layout.json）")
        src_layout = correct_docs_dir() / source / ".manual_layout.json"
        if src_layout.is_file():
            shutil.copy2(str(src_layout), str(flow_template_dir(batch_id) / "manual_layout.json"))
        _write_meta(batch, source)

        # 2. 花名册
        roster = build_roster(class_ids)

        # 3. 全局题号（页序 flatten）
        global_questions = _flatten_questions(pages)
        if not global_questions:
            raise RuntimeError("切题模板没有题目")
        gq_by_global: dict[int, float] = {gq["global_no"]: gq["max_score"] for gq in global_questions}
        page_qmap: dict[int, dict[int, int]] = {}
        for gq in global_questions:
            page_qmap.setdefault(gq["page_no"], {})[gq["display_no"]] = gq["global_no"]

        # 建题目行（若源文件夹在「答题卡（参照批改）」里存过标准答案，回填到顶部标准答案框）
        answer_key = _read_source_answer_key(source)
        question_id_by_global: dict[int, str] = {}
        for gq in global_questions:
            gno = gq["global_no"]
            q = FlowQuestion(
                batch_id=batch_id,
                question_no=gno,
                display_label=f"第{gno}题",
                slot_ids_json=gq["slot_ids"],
                max_score=gq["max_score"],
                standard_answer=_format_standard_answer(answer_key, gno),
                crop_dir=gq["crop_dir"],
                status="pending",
                total_items=0,
            )
            db.add(q)
            db.flush()
            question_id_by_global[gno] = q.id
        db.commit()

        # 4. 枚举源卷（跳过标准答案 / meta / 隐藏文件）
        src_dir = correct_docs_dir() / source
        papers = []
        for f in src_dir.iterdir():
            if not f.is_file() or f.suffix.lower() not in _SOURCE_EXTS:
                continue
            if _STANDARD_ANSWER_RE.match(_stem(f.name)):
                continue
            papers.append(f)
        papers.sort(key=lambda p: _natural_key(p.name))
        if not papers:
            raise RuntimeError("源文件夹没有学生答题卡")
        state["total"] = len(papers)

        processed = 0
        for paper in papers:
            resolved = resolve_student(paper.name, roster)
            identity = _identity_key(resolved)
            page_no = _paper_page_no(paper.name)

            img_path = _ensure_img_in_folder(paper, source)
            if img_path is None and paper.suffix.lower() in _SOURCE_IMAGE_EXTS:
                img_path = paper
            if img_path is None:
                state["errors"].append({"paper_name": paper.name, "msg": "无法生成批改图片"})
                continue

            layout_page = pages.get(str(page_no))
            if not isinstance(layout_page, dict):
                state["errors"].append({"paper_name": paper.name, "msg": f"缺 P{page_no} 切题模板"})
                continue
            lp = layout_page.get("layout") if isinstance(layout_page.get("layout"), dict) else layout_page

            # 完整卷归档
            archive_name = _archive_name(identity, page_no)
            archive_dest = flow_papers_dir(batch_id) / archive_name
            try:
                with Image.open(str(img_path)) as im:
                    im.convert("RGB").save(str(archive_dest), quality=92)
            except Exception as e:
                state["errors"].append({"paper_name": paper.name, "msg": f"归档失败: {e}"})

            # 逐题裁图
            with Image.open(str(img_path)) as img:
                blocks, _target = manual_layout_blocks_for_image(lp, str(img_path))
                by_q: dict[int, list[dict]] = {}
                for b in blocks:
                    by_q.setdefault(int(b.get("index") or 1), []).append(b)
                for display_no, qblocks in by_q.items():
                    global_no = (page_qmap.get(page_no) or {}).get(display_no)
                    if global_no is None or global_no not in question_id_by_global:
                        continue
                    union = _union_bbox(qblocks)
                    if union is None:
                        state["errors"].append({"paper_name": paper.name, "msg": f"第{global_no}题无作答区坐标"})
                        continue
                    crop_name = f"{identity}--{global_no}.jpg"
                    crop_path = flow_crops_dir(batch_id) / f"q{global_no}" / crop_name
                    if not _save_crop(img, union, crop_path, pad=8):
                        state["errors"].append({"paper_name": paper.name, "msg": f"第{global_no}题裁图失败"})
                        continue
                    db.add(
                        FlowItem(
                            batch_id=batch_id,
                            question_id=question_id_by_global[global_no],
                            student_id=resolved.get("student_id"),
                            student_name=resolved.get("name"),
                            student_number=resolved.get("student_number"),
                            paper_name=paper.name,
                            source_page_no=page_no,
                            crop_path=f"crops/q{global_no}/{crop_name}",
                            full_paper_path=f"papers/{archive_name}",
                            bbox_json=union,
                            max_score=gq_by_global.get(global_no, 0),
                            status="pending",
                        )
                    )

            processed += 1
            state["processed"] = processed
            if processed % 20 == 0:
                db.commit()
        db.commit()

        # 回填题目 total_items 与批次
        for gq in global_questions:
            cnt = (
                db.query(FlowItem)
                .filter(FlowItem.question_id == question_id_by_global[gq["global_no"]])
                .count()
            )
            db.query(FlowQuestion).filter(FlowQuestion.id == question_id_by_global[gq["global_no"]]).update(
                {"total_items": cnt}
            )
        batch.total_papers = processed
        batch.status = "assigning"
        db.commit()
        state["status"] = "done"
    except Exception as e:
        db.rollback()
        try:
            db.query(FlowBatch).filter(FlowBatch.id == batch_id).update({"status": "created"})
            db.commit()
        except Exception:
            pass
        state["status"] = "error"
        state["error_message"] = str(e)
    finally:
        db.close()


def start_cut(batch_id: str) -> dict:
    db = SessionLocal()
    try:
        batch = db.query(FlowBatch).filter(FlowBatch.id == batch_id).first()
        if not batch:
            raise RuntimeError("批次不存在")
        owner = batch.owner_user_id
    finally:
        db.close()

    with _cut_lock:
        state = _cut_jobs.setdefault(
            batch_id,
            {"status": "idle", "processed": 0, "total": 0, "errors": [], "error_message": None},
        )
        if state.get("status") == "running":
            return {"status": "running", "batch_id": batch_id}
        state["status"] = "running"
        state["processed"] = 0
        state["total"] = 0
        state["errors"] = []
        state["error_message"] = None

    thread = threading.Thread(target=_cut_worker, args=(batch_id, owner or ""), daemon=True)
    thread.start()
    return {"status": "started", "batch_id": batch_id}


def _cut_worker(batch_id: str, owner_user_id: str) -> None:
    try:
        if owner_user_id:
            run_with_grading_user(owner_user_id, _do_cut, batch_id)
        else:
            _do_cut(batch_id)
    except Exception as e:
        state = _cut_jobs.setdefault(batch_id, {})
        state["status"] = "error"
        state["error_message"] = str(e)


def cut_status(batch_id: str) -> dict:
    state = _cut_jobs.get(batch_id) or {
        "status": "idle",
        "processed": 0,
        "total": 0,
        "errors": [],
        "error_message": None,
    }
    return {
        "status": state.get("status", "idle"),
        "processed": state.get("processed", 0),
        "total": state.get("total", 0),
        "errors": (state.get("errors") or [])[-50:],
        "error_message": state.get("error_message"),
    }
