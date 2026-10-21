# -*- coding: utf-8 -*-
"""钉钉发送成绩报告 PDF：reportlab 生成 → media/upload 换 media_id → asyncsend_v2 文件消息。

自动（批改/统分完成钩子）与手动（「推送钉钉」按钮）共用本模块，
与 dingtalk_notify 的文字通知走同一 payload，数据口径一致。

钉钉约束：
  - media/upload 返回的 media_id 是临时的（3 天），必须生成后立刻发送；
  - 文件消息 msgtype=file 需要 media_id + file_name；
  - 任何失败只返回 (False, 原因)，绝不外抛影响批改主流程。
"""
from __future__ import annotations

import re
import time
from io import BytesIO
from typing import Optional

import requests

from app.config import settings
from app.dingtalk import _DING_BASE, _ding_token

_TIMEOUT = 30
# 成绩单最多列 N 名，超出在 PDF 里注明总人数（防超大文件撞钉钉上限）
_MAX_ROWS = 300


def _fmt_num(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else str(f)
    except (TypeError, ValueError):
        return str(v)


def _ranking_of(payload: dict, report_kind: str) -> list[dict]:
    """与 dingtalk_notify._build_notify_content 同口径：score_ranking 优先，essay 用 students 转换。"""
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
    return ranking or []


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", str(name or "")).strip()
    return (cleaned[:80] or "成绩报告") + ".pdf"


def _report_filename(payload: dict) -> str:
    class_name = (payload.get("class") or {}).get("class_name") or "班级"
    exam_name = payload.get("exam_name") or "成绩报告"
    return _safe_filename(f"{class_name}_{exam_name}_成绩报告")


def build_score_report_pdf(payload: dict, report_kind: str = "smart_scoring") -> bytes:
    """把通知同款 payload 渲染成成绩报告 PDF（A4，中文）。"""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    # 中文字体复用 worksheet_pdf 的回退链（Windows 系统字体 → 文泉驿 → 内置 CID）
    from app.utils.worksheet_pdf import body_font, title_font

    summary = payload.get("score_summary") or {}
    class_meta = payload.get("class") or {}
    exam_name = str(payload.get("exam_name") or "成绩报告")
    class_name = str(class_meta.get("class_name") or "")
    grade_name = str(class_meta.get("grade") or "")

    count = summary.get("count") or 0
    avg, mx, mn = summary.get("average"), summary.get("max"), summary.get("min")
    full = summary.get("full_score")

    head_verb = {
        "essay": "作文批改完成",
        "manual": "自主阅卷完成",
        "grading_done": "批改完成",
    }.get(report_kind, "统分完成")

    def _score(v) -> str:
        if v is None:
            return "—"
        s = _fmt_num(v)
        if full is not None:
            try:
                s += f"/{_fmt_num(float(full))}"
            except Exception:
                pass
        return s

    t_font, b_font = title_font(), body_font()
    st_title = ParagraphStyle("t", fontName=t_font, fontSize=16, leading=22,
                              alignment=TA_CENTER, spaceAfter=2)
    st_sub = ParagraphStyle("s", fontName=b_font, fontSize=10.5, leading=15,
                            alignment=TA_CENTER, textColor=colors.HexColor("#555555"))
    st_h2 = ParagraphStyle("h2", fontName=t_font, fontSize=12, leading=17,
                           spaceBefore=10, spaceAfter=4)
    st_cell = ParagraphStyle("c", fontName=b_font, fontSize=9.5, leading=13)
    st_cell_c = ParagraphStyle("cc", fontName=b_font, fontSize=9.5, leading=13,
                               alignment=TA_CENTER)
    st_note = ParagraphStyle("n", fontName=b_font, fontSize=8.5, leading=12,
                             textColor=colors.HexColor("#666666"))

    ranking = _ranking_of(payload, report_kind)
    has_scores = any(r.get("score_total") is not None for r in ranking)
    has_wrong = any(r.get("wrong_count") is not None for r in ranking)

    # 摘要行
    if avg is None and mx is None and mn is None:
        summary_line = f"已完成 <b>{count}</b> 人（未统分）"
    else:
        summary_line = (
            f"已完成 <b>{count}</b> 人 ｜ 平均 <b>{_score(avg)}</b> ｜ "
            f"最高 <b>{_score(mx)}</b> ｜ 最低 <b>{_score(mn)}</b>"
        )

    story = [
        Paragraph(f"{class_name or '班级'} · {exam_name}", st_title),
        Paragraph(f"{head_verb}成绩报告" + (f"（{grade_name}）" if grade_name else ""), st_sub),
        Spacer(1, 6),
        Paragraph(summary_line, ParagraphStyle(
            "sm", fontName=b_font, fontSize=11, leading=16, alignment=TA_CENTER)),
    ]
    if payload.get("scope_note"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(str(payload["scope_note"]), st_note))

    # 成绩单表格
    if ranking:
        story.append(Paragraph("成绩单（按分数降序）" if has_scores
                               else "完成情况（按错题数排序）", st_h2))
        header = ["排名", "学生"]
        widths = [16 * mm, 96 * mm]
        if has_scores:
            header.append("得分")
            widths.append(34 * mm)
        if has_wrong:
            header.append("错题")
            widths.append(28 * mm)

        rows = [header]
        for r in ranking[:_MAX_ROWS]:
            box = str(r.get("student_box") or "?")
            row = [str(r.get("rank") or ""), Paragraph(box, st_cell)]
            if has_scores:
                sv = r.get("score_total")
                row.append(Paragraph(
                    "未统分" if sv is None else _score(sv), st_cell_c))
            if has_wrong:
                w = r.get("wrong_count")
                row.append(Paragraph("—" if w is None else str(w), st_cell_c))
            rows.append(row)

        table = Table(rows, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), b_font),
            ("FONTSIZE", (0, 0), (-1, 0), 9.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f5f7fa")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)
        if len(ranking) > _MAX_ROWS:
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"…（共 {len(ranking)} 人，此处仅显示前 {_MAX_ROWS} 名）",
                                   st_note))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"叙阅 GradeBuddy 自动生成 · {time.strftime('%Y-%m-%d %H:%M')}", st_note))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"{class_name}_{exam_name}_成绩报告",
        author="叙阅 GradeBuddy",
    )
    doc.build(story)
    return buf.getvalue()


def upload_file_media(pdf_bytes: bytes, filename: str) -> Optional[str]:
    """钉钉 media/upload?type=file → media_id；失败返回 None。"""
    url = f"{_DING_BASE}/media/upload"
    # type 官方文档为表单字段，同时放 query 兼容不同版本网关
    params = {"access_token": _ding_token(), "type": "file"}
    files = {"media": (filename, pdf_bytes, "application/pdf")}
    try:
        resp = requests.post(url, params=params, data={"type": "file"},
                             files=files, timeout=_TIMEOUT)
        data = resp.json()
    except Exception as e:
        print(f"[dingtalk_pdf] media/upload 请求失败: {e}")
        return None
    if data.get("errcode") != 0:
        print(f"[dingtalk_pdf] media/upload 失败 errcode={data.get('errcode')} "
              f"errmsg={data.get('errmsg')}")
        return None
    media_id = str(data.get("media_id") or "").strip()
    return media_id or None


def send_file_message(userid: str, media_id: str, filename: str) -> bool:
    """asyncsend_v2 msgtype=file，把上传好的文件发到老师工作通知。"""
    agent_id_str = (settings.DINGTALK_AGENT_ID or "").strip()
    if not agent_id_str:
        print("[dingtalk_pdf] DINGTALK_AGENT_ID 为空，跳过 PDF 发送")
        return False
    try:
        agent_id = int(agent_id_str)
    except (TypeError, ValueError):
        print(f"[dingtalk_pdf] DINGTALK_AGENT_ID 非法={agent_id_str!r}")
        return False

    url = f"{_DING_BASE}/topapi/message/corpconversation/asyncsend_v2"
    msg = {
        "agent_id": agent_id,
        "userid_list": userid,
        "msg": {"msgtype": "file",
                "file": {"media_id": media_id, "file_name": filename}},
    }
    try:
        resp = requests.post(
            url, params={"access_token": _ding_token()},
            json=msg, timeout=_TIMEOUT)
        data = resp.json()
    except Exception as e:
        print(f"[dingtalk_pdf] 文件消息请求失败 userid={userid}: {e}")
        return False
    if data.get("errcode") != 0:
        print(f"[dingtalk_pdf] 文件消息失败 userid={userid} "
              f"errcode={data.get('errcode')} errmsg={data.get('errmsg')}")
        return False
    return True


def send_report_pdf(userid: str, payload: dict,
                    report_kind: str = "smart_scoring") -> tuple[bool, str]:
    """生成成绩报告 PDF 并发送到指定钉钉用户。返回 (是否成功, 结果说明)。"""
    try:
        pdf_bytes = build_score_report_pdf(payload, report_kind)
        filename = _report_filename(payload)
        media_id = upload_file_media(pdf_bytes, filename)
        if not media_id:
            return False, "PDF 上传钉钉失败"
        if send_file_message(userid, media_id, filename):
            return True, "成绩报告 PDF 已发送"
        return False, "PDF 文件消息发送失败"
    except Exception as e:
        print(f"[dingtalk_pdf] 发送报告失败 userid={userid!r} kind={report_kind!r}: {e}")
        return False, f"PDF 发送失败：{e}"
