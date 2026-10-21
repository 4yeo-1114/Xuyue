# -*- coding: utf-8 -*-
"""批改完成后自动配套练习 / 高频错题举一反三（客户清单 #2 全自动）。

链路：批改落盘 → auto_class_sync.auto_sync_folder_after_grading（学情同步成功后）
  → auto_generate_variants_after_grading：
  1) 取该场错题（student_wrong_questions，auto_sync 刚导入；无记录时回退批改历史 completed）；
  2) 映射知识点（wrong_question_kp_bridge / knowledge_point_id；无桥接时用题干作伪 kp）；
  3) 按高频错点取 1-3 道变式题（优先 fetch_variant_questions 从资产库取；
     资产库不可用/空时可选 LLM 生成，get_llm_config 必须传 db；再不行跳过并记原因）；
  4) 原子写 JSON：grading_data_{user_id}/auto_variants/{folder_safe}.json。

幂等：同场已生成过（items 非空）就跳过；force=True 强制重跑。
并发护栏：单场单飞 + heavy_slot 全局排队（30 账号环境，绝不能批改一完就打爆）。
失败静默兜底：练习生成失败绝不影响学情同步/分层主链路。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 每个薄弱点取变式题条数上限
VARIANTS_PER_KP_MIN = 1
VARIANTS_PER_KP_MAX = 3
# 纳入配套练习的薄弱点数量上限（按错题频次）
MAX_WEAK_POINTS = 5
# 高频门槛：至少几条错题才算高频错点
MIN_WRONG_COUNT = 1

# 单场单飞：folder_safe -> True（生成中）
_inflight_lock = threading.Lock()
_inflight: set[str] = set()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def auto_variants_path(folder_safe: str) -> Path:
    """该场配套练习 JSON 路径：grading_data_{user_id}/auto_variants/{folder_safe}.json。"""
    from app.grading.user_paths import grading_paths

    root = grading_paths().root / "auto_variants"
    root.mkdir(parents=True, exist_ok=True)
    safe = str(folder_safe or "").strip().replace("/", "_").replace("\\", "_")
    return root / f"{safe}.json"


def atomic_write_json(path: Path, payload: dict) -> None:
    """原子写 JSON：先写 .tmp 再 os.replace，避免读到半截文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_auto_variants(folder_safe: str) -> Optional[dict]:
    """读该场已生成的配套练习；不存在/坏文件返回 None。"""
    try:
        p = auto_variants_path(folder_safe)
    except Exception:
        logger.warning("auto_variant: resolve path failed folder=%s", folder_safe, exc_info=True)
        return None
    if not p.is_file():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.warning("auto_variant: read json failed folder=%s", folder_safe, exc_info=True)
        return None


def should_skip_existing(existing: Optional[dict], force: bool) -> bool:
    """幂等判定：已生成过有效结果且非 force → 跳过。"""
    if force:
        return False
    if not isinstance(existing, dict):
        return False
    items = existing.get("items")
    return isinstance(items, list) and len(items) > 0


# ── 错题 → 知识点 → 高频错点（纯逻辑，可单测） ──────────────────
def aggregate_weak_points(
    rows: List[dict],
    *,
    min_wrong_count: int = MIN_WRONG_COUNT,
    max_points: int = MAX_WEAK_POINTS,
) -> List[dict]:
    """错题行 → 高频薄弱点列表（按错题条数降序，截断 max_points）。

    rows 每行：{question_title, student_name, kp_name?, kp_id?}。
    有 kp_name 按知识点聚合；无则用 question_title 作伪 kp（高频错题举一反三）。
    返回 [{kp_name, kp_id, wrong_count, student_count, titles}]。
    """
    buckets: Dict[str, dict] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("question_title") or "").strip()
        if not title:
            continue
        kp_name = str(row.get("kp_name") or "").strip()
        kp_id = str(row.get("kp_id") or row.get("knowledge_point_id") or "").strip()
        key = kp_name or title
        b = buckets.setdefault(key, {
            "kp_name": kp_name or title,
            "kp_id": kp_id or None,
            "wrong_count": 0,
            "_students": set(),
            "titles": [],
        })
        b["wrong_count"] += 1
        student = str(row.get("student_name") or "").strip()
        if student:
            b["_students"].add(student)
        if title and title not in b["titles"]:
            b["titles"].append(title)

    result: List[dict] = []
    for b in buckets.values():
        if b["wrong_count"] < min_wrong_count:
            continue
        result.append({
            "kp_name": b["kp_name"],
            "kp_id": b["kp_id"],
            "wrong_count": b["wrong_count"],
            "student_count": len(b["_students"]),
            "titles": list(b["titles"]),
        })
    result.sort(key=lambda x: (-x["wrong_count"], -x["student_count"], x["kp_name"]))
    return result[:max_points]


def assemble_weak_point_payload(
    weak_points: List[dict],
    question_fetcher: Callable[[str, str, int], List[dict]],
    subject: str,
    *,
    limit_per_kp: int = VARIANTS_PER_KP_MAX,
) -> List[dict]:
    """每个高频错点取 1-N 道变式题；fetcher 失败/空 → 记 skip_reason，不抛。"""
    limit = max(VARIANTS_PER_KP_MIN, min(VARIANTS_PER_KP_MAX, int(limit_per_kp or VARIANTS_PER_KP_MAX)))
    out: List[dict] = []
    for wp in weak_points or []:
        kp_name = str(wp.get("kp_name") or "").strip()
        entry = {
            "kp_name": kp_name,
            "kp_id": wp.get("kp_id"),
            "wrong_count": int(wp.get("wrong_count") or 0),
            "student_count": int(wp.get("student_count") or 0),
            "titles": list(wp.get("titles") or []),
            "variants": [],
            "skip_reason": None,
        }
        try:
            questions = question_fetcher(kp_name, subject, limit) or []
        except Exception as exc:
            logger.info("auto_variant: fetch variants failed kp=%s: %s", kp_name, exc)
            entry["skip_reason"] = "fetch_failed"
            out.append(entry)
            continue
        for q in questions[:limit]:
            if not isinstance(q, dict):
                continue
            entry["variants"].append({
                "id": q.get("id"),
                "question": str(q.get("question") or q.get("question_text") or "").strip(),
                "answer": str(q.get("answer") or "").strip(),
                "analysis": str(q.get("analysis") or "").strip(),
                "difficulty": q.get("difficulty"),
                "kp_name": kp_name,
                "source": q.get("source") or "asset_db",
            })
        if not entry["variants"]:
            entry["skip_reason"] = entry["skip_reason"] or "no_variants"
        out.append(entry)
    return out


def flatten_variant_items(weak_payload: List[dict]) -> List[dict]:
    """weak_points 列表 → 前端扁平 items（按 kp 顺序）。"""
    items: List[dict] = []
    for wp in weak_payload or []:
        for v in wp.get("variants") or []:
            items.append({**v, "kp_name": v.get("kp_name") or wp.get("kp_name")})
    return items


# ── 数据读取（懒加载重依赖） ────────────────────────────────────
def load_wrong_rows_from_db(db, class_id: str, exam_name: str, subject: str = "") -> List[dict]:
    """student_wrong_questions + wrong_question_kp_bridge 该场错题行。"""
    if db is None or not class_id or not exam_name:
        return []
    from app.models.student_analysis import StudentWrongQuestion
    from app.models.wrong_question_kp_bridge import WrongQuestionKpBridge

    q = (
        db.query(
            StudentWrongQuestion.question_title,
            StudentWrongQuestion.student_name,
            StudentWrongQuestion.knowledge_point_id,
            WrongQuestionKpBridge.kp_name,
            WrongQuestionKpBridge.kp_id,
        )
        .outerjoin(
            WrongQuestionKpBridge,
            WrongQuestionKpBridge.wrong_question_id == StudentWrongQuestion.id,
        )
        .filter(
            StudentWrongQuestion.class_id == class_id,
            StudentWrongQuestion.exam_name == exam_name,
        )
    )
    if subject:
        q = q.filter(StudentWrongQuestion.subject == subject)
    rows = []
    for title, student_name, kp_col_id, kp_name, kp_id in q.all():
        rows.append({
            "question_title": title or "",
            "student_name": student_name or "",
            "knowledge_point_id": kp_col_id or "",
            "kp_name": kp_name or "",
            "kp_id": kp_id or kp_col_id or "",
        })
    return rows


def load_wrong_rows_from_history(folder_safe: str) -> List[dict]:
    """回退：从批改历史 completed 解析错题标题（无 DB 记录时）。"""
    try:
        from app.services.auto_class_sync import load_folder_completed
        from app.grading.router import _parse_ai_result_to_counts
    except Exception:
        logger.warning("auto_variant: history loaders unavailable", exc_info=True)
        return []

    completed = load_folder_completed(folder_safe) or {}
    rows: List[dict] = []
    for filename, info in completed.items():
        if not isinstance(info, dict):
            continue
        student = str(filename or "")
        # 去页号：张三_1.jpg → 张三
        stem = student.rsplit(".", 1)[0]
        if stem.endswith(("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")) and "_" in stem:
            stem = stem.rsplit("_", 1)[0]
        result_text = info.get("result") or ""
        try:
            _counts, blocks = _parse_ai_result_to_counts(result_text)
        except Exception:
            continue
        for b in blocks or []:
            if not isinstance(b, dict):
                continue
            if b.get("status") in ("wrong", "blank"):
                rows.append({
                    "question_title": str(b.get("title") or "").strip(),
                    "student_name": stem,
                    "kp_name": "",
                    "kp_id": "",
                })
    return rows


def _default_question_fetcher(asset_db, subject: str):
    """资产库变式题 fetcher；asset_db 不可用时返回空列表（不抛到主链路）。"""
    def _fetch(kp_name: str, subj: str, limit: int) -> List[dict]:
        if asset_db is None:
            return []
        from app.services.bandit_recommender import AssetDBUnavailable, fetch_variant_questions

        try:
            return fetch_variant_questions(asset_db, subj or subject, kp_name, limit)
        except AssetDBUnavailable:
            return []
        except Exception:
            logger.warning("auto_variant: asset fetch error kp=%s", kp_name, exc_info=True)
            return []
    return _fetch


# 引用图形但没给【图示】描述的裸表述（检测闸用）
_FIGURE_REF_RE = re.compile(r"如图|见下图|如下图|见上图|如图所示|图中|右图|左图")


def _needs_figure_fix(q: str) -> bool:
    """题干引用了图形却没有【图示】文字描述 → 需要修复。"""
    return bool(_FIGURE_REF_RE.search(q or "")) and "【图示" not in (q or "")


def _repair_figure_refs(db, items: List[dict]) -> List[dict]:
    """硬闸：含「如图」却无【图示】描述的题，一次 LLM 调用批量补写图形描述。

    失败/超时/条数对不上 → 保持原题不动（fail-open，宁可少修不拖垮出题）。
    """
    if db is None:
        return items
    idxs = [i for i, it in enumerate(items) if _needs_figure_fix(it.get("question", ""))]
    if not idxs:
        return items
    try:
        import requests

        from app.utils.qwen_settings import QWEN_CHAT_EXTRA_BODY, get_llm_config

        base_url, api_key, model = get_llm_config(db)
        if not api_key:
            return items
        numbered = "\n".join(
            f"{n + 1}. {items[i]['question']}" for n, i in enumerate(idxs)
        )
        prompt = (
            "以下题目引用了图形但没有图形描述，学生看不到图无法作答。\n"
            "请为每题补写【图示：…】完整图形描述（形状、顶点字母、边长/角度/坐标等全部已知条件），"
            "并把题干里裸的「如图」等表述改为「如【图示】」或直接融入描述。\n"
            "不要改动题目本意、数字和设问。\n"
            '只输出 JSON：{"fixed":["完整题干1","完整题干2"]}，顺序与输入一致，不要输出其它文字。\n'
            f"{numbered}"
        )
        resp = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                **QWEN_CHAT_EXTRA_BODY,
            },
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60,
        )
        if resp.status_code != 200:
            return items
        content = ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return items
        fixed = json.loads(text[start : end + 1]).get("fixed")
        if not isinstance(fixed, list):
            return items
        for n, i in enumerate(idxs):
            if n < len(fixed):
                q2 = str(fixed[n] or "").strip()
                if q2:
                    items[i] = {**items[i], "question": q2}
        return items
    except Exception:
        logger.info("auto_variant: figure repair failed", exc_info=True)
        return items


def _llm_generate_variants(
    db,
    subject: str,
    kp_name: str,
    titles: List[str],
    limit: int,
    types: Optional[List[str]] = None,
    extra_topics: Optional[List[str]] = None,
) -> List[dict]:
    """资产库空时降级 / AI 题源：LLM 生成变式题干+答案。get_llm_config 必须传 db；失败返回 []。

    types：题型偏好（英文枚举或中文均可，如 choice/选择题）；extra_topics：补充知识点。
    """
    if db is None or not kp_name:
        return []
    try:
        import requests

        from app.utils.qwen_settings import QWEN_CHAT_EXTRA_BODY, get_llm_config

        base_url, api_key, model = get_llm_config(db)
        if not api_key:
            return []
        sample = "；".join(titles[:3]) if titles else ""
        type_hint = ""
        if types:
            try:
                from app.services.ai_question_gen import TYPE_ZH

                zh = [TYPE_ZH.get(str(t).strip(), str(t).strip()) for t in types if str(t).strip()]
            except Exception:
                zh = [str(t).strip() for t in types if str(t).strip()]
            if zh:
                type_hint = f"\n题型偏好：优先出{'、'.join(zh)}。"
        topics_hint = ""
        if extra_topics:
            ts = [str(t).strip() for t in extra_topics if str(t).strip()]
            if ts:
                topics_hint = f"\n补充知识点：{'、'.join(ts)}（可与「{kp_name}」结合出题）。"
        prompt = (
            f"你是资深{subject or '学科'}教师。学生在知识点「{kp_name}」上高频出错"
            f"{('，原题：' + sample) if sample else ''}。\n"
            f"请生成 {limit} 道同类变式题（难度适中、适合巩固）{type_hint}{topics_hint}，只输出 JSON：\n"
            '{"questions":[{"question":"题干","options":["选项1","选项2","选项3","选项4"],'
            '"answer":"参考答案","analysis":"简要解析"}]}\n'
            "出题要求（务必遵守）：\n"
            "1. 每道题必须完整、可独立作答，不允许只给半截题干。\n"
            "2. 选择题/多选题：把全部选项写进 options（一般 4 个，选项内容本身不要加 A. B. C. D. 前缀）；"
            "answer 写正确选项字母（如「B」）加简要说明。判断题 options 留空数组，answer 写「正确」或「错误」。"
            "填空题用「___」标出空格。简答题直接出题干。\n"
            "3. 几何题、统计图、表格等需要图形的题：你无法配图，必须在题干末尾用【图示：…】以文字完整描述"
            "图形（形状、顶点字母、边长/角度/坐标等全部已知条件），使题干自含可解。"
            "原题若自带配图，变式题也用【图示】文字描述代替图片。\n"
            "4. 题干中禁止出现没有描述的「如图」「见下图」「如下图所示」等依赖图片的表述"
            "（系统会检查：凡含「如图」而无【图示】描述的题会被退回重写）。\n"
            "不要输出 ```json 代码块或其它说明文字。"
        )
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            **QWEN_CHAT_EXTRA_BODY,
        }
        resp = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60,
        )
        if resp.status_code != 200:
            return []
        content = ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return []
        data = json.loads(text[start : end + 1])
        qs = data.get("questions") if isinstance(data, dict) else None
        out = []
        for it in (qs or [])[:limit]:
            if not isinstance(it, dict):
                continue
            q = str(it.get("question") or "").strip()
            if not q:
                continue
            # 选项并入题干（换行分隔，前端 white-space:pre-line 保留换行），
            # 使 question 字段自含完整题目；同时保留结构化 options 供后续判分用。
            opt_list = it.get("options")
            opt_texts: List[str] = []
            if isinstance(opt_list, list):
                letters = "ABCDEFGH"
                for i, o in enumerate(opt_list):
                    s = str(o or "").strip()
                    if not s:
                        continue
                    if re.match(r"^[A-H][.．、)）]", s):
                        opt_texts.append(s)
                    elif i < len(letters):
                        opt_texts.append(f"{letters[i]}. {s}")
            q_full = q if not opt_texts else q + "\n" + "\n".join(opt_texts)
            out.append({
                "id": f"llm-{kp_name}-{len(out)}",
                "question": q_full,
                "options": opt_texts,
                "answer": str(it.get("answer") or "").strip(),
                "analysis": str(it.get("analysis") or "").strip(),
                "difficulty": None,
                "source": "llm",
            })
        # 硬闸：裸「如图」没描述的题退回补写【图示】
        return _repair_figure_refs(db, out)
    except Exception:
        logger.info("auto_variant: llm fallback failed kp=%s", kp_name, exc_info=True)
        return []


# ── 主入口 ──────────────────────────────────────────────────────
def auto_generate_variants_after_grading(
    user_id: str,
    folder_safe: str,
    *,
    force: bool = False,
    db=None,
    asset_db=None,
    question_fetcher: Optional[Callable[[str, str, int], List[dict]]] = None,
    limit_per_kp: int = VARIANTS_PER_KP_MAX,
    use_llm_fallback: bool = True,
    source: Optional[str] = None,
    types: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """批改完成后自动生成该场配套练习。返回摘要；异常由调用方兜底（这里也尽量不抛）。

    幂等键：auto_variants/{folder_safe}.json（items 非空则跳过，force 强制重跑）。
    单场单飞：同 folder 已在跑 → skipped=already_running。
    source="ai"：跳过题库抽题，全部 LLM 生成（types/topics 给出题偏好）。
    """
    folder = str(folder_safe or "").strip()
    if not folder:
        return {"skipped": "no_folder"}

    # 单场单飞
    with _inflight_lock:
        if folder in _inflight:
            return {"skipped": "already_running", "folder": folder}
        _inflight.add(folder)
    try:
        return _generate_locked(
            user_id,
            folder,
            force=force,
            db=db,
            asset_db=asset_db,
            question_fetcher=question_fetcher,
            limit_per_kp=limit_per_kp,
            use_llm_fallback=use_llm_fallback,
            source=source,
            types=types,
            topics=topics,
        )
    finally:
        with _inflight_lock:
            _inflight.discard(folder)


def _generate_locked(
    user_id: str,
    folder: str,
    *,
    force: bool,
    db,
    asset_db,
    question_fetcher,
    limit_per_kp: int,
    use_llm_fallback: bool,
    source: Optional[str] = None,
    types: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    # 全局重活排队（1015 总闸：新重活链路必须包 heavy_slot）
    try:
        from app.services.heavy_budget import heavy_slot

        slot_ctx = heavy_slot("auto-variant")
    except Exception:
        from contextlib import nullcontext

        slot_ctx = nullcontext(0.0)

    with slot_ctx:
        return _generate_impl(
            user_id,
            folder,
            force=force,
            db=db,
            asset_db=asset_db,
            question_fetcher=question_fetcher,
            limit_per_kp=limit_per_kp,
            use_llm_fallback=use_llm_fallback,
            source=source,
            types=types,
            topics=topics,
        )


def _generate_impl(
    user_id: str,
    folder: str,
    *,
    force: bool,
    db,
    asset_db,
    question_fetcher,
    limit_per_kp: int,
    use_llm_fallback: bool,
    source: Optional[str] = None,
    types: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    existing = load_auto_variants(folder)
    if should_skip_existing(existing, force):
        return {
            "skipped": "already_generated",
            "folder": folder,
            "items_count": len(existing.get("items") or []),
        }

    from app.services.auto_class_sync import parse_class_folder, read_folder_meta

    parsed = parse_class_folder(folder)
    class_id, exam_name = (parsed if parsed else ("", ""))
    try:
        meta = read_folder_meta(folder) or {}
    except Exception:
        meta = {}
    subject = str(meta.get("subject") or "").strip()

    own_db = False
    if db is None and class_id:
        try:
            from app.database import SessionLocal

            db = SessionLocal()
            own_db = True
        except Exception:
            logger.warning("auto_variant: SessionLocal unavailable", exc_info=True)
            db = None

    own_asset = False
    if asset_db is None and question_fetcher is None:
        try:
            from app.config import settings

            if getattr(settings, "ASSETS_DB_ENABLED", False):
                from app.assets.database import assets_session

                asset_db = assets_session()
                own_asset = True
        except Exception:
            logger.info("auto_variant: assets db open failed, degrade to empty")
            asset_db = None

    try:
        rows: List[dict] = []
        if class_id and exam_name and db is not None:
            try:
                rows = load_wrong_rows_from_db(db, class_id, exam_name, subject)
            except Exception:
                logger.warning("auto_variant: db wrong rows failed", exc_info=True)
                rows = []
        if not rows:
            rows = load_wrong_rows_from_history(folder)

        weak_points = aggregate_weak_points(rows)
        if not weak_points:
            payload = {
                "folder": folder,
                "class_id": class_id or None,
                "exam_name": exam_name or None,
                "subject": subject or None,
                "status": "empty",
                "reason": "no_wrong_questions",
                "generated_at": _utc_now_iso(),
                "weak_points": [],
                "items": [],
            }
            try:
                atomic_write_json(auto_variants_path(folder), payload)
            except Exception:
                logger.warning("auto_variant: write empty json failed", exc_info=True)
            return {"folder": folder, "status": "empty", "reason": "no_wrong_questions", "items_count": 0}

        fetcher = question_fetcher
        ai_only = (str(source or "").strip().lower() == "ai")
        if fetcher is None and not ai_only:
            fetcher = _default_question_fetcher(asset_db, subject)

        # 资产库优先；空结果且允许 LLM 时补生成（source=ai 时跳过题库，直接 LLM）
        if ai_only and question_fetcher is None:
            fetcher = lambda kp_name, subj, lim: []  # noqa: E731 - AI 题源不查题库
        weak_payload = assemble_weak_point_payload(
            weak_points, fetcher, subject, limit_per_kp=limit_per_kp
        )
        if (use_llm_fallback or ai_only) and db is not None:
            for entry in weak_payload:
                if entry.get("variants"):
                    continue
                gen = _llm_generate_variants(
                    db,
                    subject,
                    entry.get("kp_name") or "",
                    entry.get("titles") or [],
                    limit_per_kp,
                    types=types,
                    extra_topics=topics,
                )
                if gen:
                    entry["variants"] = gen
                    entry["skip_reason"] = None

        items = flatten_variant_items(weak_payload)
        status = "ready" if items else "empty"
        reason = "" if items else "no_variants"
        payload = {
            "folder": folder,
            "class_id": class_id or None,
            "exam_name": exam_name or None,
            "subject": subject or None,
            "status": status,
            "reason": reason,
            "generated_at": _utc_now_iso(),
            "weak_points": weak_payload,
            "items": items,
        }
        try:
            atomic_write_json(auto_variants_path(folder), payload)
        except Exception:
            logger.warning("auto_variant: write json failed", exc_info=True)
            return {
                "folder": folder,
                "status": "failed",
                "reason": "write_failed",
                "items_count": len(items),
            }
        return {
            "folder": folder,
            "status": status,
            "reason": reason,
            "items_count": len(items),
            "weak_points": len(weak_payload),
        }
    except Exception as exc:
        # 最后兜底：任何意外都不抛（调用方还会再包一层）
        logger.warning("auto_variant: generate failed folder=%s: %s", folder, exc, exc_info=True)
        return {"folder": folder, "status": "failed", "reason": str(exc)[:200], "items_count": 0}
    finally:
        if own_db and db is not None:
            try:
                db.close()
            except Exception:
                pass
        if own_asset and asset_db is not None:
            try:
                asset_db.close()
            except Exception:
                pass


def read_auto_variants_for_api(folder_safe: str) -> Dict[str, Any]:
    """读端点数据：已有 JSON → 原样返回；没有 → status=none（不触发生成）。"""
    folder = str(folder_safe or "").strip()
    if not folder:
        return {"folder": "", "status": "none", "reason": "no_folder", "items": []}
    data = load_auto_variants(folder)
    if not data:
        return {
            "folder": folder,
            "status": "none",
            "reason": "not_generated",
            "items": [],
            "weak_points": [],
        }
    items = data.get("items")
    if not isinstance(items, list):
        items = []
        data["items"] = items
    status = data.get("status")
    if status not in ("ready", "empty", "failed"):
        status = "ready" if items else "empty"
        data["status"] = status
    data["folder"] = folder
    return data
