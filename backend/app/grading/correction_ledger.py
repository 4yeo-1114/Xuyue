# -*- coding: utf-8 -*-
"""修正/复核记账台账（B 项：修正回流 + 复核记账）。

行（source）：
- human_ai_correct：老师 ai-correct 手动修正——`_diff_ai_correct_blocks` 对照
  修正前后 stored_blocks，只记 result/comment 被改的题（was→new 进台账）；
- human_note / human_paper_note / human_wrong_note：老师批注、试卷总评、
  判错批注的增删改——`diff_note_rows` 对照保存前后文本（was_comment→new_comment，
  不带判定/分数）；
- form_guard / vl_ink：兜底强降级与 VL 笔迹复核拦截（flagged 为只标不改判，
  was=new=原判，reason 进 new_comment）。

写库范式对齐 response_log_db.write_response_logs：SessionLocal + add_all +
commit + 全 try/except 静默（旁路写入绝不阻断批改主流程）。
re-grade 全量重跑后 void_folder_corrections 置 voided=1：历史事实保留，
当前态统计（correction_stats 默认）排除。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, or_

from app.database import SessionLocal
from app.grading.form_guard import _norm_result
from app.grading.response_log_db import _text_or_none, _to_float
from app.models.correction_ledger import CorrectionLedger

_AI_CORRECT_SOURCE = "human_ai_correct"
_RESULT_TO_STATUS = {"对": "correct", "错": "wrong", "未作答": "unanswered", "半对": "partial"}
_COMMENT_MAX = 500


# ── 纯函数：ai-correct 修正对照 ─────────────────────────────────────────


def _scalar_str(value: Any) -> Optional[str]:
    """题号归一为可存字符串（历史块里可能是 int/str/列表）；空 → None。"""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        text = "_".join(str(v) for v in value)
    else:
        text = str(value)
    return text.strip() or None


def _pair_key(index: Any, sub_index: Any) -> tuple:
    return (_scalar_str(index), _scalar_str(sub_index))


def snapshot_ai_correct_fields(blocks: list) -> list[dict]:
    """快照比对四字段（result 经 _norm_result 归一），供 _diff_ai_correct_blocks 前后对照。

    ⛔ 不直接 deepcopy 整块：比对只需 result/comment/partial_ratio/score + 题号身份。
    """
    out: list[dict] = []
    for blk in blocks or []:
        if not isinstance(blk, dict):
            continue
        out.append(
            {
                "index": blk.get("index"),
                "sub_index": blk.get("sub_index"),
                "result": _norm_result(blk.get("result")),
                "comment": str(blk.get("comment") or ""),
                "partial_ratio": blk.get("partial_ratio"),
                "score": blk.get("score"),
            }
        )
    return out


def _diff_ai_correct_blocks(before: list, after: list) -> tuple[list, list]:
    """ai-correct 前后对照 → (ledger_rows, changed_blocks)。纯函数，可单测。

    - 以 (index, sub_index) 对齐；result 比对前经 _norm_result 归一
      （「半对（0.6）」==「半对」，比例细化不算改判）；score/partial_ratio 按
      float 归一比较（2 == 2.0）。
    - result/comment/partial_ratio/score 任一变化才算变更块（进 changed_blocks，
      以 engine="manual" 回流 response_logs）。
    - ledger 行记 result/comment 变化（判定/评语被推翻）**和纯调分**（score 变、
      判定/评语未变：was=new=原判，was_score/new_score 进台账）。partial_ratio
      细化仍只回流日志，不算改判不进台账。
    - 同一保存路径只记一遍：内容修正与纯调分共用本 diff 产出的 ledger_rows，
      由调用方一次 record_corrections 写入（勿另挂第二处）。
    - 变更块盖三键：ai_original_result=原判、corrected_by="human"、
      status=人工终态英文值（_derive_status 优先于 baidu_correct_result 码
      = 人工终态优先的正确实现）。
    - 全无变化 → ([], [])：原样保存不写任何东西。
    """
    before_by_key: dict = {}
    for snap in before or []:
        if not isinstance(snap, dict):
            continue
        before_by_key[_pair_key(snap.get("index"), snap.get("sub_index"))] = snap
    ledger_rows: list = []
    changed_blocks: list = []
    for blk in after or []:
        if not isinstance(blk, dict):
            continue
        snap = before_by_key.get(_pair_key(blk.get("index"), blk.get("sub_index")))
        if snap is None:
            continue
        was_result = str(snap.get("result") or "")
        new_result = _norm_result(blk.get("result"))
        was_comment = str(snap.get("comment") or "")
        new_comment = str(blk.get("comment") or "")
        was_partial = _to_float(snap.get("partial_ratio"))
        new_partial = _to_float(blk.get("partial_ratio"))
        was_score = _to_float(snap.get("score"))
        new_score = _to_float(blk.get("score"))
        result_changed = was_result != new_result
        comment_changed = was_comment != new_comment
        score_changed = was_score != new_score
        if not (result_changed or comment_changed or was_partial != new_partial or score_changed):
            continue
        # 变更块盖三键（随 blocks 进 history / response_logs）
        blk["ai_original_result"] = was_result or None
        blk["corrected_by"] = "human"
        status = _RESULT_TO_STATUS.get(new_result)
        if status:
            blk["status"] = status
        changed_blocks.append(blk)
        # 判定/评语被推翻 **或纯调分** 都进台账（比例细化除外）；同一变更块只记一行
        if result_changed or comment_changed or score_changed:
            ledger_rows.append(
                {
                    "index": blk.get("index"),
                    "sub_index": blk.get("sub_index"),
                    "source": _AI_CORRECT_SOURCE,
                    "was_result": was_result or None,
                    "new_result": new_result or None,
                    "was_comment": was_comment or None,
                    "new_comment": new_comment or None,
                    "was_score": was_score,
                    "new_score": new_score,
                    "subject_family": blk.get("subject_family"),
                }
            )
    return ledger_rows, changed_blocks


# ── 纯函数：批注类字段对照（老师批注 / 试卷总评 / 判错批注） ──────────────


def _norm_note_text(value: Any) -> Optional[str]:
    """批注文本归一：去首尾空白；空 → None（与「没有这条」同义）。"""
    text = str(value or "").strip()
    return text or None


def _note_map_texts(raw: Any, pick_text: bool = False) -> dict:
    """题号 → 文本 映射归一。wrong_annotations 值是 {text,...}，pick_text 取 text。"""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        k = _scalar_str(key)
        if not k:
            continue
        if pick_text and isinstance(val, dict):
            val = val.get("text")
        text = _norm_note_text(val)
        if text is not None:
            out[k] = text
    return out


def diff_note_rows(before: dict, after: dict) -> list[dict]:
    """批注类字段前后对照 → 台账行（纯函数，可单测）。

    before / after 形状：{"question_notes": ..., "paper_note": ...,
    "wrong_annotations": ...}；缺字段按空处理。

    - question_notes（老师批注，key=题号）：增/删/改各记一行（source=human_note）；
    - paper_note（试卷总评）：整卷一条（index=None，source=human_paper_note）；
    - wrong_annotations（判错批注，key=题号）：只对照 text（source=human_wrong_note），
      edited/generated_at 等元数据翻牌不算变更；
    - 行只带 was_comment/new_comment（文本前后），判定/分数留空——这不是改判；
      两边同为空不算变更。paper_note 超长截断由 record_corrections 统一处理。
    """
    rows: list[dict] = []

    def _add(index: Any, source: str, was: Optional[str], new: Optional[str]) -> None:
        if was == new:
            return
        rows.append(
            {
                "index": index,
                "sub_index": None,
                "source": source,
                "was_result": None,
                "new_result": None,
                "was_comment": was,
                "new_comment": new,
                "was_score": None,
                "new_score": None,
            }
        )

    qn_before = _note_map_texts((before or {}).get("question_notes"))
    qn_after = _note_map_texts((after or {}).get("question_notes"))
    for key in sorted(set(qn_before) | set(qn_after)):
        _add(key, "human_note", qn_before.get(key), qn_after.get(key))

    _add(
        None,
        "human_paper_note",
        _norm_note_text((before or {}).get("paper_note")),
        _norm_note_text((after or {}).get("paper_note")),
    )

    wa_before = _note_map_texts((before or {}).get("wrong_annotations"), pick_text=True)
    wa_after = _note_map_texts((after or {}).get("wrong_annotations"), pick_text=True)
    for key in sorted(set(wa_before) | set(wa_after)):
        _add(key, "human_wrong_note", wa_before.get(key), wa_after.get(key))

    return rows


# ── 纯函数：form_guard / vl_ink 复核记账 ────────────────────────────────


def _change_reason(change: dict) -> Optional[str]:
    """变更原因一句话（form_guard.reason / ink_evidence 置信），截 500。"""
    reason = str(change.get("reason") or "").strip()
    if reason:
        return reason[:_COMMENT_MAX]
    if change.get("has_handwriting") is False:
        return f"VL 未见手写笔迹 conf={change.get('confidence')}"[:_COMMENT_MAX]
    return None


def guard_changes_to_ledger_rows(
    changes: list,
    source: str,
    blocks: Optional[list] = None,
    subject_family: Optional[str] = None,
) -> list[dict]:
    """form_guard / ink_evidence 变更清单 → correction_ledger 行。

    - downgraded：was_result=原判、new_result=未作答（强降级事实进台账）；
    - flagged：was=new=原 result（只标不改判），reason 进 new_comment。
    blocks 供取 subject_family（router 4714 已盖好）与 flagged 的原判
    （flagged 不改判，块上的 result 即原判）。
    """
    by_key: dict = {}
    for blk in blocks or []:
        if isinstance(blk, dict):
            by_key[_pair_key(blk.get("index"), blk.get("sub_index"))] = blk
    rows: list = []
    for change in changes or []:
        if not isinstance(change, dict):
            continue
        action = str(change.get("action") or "")
        if action not in ("downgraded", "flagged"):
            continue
        blk = by_key.get(_pair_key(change.get("index"), change.get("sub_index")))
        family = (blk or {}).get("subject_family") or subject_family
        reason = _change_reason(change)
        if action == "downgraded":
            was = _norm_result(change.get("was_result")) or _norm_result((blk or {}).get("result"))
            rows.append(
                {
                    "index": change.get("index"),
                    "sub_index": change.get("sub_index"),
                    "source": source,
                    "was_result": was or None,
                    "new_result": "未作答",
                    "new_comment": reason,
                    "subject_family": family,
                }
            )
        else:  # flagged：只标不改判
            was = _norm_result(change.get("was_result")) or _norm_result((blk or {}).get("result"))
            rows.append(
                {
                    "index": change.get("index"),
                    "sub_index": change.get("sub_index"),
                    "source": source,
                    "was_result": was or None,
                    "new_result": was or None,
                    "new_comment": reason,
                    "subject_family": family,
                }
            )
    return rows


# ── 纯函数：manual-grade 纯调分对照 ────────────────────────────────────


def _score_key_to_index_pair(key: Any) -> tuple:
    """统分键「第N题」「第N题-作答区M」→ (index, sub_index)；解析不了则整键进 index。"""
    text = _scalar_str(key) or ""
    # 第12题-作答区3 / 第12题
    m = re.match(r"^第(.+?)题(?:-作答区(.+))?$", text)
    if m:
        return (m.group(1), m.group(2) or None)
    return (text or None, None)


def diff_score_map_rows(prev_scores: dict, new_scores: dict) -> list[dict]:
    """manual-grade 分数表前后对照 → 台账行（纯调分：was=new=判定留空，只记分）。

    - 只记「两边都有值且 float 不等」的键（首次打分不进台账：那是初始阅卷不是改分）；
    - 键解析成 (index, sub_index) 供台账题号列；source=human_ai_correct，
      与 ai-correct 纯调分同一语义（人工改分），engine 由调用方传 record_corrections 区分。
    """
    prev = prev_scores if isinstance(prev_scores, dict) else {}
    new = new_scores if isinstance(new_scores, dict) else {}
    rows: list[dict] = []
    for key, new_raw in new.items():
        if key not in prev:
            continue
        was_score = _to_float(prev.get(key))
        new_score = _to_float(new_raw)
        if was_score is None or new_score is None or was_score == new_score:
            continue
        index, sub_index = _score_key_to_index_pair(key)
        rows.append(
            {
                "index": index,
                "sub_index": sub_index,
                "source": _AI_CORRECT_SOURCE,
                "was_result": None,
                "new_result": None,
                "was_comment": None,
                "new_comment": None,
                "was_score": was_score,
                "new_score": new_score,
            }
        )
    return rows


# ── 写入 / 作废（SessionLocal 旁路，绝不阻断） ─────────────────────────


def _clip_comment(value: Any) -> Optional[str]:
    text = _text_or_none(value)
    return text[:_COMMENT_MAX] if text else None


def record_corrections(
    user_id: str,
    folder_safe: str,
    paper_name: str,
    engine: str,
    rows: list,
    subject_family: Optional[str] = None,
) -> None:
    """把修正/复核记账行写入 correction_ledger（旁路写入，绝不阻断主流程）。

    行形状（缺字段一律 None）：{index, sub_index, source, was_result, new_result,
    was_comment, new_comment, was_score, new_score, subject_family?}。
    comment 截 500；空 rows / 缺 user_id 静默返回；任何异常 try/except 静默。
    """
    if not rows:
        return
    uid = str(user_id or "").strip()
    if not uid:
        return
    safe = str(folder_safe or "").strip()
    paper = str(paper_name or "").strip()
    engine = str(engine or "").strip()
    entities = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entities.append(
            CorrectionLedger(
                user_id=uid,
                folder_safe=safe,
                paper_name=paper,
                engine=engine,
                index=_scalar_str(row.get("index")),
                sub_index=_scalar_str(row.get("sub_index")),
                source=str(row.get("source") or "").strip() or _AI_CORRECT_SOURCE,
                was_result=_text_or_none(row.get("was_result")),
                new_result=_text_or_none(row.get("new_result")),
                was_comment=_clip_comment(row.get("was_comment")),
                new_comment=_clip_comment(row.get("new_comment")),
                was_score=_to_float(row.get("was_score")),
                new_score=_to_float(row.get("new_score")),
                subject_family=_text_or_none(row.get("subject_family")) or _text_or_none(subject_family),
                voided=False,
            )
        )
    if not entities:
        return
    db = SessionLocal()
    try:
        db.add_all(entities)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"修正记账写入失败: {safe}/{paper}: {e}")
    finally:
        db.close()


def void_folder_corrections(folder_safe: str) -> None:
    """re-grade 全量重跑：该文件夹台账行置 voided=1（历史保留，当前态统计排除）。幂等。"""
    safe = str(folder_safe or "").strip()
    if not safe:
        return
    db = SessionLocal()
    try:
        db.query(CorrectionLedger).filter(CorrectionLedger.folder_safe == safe).update(
            {CorrectionLedger.voided: True},
            synchronize_session=False,
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"修正记账作废失败: {safe}: {e}")
    finally:
        db.close()


# ── 只读统计 ────────────────────────────────────────────────────────────


def correction_stats(db, user_id: str, days: int = 30, include_voided: bool = False) -> list[dict]:
    """修正/复核记账矩阵（只读 SELECT）：GROUP BY source, subject_family, was, new。

    默认排除 voided（re-grade 重跑已作废的行）；include_voided=True 出全历史。
    """
    uid = str(user_id or "").strip()
    if not uid:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    conds = [
        CorrectionLedger.user_id == uid,
        CorrectionLedger.created_at >= since,
    ]
    if not include_voided:
        conds.append(CorrectionLedger.voided.is_(False))
    rows = (
        db.query(
            CorrectionLedger.source,
            CorrectionLedger.subject_family,
            CorrectionLedger.was_result,
            CorrectionLedger.new_result,
            func.count(CorrectionLedger.id),
        )
        .filter(*conds)
        .group_by(
            CorrectionLedger.source,
            CorrectionLedger.subject_family,
            CorrectionLedger.was_result,
            CorrectionLedger.new_result,
        )
        .all()
    )
    matrix = [
        {
            "source": r[0],
            "subject_family": r[1],
            "was": r[2],
            "new": r[3],
            "count": int(r[4] or 0),
        }
        for r in rows or []
    ]
    matrix.sort(
        key=lambda m: (
            str(m.get("source") or ""),
            str(m.get("subject_family") or ""),
            str(m.get("was") or ""),
            str(m.get("new") or ""),
        )
    )
    return matrix


def _like_pattern(term: str) -> str:
    """LIKE 模式：用户关键词转义 % _ \\ 后包 %…%（防通配符注入/误匹配）。"""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _ledger_conds(
    user_id: str,
    days: int,
    include_voided: bool,
    source: Optional[str] = None,
    folder: Optional[str] = None,
    change_kind: Optional[str] = None,
    q: Optional[str] = None,
) -> list:
    """台账过滤条件（rows/total/facets 三处同口径复用）。

    - source：来源分类精确匹配（human_ai_correct/form_guard/vl_ink/…）；
    - folder：考试文件夹（folder_safe）精确匹配；
    - change_kind：改动类型 result=改判定 / score=改分 / comment=改评语，
      同一行可同时属于多类（判定+分数一起改是一行）；
    - q：关键词模糊搜学生卷名/考试名/评语（学生名嵌在 paper_name 里）。
    """
    uid = str(user_id or "").strip()
    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    conds = [
        CorrectionLedger.user_id == uid,
        CorrectionLedger.created_at >= since,
    ]
    if not include_voided:
        conds.append(CorrectionLedger.voided.is_(False))
    # isinstance 防御：端点直调测试绕过 FastAPI 时默认值可能是 Query 对象
    src = source.strip() if isinstance(source, str) else ""
    if src:
        conds.append(CorrectionLedger.source == src)
    fold = folder.strip() if isinstance(folder, str) else ""
    if fold:
        conds.append(CorrectionLedger.folder_safe == fold)
    kind = change_kind.strip() if isinstance(change_kind, str) else ""
    if kind == "result":
        conds.append(
            func.coalesce(CorrectionLedger.was_result, "") != func.coalesce(CorrectionLedger.new_result, "")
        )
    elif kind == "score":
        conds.append(
            func.coalesce(CorrectionLedger.was_score, -999999.0)
            != func.coalesce(CorrectionLedger.new_score, -999999.0)
        )
    elif kind == "comment":
        conds.append(
            func.coalesce(CorrectionLedger.was_comment, "") != func.coalesce(CorrectionLedger.new_comment, "")
        )
    elif kind:
        # 未知改动类型：宁可空列表也不误回全量
        from sqlalchemy import false as _false

        conds.append(_false())
    term = q.strip() if isinstance(q, str) else ""
    if term:
        pat = _like_pattern(term)
        conds.append(
            or_(
                CorrectionLedger.paper_name.ilike(pat, escape="\\"),
                CorrectionLedger.folder_safe.ilike(pat, escape="\\"),
                CorrectionLedger.was_comment.ilike(pat, escape="\\"),
                CorrectionLedger.new_comment.ilike(pat, escape="\\"),
            )
        )
    return conds


def _ledger_row_dict(r) -> dict:
    created = getattr(r, "created_at", None)
    return {
        "id": getattr(r, "id", None),
        "created_at": created.isoformat() if created else None,
        "paper_name": getattr(r, "paper_name", None),
        "folder_safe": getattr(r, "folder_safe", None),
        "engine": getattr(r, "engine", None),
        "index": getattr(r, "index", None),
        "sub_index": getattr(r, "sub_index", None),
        "source": getattr(r, "source", None),
        "was_result": getattr(r, "was_result", None),
        "new_result": getattr(r, "new_result", None),
        "was_comment": getattr(r, "was_comment", None),
        "new_comment": getattr(r, "new_comment", None),
        "was_score": getattr(r, "was_score", None),
        "new_score": getattr(r, "new_score", None),
        "subject_family": getattr(r, "subject_family", None),
        "voided": bool(getattr(r, "voided", False)),
    }


def correction_ledger_rows(
    db,
    user_id: str,
    days: int = 30,
    include_voided: bool = False,
    limit: int = 200,
    offset: int = 0,
    source: Optional[str] = None,
    folder: Optional[str] = None,
    change_kind: Optional[str] = None,
    q: Optional[str] = None,
) -> list[dict]:
    """修正/复核记账明细（只读 SELECT）：供台账查看页逐行列出。

    字段与 CorrectionLedger 列一一对应（时间/学生卷/题号/改动前后/来源）；
    默认排除 voided，按 created_at 倒序（id 兜底稳定分页），limit+offset 分页。
    """
    uid = str(user_id or "").strip()
    if not uid:
        return []
    conds = _ledger_conds(uid, days, include_voided, source=source, folder=folder, change_kind=change_kind, q=q)
    try:
        cap = max(1, min(int(limit or 200), 500))
    except (TypeError, ValueError):
        cap = 200
    try:
        off = max(0, int(offset or 0))
    except (TypeError, ValueError):
        off = 0
    rows = (
        db.query(CorrectionLedger)
        .filter(*conds)
        .order_by(CorrectionLedger.created_at.desc(), CorrectionLedger.id.desc())
        .offset(off)
        .limit(cap)
        .all()
    )
    return [_ledger_row_dict(r) for r in rows or []]


def correction_ledger_page(
    db,
    user_id: str,
    days: int = 30,
    include_voided: bool = False,
    source: Optional[str] = None,
    folder: Optional[str] = None,
    change_kind: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """分页明细 + 匹配总数 + 分类计数（台账查看页成千上万条时的口径）。

    - total：当前过滤条件下的总条数（分页母数）；
    - source_counts：按来源分类计数（**不含 source 自身过滤**，供分类 chip 显示
      「每类多少条」并可点选切换）；
    - folder_counts：按考试文件夹计数（**不含 folder 自身过滤**，供考试下拉）。
    两个 facets 都吃其余过滤（q/change_kind/voided/窗口），chip 数与列表口径一致。
    """
    uid = str(user_id or "").strip()
    if not uid:
        return {"rows": [], "total": 0, "page": 1, "page_size": 0, "source_counts": {}, "folder_counts": []}
    try:
        pg = max(1, int(page or 1))
    except (TypeError, ValueError):
        pg = 1
    try:
        size = max(1, min(int(page_size or 50), 200))
    except (TypeError, ValueError):
        size = 50

    conds = _ledger_conds(uid, days, include_voided, source=source, folder=folder, change_kind=change_kind, q=q)
    total = int(db.query(func.count(CorrectionLedger.id)).filter(*conds).scalar() or 0)
    rows = correction_ledger_rows(
        db,
        uid,
        days=days,
        include_voided=include_voided,
        limit=size,
        offset=(pg - 1) * size,
        source=source,
        folder=folder,
        change_kind=change_kind,
        q=q,
    )

    # 分类计数：各自维度去掉自身过滤（点 chip 前先看到每类条数）
    src_conds = _ledger_conds(uid, days, include_voided, folder=folder, change_kind=change_kind, q=q)
    source_counts: dict[str, int] = {}
    for src, cnt in (
        db.query(CorrectionLedger.source, func.count(CorrectionLedger.id)).filter(*src_conds).group_by(CorrectionLedger.source).all()
    ):
        source_counts[str(src or "unknown")] = int(cnt or 0)

    fold_conds = _ledger_conds(uid, days, include_voided, source=source, change_kind=change_kind, q=q)
    folder_counts = [
        {"folder": str(f or ""), "count": int(c or 0)}
        for f, c in (
            db.query(CorrectionLedger.folder_safe, func.count(CorrectionLedger.id))
            .filter(*fold_conds)
            .group_by(CorrectionLedger.folder_safe)
            .order_by(func.count(CorrectionLedger.id).desc())
            .limit(200)
            .all()
        )
    ]

    return {
        "rows": rows,
        "total": total,
        "page": pg,
        "page_size": size,
        "source_counts": source_counts,
        "folder_counts": folder_counts,
    }
