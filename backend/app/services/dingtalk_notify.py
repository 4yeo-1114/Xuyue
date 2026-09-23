# -*- coding: utf-8 -*-
"""批改/统分完成后自动给老师发钉钉「工作通知」（异步、绝不阻断主流程）。

支持三种 report_kind：
  - "smart_scoring"（默认）：智能批改/参照答案批改统分后，collect_smart_scoring_payload；
  - "essay"：作文批改完成后，collect_essay_payload；
  - "manual"：答题卡自主阅卷全部阅完后，collect_manual_payload。

流程：
  1) user_id → 钉钉 userid（优先 users.dingtalk_userid，否则 users.phone 走 getbymobile 反查，成功后回填）；
  2) 按 report_kind 取聚合，拿到摘要 + 降序成绩单；
  3) 拼 action_card 消息（摘要 + 完整成绩单 + 底部「查看成绩报告」按钮=报告链接）；
  4) asyncsend_v2 发到老师钉钉「工作通知」。

任何一步失败都只记日志、静默降级，绝不外抛影响主流程。
"""
from __future__ import annotations

import threading
from typing import Optional
from urllib.parse import quote

import requests

from app.config import settings
from app.database import SessionLocal
from app.dingtalk import _DING_BASE, _ding_token
from app.grading.user_paths import run_with_grading_user

# 工作通知正文保守上限（字符）。中文 3 字节/字，action_card.markdown 有长度限制，
# 统一按 ~4000 字符截断，避免超长报错。
_MAX_NOTIFY_CHARS = 4000
# 完整成绩单最多列 N 名，超出提示「点按钮看完整名单」
_MAX_RANKING_ROWS = 50
_TIMEOUT = 10


def _get_userid_by_mobile(mobile: str) -> Optional[str]:
    """钉钉 openapi：手机号 → userid（topapi/v2/user/getbymobile）。"""
    url = f"{_DING_BASE}/topapi/v2/user/getbymobile?access_token={_ding_token()}"
    try:
        resp = requests.post(url, json={"mobile": mobile}, timeout=_TIMEOUT)
        data = resp.json()
    except Exception as e:
        print(f"[dingtalk_notify] getbymobile 请求失败 mobile={mobile}: {e}")
        return None
    if data.get("errcode") != 0:
        print(
            f"[dingtalk_notify] getbymobile 失败 mobile={mobile} "
            f"errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
        )
        return None
    result = data.get("result") or {}
    userid = str(result.get("userid") or "").strip()
    return userid or None


def _resolve_dingtalk_userid(user_id: str) -> Optional[str]:
    """user_id → 钉钉 userid。优先已绑定 dingtalk_userid，否则用 phone 反查，成功后回填。"""
    db = SessionLocal()
    try:
        from app.models.user import User

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"[dingtalk_notify] user 不存在 user={user_id!r}")
            return None

        bound = getattr(user, "dingtalk_userid", None)
        if bound and str(bound).strip():
            return str(bound).strip()

        phone = (getattr(user, "phone", None) or "").strip()
        if not phone:
            print(f"[dingtalk_notify] 无 phone 也无 dingtalk_userid user={user_id!r}，跳过")
            return None

        userid = _get_userid_by_mobile(phone)
        if userid:
            # 回填：列存在才写，失败不影响发通知
            try:
                if hasattr(user, "dingtalk_userid"):
                    user.dingtalk_userid = userid
                    db.commit()
            except Exception as e:
                db.rollback()
                print(f"[dingtalk_notify] 回填 dingtalk_userid 失败: {e}")
        return userid
    except Exception as e:
        print(f"[dingtalk_notify] 解析 userid 失败 user={user_id!r}: {e}")
        return None
    finally:
        db.close()


def send_work_notice(userid: str, title: str, body_markdown: str, link_url: str) -> bool:
    """工作通知 asyncsend_v2，action_card（底部可点按钮跳转报告链接）。"""
    agent_id_str = (settings.DINGTALK_AGENT_ID or "").strip()
    if not agent_id_str:
        print("[dingtalk_notify] DINGTALK_AGENT_ID 为空，跳过")
        return False
    try:
        agent_id = int(agent_id_str)
    except (TypeError, ValueError):
        print(f"[dingtalk_notify] DINGTALK_AGENT_ID 非法={agent_id_str!r}")
        return False

    url = f"{_DING_BASE}/topapi/message/corpconversation/asyncsend_v2?access_token={_ding_token()}"
    msg = {
        "agent_id": agent_id,
        "userid_list": userid,
        "msg": {
            "msgtype": "action_card",
            "action_card": {
                "title": title,
                "markdown": body_markdown,
                "single_title": "查看成绩报告",
                "single_url": link_url,
            },
        },
    }
    try:
        resp = requests.post(url, json=msg, timeout=_TIMEOUT)
        data = resp.json()
    except Exception as e:
        print(f"[dingtalk_notify] asyncsend_v2 请求失败 userid={userid}: {e}")
        return False
    ok = data.get("errcode") == 0
    if not ok:
        print(
            f"[dingtalk_notify] asyncsend_v2 失败 userid={userid} "
            f"errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
        )
    return ok


def _fmt_num(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else str(f)
    except (TypeError, ValueError):
        return str(v)


def _build_notify_content(payload: dict, report_kind: str = "smart_scoring") -> tuple[str, str]:
    """返回 (title, body_markdown)：摘要 + 降序完整成绩单 + 截断。"""
    summary = payload.get("score_summary") or {}
    class_meta = payload.get("class") or {}
    exam_name = payload.get("exam_name") or ""
    class_name = class_meta.get("class_name") or ""

    count = summary.get("count") or 0
    avg = summary.get("average")
    mx = summary.get("max")
    mn = summary.get("min")
    full = summary.get("full_score")

    def _fmt_score(v) -> str:
        if v is None:
            return "—"
        s = _fmt_num(v)
        if full is not None:
            try:
                s += f"/{_fmt_num(full)}"
            except Exception:
                pass
        return s

    # 成绩单：smart_scoring/manual 用 score_ranking；essay 用 students（转成同构列表）
    ranking = payload.get("score_ranking")
    if ranking is None and report_kind == "essay":
        ranking = [
            {
                "rank": idx + 1,
                "student_box": s.get("student_box") or "?",
                "score_total": s.get("score_total"),
                "wrong_count": None,
            }
            for idx, s in enumerate(payload.get("students") or [])
        ]
    ranking = ranking or []

    head_verb = {"essay": "作文批改完成", "manual": "自主阅卷完成"}.get(report_kind, "统分完成")
    head = class_name or "班级"
    lines = [
        f"### {head} · {exam_name} {head_verb}",
        f"已完成 **{count}** 人 ｜ 平均 **{_fmt_score(avg)}** ｜ 最高 **{_fmt_score(mx)}** ｜ 最低 **{_fmt_score(mn)}**",
        "",
        "**成绩单（按分数降序）**",
    ]
    for r in ranking[:_MAX_RANKING_ROWS]:
        box = r.get("student_box") or "?"
        score = _fmt_num(r.get("score_total"))
        wrong = r.get("wrong_count")
        suffix = f"（错 {wrong} 题）" if wrong is not None else ""
        lines.append(f"{r.get('rank')}. {box}：{score} 分{suffix}")
    if len(ranking) > _MAX_RANKING_ROWS:
        lines.append(f"…（共 {len(ranking)} 人，完整名单点下方按钮查看）")

    body = "\n".join(lines)
    if len(body) > _MAX_NOTIFY_CHARS:
        body = body[:_MAX_NOTIFY_CHARS - 24] + "\n…（内容过长已截断，点按钮查看完整名单）"
    return "批改完成通知", body


def _build_report_link(folder_safe: str) -> str:
    """报告链接 = 前端公网 base + /dingtalk/entry?corpId=..&redirect=<urlencode 内部路径>。"""
    base = (settings.DINGTALK_FRONTEND_BASE_URL or "").strip().rstrip("/")
    if not base:
        return ""
    inner = f"/nav/grading-start?folder={folder_safe}"
    redirect = quote(inner, safe="")
    corp_id = (settings.DINGTALK_CORP_ID or "").strip()
    return f"{base}/dingtalk/entry?corpId={corp_id}&redirect={redirect}"


def _notify_impl(user_id: str, safe: str, report_kind: str = "smart_scoring") -> None:
    """线程内真正干活（已处于 grading 用户上下文，collector 依赖 correct_docs_dir() 走 contextvar）。"""
    try:
        userid = _resolve_dingtalk_userid(user_id)
        if not userid:
            return

        from app.services.ai_auto_report.collector import (
            collect_essay_payload,
            collect_manual_payload,
            collect_smart_scoring_payload,
        )

        if report_kind == "essay":
            payload = collect_essay_payload(safe)
        elif report_kind == "manual":
            payload = collect_manual_payload(safe)
        else:
            payload = collect_smart_scoring_payload(safe)

        title, body = _build_notify_content(payload, report_kind)
        link = _build_report_link(safe)
        if link:
            send_work_notice(userid, title, body, link)
        else:
            print("[dingtalk_notify] DINGTALK_FRONTEND_BASE_URL 为空，无法生成报告链接，改发纯文本")
            send_work_notice(userid, title, body + "\n\n（未配置前端公网地址，无法生成报告链接）", "")
    except Exception as e:
        print(f"[dingtalk_notify] 推送失败 user={user_id!r} safe={safe!r} kind={report_kind!r}: {e}")


def notify_grading_done(user_id: str, safe: str, report_kind: str = "smart_scoring") -> None:
    """批改/统分完成钩子：立即返回；独立 daemon 线程内恢复 grading 上下文后推送。"""
    uid = str(user_id or "").strip()
    s = str(safe or "").strip()
    if not uid or uid == "unknown" or not s:
        return
    # 四项钉钉配置缺一不可，缺了直接跳过（不报错、不阻塞）
    if not (
        settings.DINGTALK_CORP_ID
        and settings.DINGTALK_APP_KEY
        and settings.DINGTALK_APP_SECRET
        and settings.DINGTALK_AGENT_ID
    ):
        print("[dingtalk_notify] 钉钉配置不完整，跳过")
        return
    threading.Thread(
        target=lambda: run_with_grading_user(uid, _notify_impl, uid, s, report_kind),
        daemon=True,
    ).start()
