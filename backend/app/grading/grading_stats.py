# -*- coding: utf-8 -*-
"""开始批改：按用户/文件夹/自然日统计上传与批改份数。"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.grading_daily_stat import GradingDailyStat
from app.models.user import User

logger = logging.getLogger(__name__)

_STAT_UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".pdf", ".doc", ".docx"}


# ── 口径 B 计量旁路（docs/payment/payment-design.md §7.1）──────────────────────────
# ⛔ 禁忌：本函数**绝不**放在 `_increment` 的 try 内、也**绝不**放进
#    `record_graded_state_change` 的 `try/except: pass` 里 —— 那里吞异常且无日志，
#    计费事件被吞 = 静默少收钱。因此：所有 `_emit_*` 调用点一律写在**吞异常区之外**，
#    且 `emit_usage_event` 自己带 session 与异常处理（失败 logging.error 留痕，不阻塞主流程）。
def _emit_usage(kind: str, user_id: str, folder_safe: str, subject_key: str,
                delta: int, count: int = 1, occurrence: str = "") -> None:
    """旁路投递口径 B 用量事件。失败只留痕，⛔ 绝不向批改主流程抛异常。"""
    if not str(subject_key or "").strip():
        # ⚠️ 实测（脚本与原始输出见交付报告，2026-09-24）：
        #   · 空串路径**当前不可达**：两个调用点传的都是真实文件名
        #     （`grading/router.py:859` `target_file.name` / `:3890` `save_name`），
        #     `Path.name` 不可能为空。
        #   · 但**纯空白 stem 可达**：`get_stat_student_key("   .jpg") == "   "`
        #     （前后空格在 Windows/Linux 都是合法文件名），它同样落到本分支。
        #   真发生时的后果：口径 A 的 `grading_daily_stats` **已经把这 1 份计进去了**
        #   （实测 `upload_count=1`），口径 B 却不落 `usage_events` ⇒
        #   **两边口径不一致 = 静默少收钱** —— 正是 §7.1 全篇要防的那个形态。
        #   ⛔ 所以绝不静默 return：必须留痕（与同函数 except 分支同款）。
        #   根治不在此处：placeholder 归并键属 ① 类业务口径，未擅自发明；
        #   应在上游拒绝空/纯空白文件名，或 Phase 1 定 placeholder 规则。
        logger.error(
            "口径 B 计量丢弃：subject_key 为空/纯空白，本次不投用量事件"
            "（口径 A 的 grading_daily_stats 可能已把这份计入）："
            "kind=%s user_id=%s folder=%s subject=%r delta=%s",
            kind, user_id, folder_safe, subject_key, delta,
        )
        return
    try:
        from app.services.payment.metering import emit_usage_events

        emit_usage_events(
            user_id=user_id,
            kind=kind,
            folder_safe=folder_safe,
            subject_key=subject_key,
            count=count,
            delta=delta,
            occurrence=occurrence,
        )
    except Exception:
        # 连 import / 调用都没起来（如计量模块被误删）也必须留痕，⛔ 不静默
        logger.error(
            "口径 B 计量旁路调用失败：kind=%s user_id=%s folder=%s subject=%s delta=%s",
            kind, user_id, folder_safe, subject_key, delta, exc_info=True,
        )


def display_folder_name(folder_safe: str) -> str:
    safe = str(folder_safe or "").strip()
    if safe.startswith("cls_") and "__" in safe:
        return safe.split("__", 1)[1] or safe
    return safe or "未命名文件夹"


def get_stat_student_key(filename: str) -> str:
    """与前端学生试卷框一致：张三_1.jpg / 张三_2.jpg 归为同一学生「张三」。"""
    stem = Path(str(filename or "")).stem
    m = re.search(r"^(.*?)_\d+$", stem)
    return ((m.group(1) if m else stem) or stem).strip() or stem


def _list_folder_upload_filenames(folder_safe: str) -> list[str]:
    from app.grading.user_paths import correct_docs_dir

    dir_path = correct_docs_dir() / folder_safe
    if not dir_path.is_dir():
        return []
    names: list[str] = []
    for f in dir_path.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in _STAT_UPLOAD_EXTS:
            continue
        if f.stem == "标准答案":
            continue
        names.append(f.name)
    return names


def _load_history_completed(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        completed = data.get("completed")
        return completed if isinstance(completed, dict) else {}
    except Exception:
        return {}


def _load_folder_history_maps(folder_safe: str) -> tuple[dict, dict]:
    from app.grading.user_paths import grading_history_dir

    hist_dir = grading_history_dir()
    essay = _load_history_completed(hist_dir / f"{folder_safe}__essay.json")
    ref = _load_history_completed(hist_dir / f"{folder_safe}.json")
    return ref, essay


def _history_entry_for_file(folder_safe: str, filename: str) -> tuple[Optional[dict], str]:
    ref_map, essay_map = _load_folder_history_maps(folder_safe)
    essay_entry = essay_map.get(filename)
    if essay_entry is not None:
        return essay_entry, "essay"
    ref_entry = ref_map.get(filename)
    if ref_entry is not None:
        return ref_entry, "ref"
    return None, "ref"


def _student_group_shows_graded(
    folder_safe: str,
    student_key: str,
    *,
    override_filename: Optional[str] = None,
    override_entry: Optional[dict] = None,
    override_source: Optional[str] = None,
    exclude_filenames: Optional[set[str]] = None,
) -> bool:
    """同一学生的任一张试卷显示「已批改」即视为该学生已批改。"""
    exclude = exclude_filenames or set()
    ref_map, essay_map = _load_folder_history_maps(folder_safe)
    for fname in _list_folder_upload_filenames(folder_safe):
        if get_stat_student_key(fname) != student_key:
            continue
        if fname in exclude:
            continue
        if override_filename and fname == override_filename:
            entry = override_entry
            source = override_source or "ref"
        else:
            entry = essay_map.get(fname)
            if entry is not None:
                source = "essay"
            else:
                entry = ref_map.get(fname)
                source = "ref"
        if is_paper_shows_graded_badge(entry, source=source):
            return True
    return False


def _today() -> date:
    return date.today()


def _increment(
    user_id: str,
    folder_safe: str,
    *,
    upload_delta: int = 0,
    grade_delta: int = 0,
    stat_date: Optional[date] = None,
) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    folder = str(folder_safe or "").strip() or "_default"
    d = stat_date or _today()
    if upload_delta <= 0 and grade_delta <= 0:
        return

    db = SessionLocal()
    try:
        row = (
            db.query(GradingDailyStat)
            .filter(
                GradingDailyStat.user_id == uid,
                GradingDailyStat.folder_safe == folder,
                GradingDailyStat.stat_date == d,
            )
            .first()
        )
        if not row:
            row = GradingDailyStat(
                user_id=uid,
                folder_safe=folder,
                stat_date=d,
                upload_count=0,
                grade_count=0,
            )
            db.add(row)
        if upload_delta > 0:
            row.upload_count = int(row.upload_count or 0) + upload_delta
        if grade_delta > 0:
            row.grade_count = int(row.grade_count or 0) + grade_delta
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def record_upload(
    user_id: str,
    folder_safe: str,
    count: int = 1,
    *,
    subject_key: Optional[str] = None,
    occurrence: str = "",
) -> None:
    n = max(1, int(count or 1))
    _increment(user_id, folder_safe, upload_delta=n)
    # ↓ 旁路：在 _increment 的吞异常 try **之外**（§7.1 禁忌）
    _emit_usage("upload", user_id, folder_safe, subject_key or "", +1, count=n, occurrence=occurrence)


def record_upload_for_file(user_id: str, folder_safe: str, filename: str) -> None:
    """同一学生多张试卷（如 张三_1、张三_2）仅计 1 份上传。"""
    key = get_stat_student_key(filename)
    for fname in _list_folder_upload_filenames(folder_safe):
        if fname == filename:
            continue
        if get_stat_student_key(fname) == key:
            return
    record_upload(user_id, folder_safe, 1, subject_key=key)


def record_grade(
    user_id: str,
    folder_safe: str,
    count: int = 1,
    *,
    subject_key: Optional[str] = None,
    occurrence: str = "",
) -> None:
    n = max(1, int(count or 1))
    _increment(user_id, folder_safe, grade_delta=n)
    # ↓ 旁路：在 _increment 的吞异常 try **之外**（§7.1 禁忌）
    _emit_usage("grade", user_id, folder_safe, subject_key or "", +1, count=n, occurrence=occurrence)


def _decrement_field(user_id: str, folder_safe: str, field: str, amount: int = 1) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    folder = str(folder_safe or "").strip() or "_default"
    remaining = max(1, int(amount or 1))

    db = SessionLocal()
    try:
        rows = (
            db.query(GradingDailyStat)
            .filter(
                GradingDailyStat.user_id == uid,
                GradingDailyStat.folder_safe == folder,
            )
            .order_by(GradingDailyStat.stat_date.desc())
            .all()
        )
        for row in rows:
            if remaining <= 0:
                break
            current = int(getattr(row, field) or 0)
            if current <= 0:
                continue
            take = min(current, remaining)
            setattr(row, field, current - take)
            remaining -= take
        for row in rows:
            if int(row.upload_count or 0) <= 0 and int(row.grade_count or 0) <= 0:
                db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def record_upload_decrement(
    user_id: str,
    folder_safe: str,
    count: int = 1,
    *,
    subject_key: Optional[str] = None,
    occurrence: str = "",
) -> None:
    n = max(1, int(count or 1))
    _decrement_field(user_id, folder_safe, "upload_count", n)
    _emit_usage("upload", user_id, folder_safe, subject_key or "", -1, count=n, occurrence=occurrence)


def record_grade_decrement(
    user_id: str,
    folder_safe: str,
    count: int = 1,
    *,
    subject_key: Optional[str] = None,
    occurrence: str = "",
) -> None:
    n = max(1, int(count or 1))
    _decrement_field(user_id, folder_safe, "grade_count", n)
    # ↓ 旁路：口径 A 的扣减**不得**直接改账本（§3.3 I6）；账本只认 usage_events 的 delta
    _emit_usage("grade", user_id, folder_safe, subject_key or "", -1, count=n, occurrence=occurrence)


def record_paper_deleted_for_file(user_id: str, folder_safe: str, filename: str) -> None:
    """删除试卷：仅当该学生已无其他试卷时扣减上传；仅当该学生不再有任何已批改页时扣减批改。"""
    key = get_stat_student_key(filename)
    has_other_files = any(
        get_stat_student_key(fname) == key
        for fname in _list_folder_upload_filenames(folder_safe)
        if fname != filename
    )
    if not has_other_files:
        record_upload_decrement(user_id, folder_safe, 1, subject_key=key)

    was_group_graded = _student_group_shows_graded(folder_safe, key)
    still_group_graded = _student_group_shows_graded(
        folder_safe, key, exclude_filenames={filename}
    )
    if was_group_graded and not still_group_graded:
        record_grade_decrement(user_id, folder_safe, 1, subject_key=key)


def remove_folder_stats(user_id: str, folder_safe: str) -> None:
    """清空文件夹统计行（口径 A 会**一次性抹掉历史**，§1.3 陷阱 3）。

    ⛔ 口径 B 的账本**不得**被抹掉（§3.3 I6）：改为对该文件夹下净额仍为 +1 的每个学生
    补投 `delta=-1` 冲正事件 ⇒ 净额归 0 ⇒ net-diff 自动产生反向分录，历史一行不动。
    """
    uid = str(user_id or "").strip()
    if not uid:
        return
    folder = str(folder_safe or "").strip() or "_default"
    db = SessionLocal()
    try:
        db.query(GradingDailyStat).filter(
            GradingDailyStat.user_id == uid,
            GradingDailyStat.folder_safe == folder,
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    # ↓ 旁路：在吞异常的 try **之外**（§7.1 禁忌）
    try:
        from app.services.payment.metering import emit_folder_removed

        emit_folder_removed(uid, folder)
    except Exception:
        logger.error(
            "口径 B 文件夹冲正投递失败：user_id=%s folder=%s", uid, folder, exc_info=True
        )


def is_placeholder_completed_item(item: dict) -> bool:
    """识别“被错误保存为成功”的空批改结果（与 grading router 一致）。"""
    if not isinstance(item, dict):
        return False
    result = str(item.get("result") or "").strip()
    if not result:
        return True
    if any(item.get(key) for key in ("image_original", "image_annotated", "image_marks_only")):
        return False
    return result == "总题量：0；已批改：0；批改中：0"


def is_paper_shows_graded_badge(entry: Optional[dict], *, source: str) -> bool:
    """
    是否与前端文件夹列表「已批改」徽章一致。
    manual 模式界面显示「分析完成」，不计入批改份数；作文/参照/智能阅卷 completed 且非占位计入。
    """
    if not isinstance(entry, dict):
        return False
    if is_placeholder_completed_item(entry):
        return False
    if source == "manual":
        return False
    return True


def record_graded_state_change(
    user_id: str,
    folder_safe: str,
    old_entry: Optional[dict],
    new_entry: Optional[dict],
    *,
    source: str,
    filename: str,
) -> None:
    """按学生维度统计：同一学生多张试卷仅计 1 份批改。

    ⚠️ 结构变更（相对改动前，已申报）：原实现把 `record_grade` / `record_grade_decrement`
    也包在 `try/except: pass` 里。现改为**只把「跃迁判定」放在 try 内**，两个写调用移到
    try **之外** —— 否则口径 B 的计量旁路会随 `except: pass` 一起被静默吞掉（§7.1 禁忌）。
    两个写函数自身（`_increment` / `_decrement_field`）内部仍各自吞异常，故**无新增异常路径**。
    """
    transition = 0
    try:
        key = get_stat_student_key(filename)
        was = _student_group_shows_graded(
            folder_safe,
            key,
            override_filename=filename,
            override_entry=old_entry,
            override_source=source,
        )
        now = _student_group_shows_graded(
            folder_safe,
            key,
            override_filename=filename,
            override_entry=new_entry,
            override_source=source,
        )
        if not was and now:
            transition = 1
        elif was and not now:
            transition = -1
    except Exception:
        return

    if transition == 0:
        return
    try:
        from app.services.payment.metering import payload_occurrence

        occurrence = payload_occurrence(new_entry)
    except Exception:
        occurrence = ""
    # ↓ 旁路：在吞异常的 try **之外**（§7.1 禁忌）
    if transition > 0:
        record_grade(user_id, folder_safe, 1, subject_key=key, occurrence=occurrence)
    else:
        record_grade_decrement(user_id, folder_safe, 1, subject_key=key, occurrence=occurrence)


def query_grading_stats(
    db: Session,
    start_date: date,
    end_date: date,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    rows = (
        db.query(GradingDailyStat)
        .filter(
            GradingDailyStat.stat_date >= start_date,
            GradingDailyStat.stat_date <= end_date,
        )
        .all()
    )

    users_map: dict[str, dict[str, Any]] = {}
    all_upload = 0
    all_grade = 0

    for row in rows:
        uid = row.user_id
        upload = int(row.upload_count or 0)
        grade = int(row.grade_count or 0)
        all_upload += upload
        all_grade += grade

        if uid not in users_map:
            users_map[uid] = {"upload_count": 0, "grade_count": 0, "folders": {}}
        users_map[uid]["upload_count"] += upload
        users_map[uid]["grade_count"] += grade

        fkey = row.folder_safe or "_default"
        uf = users_map[uid]["folders"]
        if fkey not in uf:
            uf[fkey] = {"upload_count": 0, "grade_count": 0}
        uf[fkey]["upload_count"] += upload
        uf[fkey]["grade_count"] += grade

    user_rows = (
        db.query(User.id, User.email, User.display_name, User.roles)
        .filter(User.id.in_(list(users_map.keys()) if users_map else ["__none__"]))
        .all()
        if users_map
        else []
    )
    user_info = {r.id: r for r in user_rows}

    all_users_list = []
    for uid, agg in users_map.items():
        info = user_info.get(uid)
        all_users_list.append(
            {
                "user_id": uid,
                "display_name": getattr(info, "display_name", None) if info else None,
                "email": getattr(info, "email", None) if info else None,
                "upload_count": agg["upload_count"],
                "grade_count": agg["grade_count"],
            }
        )
    all_users_list.sort(key=lambda x: (x.get("display_name") or x.get("email") or ""))

    selected_user = None
    if user_id:
        agg = users_map.get(user_id, {"upload_count": 0, "grade_count": 0, "folders": {}})
        info = user_info.get(user_id)
        if not info:
            info = db.query(User).filter(User.id == user_id).first()
        folders = []
        for fkey, counts in sorted(
            (agg.get("folders") or {}).items(),
            key=lambda kv: display_folder_name(kv[0]),
        ):
            folders.append(
                {
                    "folder_safe": fkey,
                    "folder_name": display_folder_name(fkey),
                    "upload_count": counts["upload_count"],
                    "grade_count": counts["grade_count"],
                }
            )
        selected_user = {
            "user_id": user_id,
            "display_name": getattr(info, "display_name", None) if info else None,
            "email": getattr(info, "email", None) if info else None,
            "folders": folders,
            "total_upload": agg.get("upload_count", 0),
            "total_grade": agg.get("grade_count", 0),
        }

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "selected_user": selected_user,
        "all_users_summary": {
            "total_upload": all_upload,
            "total_grade": all_grade,
            "users": all_users_list,
        },
    }
