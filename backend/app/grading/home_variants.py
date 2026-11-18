# -*- coding: utf-8 -*-
"""首页快速批改「举一反三」：错题 → VL 读题 → LLM 变式题（客户 1029 需求）。

链路：POST /grading/home/{job_id}/variants（router.api_home_variants_generate）
  1) collect_wrong_question_groups(blocks) 取错/半对题（上限 MAX_WRONG_QUESTIONS）；
  2) 逐题裁图 VL 结构化分析（question_text / knowledge_points），失败走文本兜底；
  3) auto_variant._llm_generate_variants 每题生成变式题（题干+选项+答案+解析）；
  4) 前端「出成试卷」POST /exams/papers 落 smart_exam_papers（与网页版组卷同一份）。

单题失败记 from_error 不拖垮整批；全失败返回空 items 由端点报原因。
重 LLM：调用方必须是同步 def 端点，生成段包 heavy_slot 全局排队（1015 总闸）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 一场最多取几道错题做变式（防 LLM 打爆）
MAX_WRONG_QUESTIONS = 6
# 每道错题默认/最大变式题条数
DEFAULT_VARIANTS_PER_QUESTION = 2
MAX_VARIANTS_PER_QUESTION = 3

# 判定徽章优先级：同题多作答区取最差判定
_RESULT_RANK = {"错": 5, "半对": 4, "待确认": 3, "未作答": 2, "未批": 1, "对": 0, "": 0}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def question_type_of(question: str, options: List[str], answer: str) -> str:
    """按题面猜题型（落 smart_exam_papers 用，与组卷题型枚举对齐）。"""
    if options:
        return "choice"
    if str(answer or "").strip() in ("正确", "错误"):
        return "judge"
    if "___" in (question or "") or "＿＿＿" in (question or ""):
        return "fill"
    return "short_answer"


def split_merged_options(question: str, options: List[str]) -> str:
    """_llm_generate_variants 把选项并进了题干；还原出不含选项的 content（组卷/作业纸用）。

    合并规则是 q + '\\n' + '\\n'.join(opts)，这里按同样后缀精确剥掉；
    对不上（题干被改写过）就原样返回，宁可选项重复不丢题干。
    """
    q = str(question or "")
    opts = [str(o or "") for o in (options or []) if str(o or "").strip()]
    if not opts:
        return q
    suffix = "\n".join(opts)
    if q.endswith(suffix):
        return q[: -len(suffix)].rstrip("\n")
    return q


def build_variant_items(
    wrong_groups: Dict[str, dict],
    analyses: Dict[str, dict],
    variants_by_key: Dict[str, List[dict]],
) -> List[dict]:
    """纯装配：错题组 + VL 分析 + 变式题 → 扁平 items（按题号顺序）。"""
    items: List[dict] = []
    for key in sorted(wrong_groups.keys(), key=lambda k: (len(k), k)):
        group = wrong_groups.get(key) or {}
        analysis = analyses.get(key) or {}
        for n, v in enumerate(variants_by_key.get(key) or [], start=1):
            if not isinstance(v, dict):
                continue
            question = str(v.get("question") or "").strip()
            if not question:
                continue
            options = [str(o).strip() for o in (v.get("options") or []) if str(o).strip()]
            answer = str(v.get("answer") or "").strip()
            kp = str(v.get("kp_name") or "").strip()
            if not kp:
                kps = [str(k).strip() for k in (analysis.get("knowledge_points") or []) if str(k or "").strip()]
                kp = kps[0] if kps else ""
            items.append({
                "from_key": key,
                "from_title": f"第{key}题",
                "orig_result": str(group.get("result") or ""),
                "no": n,
                "question": question,
                "content": split_merged_options(question, options),
                "options": options,
                "type": question_type_of(question, options, answer),
                "answer": answer,
                "analysis": str(v.get("analysis") or "").strip(),
                "kp_name": kp,
                "source": str(v.get("source") or "llm"),
            })
    return items


def generate_home_variants(
    blocks: list,
    *,
    source_image_path: str = "",
    subject: str = "",
    count_per_question: int = DEFAULT_VARIANTS_PER_QUESTION,
    db=None,
    analyze_fn: Optional[Callable[[dict, str], dict]] = None,
    generate_fn: Optional[Callable[..., List[dict]]] = None,
    annotations: Optional[dict] = None,
) -> Dict[str, Any]:
    """错/半对题 → 变式题 items。heavy_slot 全局排队；单题失败不拖垮整批。

    analyze_fn(group, source_image_path) -> VL 分析 dict（可注入假实现单测）；
    generate_fn(db, subject, kp_name, titles, limit, extra_topics=...) -> 变式题列表；
    annotations：wrong_annotations 映射（题号 -> {text}），作为错因上下文兜底。
    返回 {items, generated_at, wrong_count, failed_keys}。
    """
    from app.grading.wrong_annotations import collect_wrong_question_groups

    wrong_groups = collect_wrong_question_groups(blocks)
    if not wrong_groups:
        return {"items": [], "generated_at": _utc_now_iso(), "wrong_count": 0, "failed_keys": []}
    # 上限截断：题号序在前的优先（fail-open，超出的题不动）
    keys = sorted(wrong_groups.keys(), key=lambda k: (len(k), k))[:MAX_WRONG_QUESTIONS]
    wrong_groups = {k: wrong_groups[k] for k in keys}

    try:
        from app.services.heavy_budget import heavy_slot

        slot_ctx = heavy_slot("home-variants")
    except Exception:
        from contextlib import nullcontext

        slot_ctx = nullcontext(0.0)

    with slot_ctx:
        return _generate_impl(
            wrong_groups,
            source_image_path=source_image_path,
            subject=subject,
            count_per_question=count_per_question,
            db=db,
            analyze_fn=analyze_fn,
            generate_fn=generate_fn,
            annotations=annotations or {},
        )


def _default_analyze(group: dict, source_image_path: str) -> dict:
    """裁图 VL 结构化分析（复用错题库分析）；失败返回 {} 走文本兜底。"""
    try:
        from app.grading.wrong_annotations import _crop_paths_for_group
        from app.grading.wrong_question_db import _analyze_wrong_question_with_vl

        q_path, a_path = _crop_paths_for_group(group, source_image_path)
        if not q_path:
            return {}
        record = {
            "display_title": "",
            "paper_subject": "",
            "question_type": None,
            "status": group.get("result") or "",
            "reason": group.get("comment") or "",
        }
        analysis = _analyze_wrong_question_with_vl(record, q_path, a_path)
        if str(analysis.get("status") or "") != "done":
            return {}
        return analysis
    except Exception:
        logger.info("home_variants: analyze failed", exc_info=True)
        return {}


def _default_generate(db, subject, kp_name, titles, limit, extra_topics=None):
    from app.services.auto_variant import _llm_generate_variants

    return _llm_generate_variants(
        db, subject, kp_name, titles, limit, extra_topics=extra_topics
    )


def _generate_impl(
    wrong_groups: Dict[str, dict],
    *,
    source_image_path: str,
    subject: str,
    count_per_question: int,
    db,
    analyze_fn,
    generate_fn,
    annotations: Dict[str, dict],
) -> Dict[str, Any]:
    analyze = analyze_fn or _default_analyze
    generate = generate_fn or _default_generate
    limit = max(1, min(MAX_VARIANTS_PER_QUESTION, int(count_per_question or DEFAULT_VARIANTS_PER_QUESTION)))

    analyses: Dict[str, dict] = {}
    variants_by_key: Dict[str, List[dict]] = {}
    failed_keys: List[str] = []

    for key, group in wrong_groups.items():
        try:
            analysis = analyze(group, source_image_path) or {}
        except Exception:
            logger.info("home_variants: analyze error key=%s", key, exc_info=True)
            analysis = {}
        analyses[key] = analysis

        # 原题文本：VL 读出的题干优先，退块字段，再退判错批注/机器评语
        question_text = str(analysis.get("question_text") or "").strip() or str(
            group.get("question_content") or ""
        ).strip()
        anno = str((annotations.get(key) or {}).get("text") or "").strip()
        fallback_ctx = "；".join(
            p for p in (anno, str(group.get("comment") or "").strip()) if p
        )
        if not question_text:
            question_text = fallback_ctx

        kps = analysis.get("knowledge_points")
        kps = [str(k).strip() for k in (kps or []) if str(k or "").strip()]
        kp_name = kps[0] if kps else (question_text[:24] if question_text else "本题考点")

        titles = [question_text] if question_text else []
        try:
            variants = generate(
                db, subject, kp_name, titles, limit, extra_topics=kps[1:] or None
            ) or []
        except Exception:
            logger.info("home_variants: generate error key=%s", key, exc_info=True)
            variants = []
        if not variants:
            # 兜底：换「错因」当考点再试一次（题干识别失败时仍尽量出题）
            if fallback_ctx and kp_name != fallback_ctx[:24]:
                try:
                    variants = generate(
                        db, subject, fallback_ctx[:24], titles or [fallback_ctx], limit
                    ) or []
                except Exception:
                    variants = []
        if variants:
            variants_by_key[key] = variants
        else:
            failed_keys.append(key)

    items = build_variant_items(wrong_groups, analyses, variants_by_key)
    return {
        "items": items,
        "generated_at": _utc_now_iso(),
        "wrong_count": len(wrong_groups),
        "failed_keys": failed_keys,
    }
