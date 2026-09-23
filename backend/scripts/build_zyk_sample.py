# -*- coding: utf-8 -*-
"""资源库样板数据生成：三年级/数学/分数，含「视频链接 PDF」和「公开课件 PPT 链接 PDF」。

结构（落在全局共享目录 grading_data_all/_shared/zyk_data 下）：
    三年级/数学/分数/
        教学视频-分数的初步认识.pdf
        公开课件PPT-分数的初步认识.pdf

PDF 内容：标题 + 讲什么 + 适合谁 + 可点击的原链接（点一下跳转）。

运行方式（在 grade-buddy-scan-back_end 目录下）：
    /d/anconda/python scripts/build_zyk_sample.py
"""
import sys
from pathlib import Path

# 把项目根加入 sys.path，便于 import app 模块
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

from app.grading.user_paths import shared_zyk_dir

# 注册简体中文字体（reportlab 内置 CID 字体，无需外部字体文件）
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

FONT = "STSong-Light"
LINK_BLUE = "#2563eb"


def _style(size: float, **kw) -> ParagraphStyle:
    base = dict(fontName=FONT, fontSize=size, leading=size * 1.6, textColor=colors.black, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(str(size), **base)


TITLE = _style(16, spaceAfter=2 * mm)
SUB = _style(11, textColor=colors.HexColor("#555555"))
BODY = _style(11)
LINK = _style(11, textColor=colors.HexColor(LINK_BLUE))


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_link_pdf(out: Path, title: str, items: list[dict]) -> None:
    """生成一份「链接清单」PDF：每个 item = {title, intro, fit, url}。"""
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    story = [Paragraph(_escape(title), TITLE), HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#cccccc"), spaceAfter=5 * mm)]
    for i, it in enumerate(items, 1):
        story.append(Paragraph(f"{i}. {_escape(it['title'])}", SUB))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<b>讲什么：</b>{_escape(it['intro'])}", BODY))
        story.append(Spacer(1, 1.5 * mm))
        story.append(Paragraph(f"<b>适合谁：</b>{_escape(it['fit'])}", BODY))
        story.append(Spacer(1, 1.5 * mm))
        url = it["url"]
        href = url.replace("&", "&amp;")
        story.append(Paragraph(f"<b>原链接：</b><a href=\"{href}\" color=\"{LINK_BLUE}\">{_escape(url)}</a>", LINK))
        story.append(Spacer(1, 5 * mm))
    doc.build(story)


# ── 样板资源数据（后续可在此扩充更多年级/学科/知识点）──────────────
SAMPLE = [
    {
        "grade": "三年级",
        "subject": "数学",
        "knowledge": "分数",
        "videos": [
            {
                "title": "人教版数学三年级上册《分数的初步认识》第一课时",
                "intro": "用分月饼等生活情境引入「平均分」，认识二分之一、三分之一、四分之一，讲解分子、分数线、分母的读写法。",
                "fit": "适合三年级第一次接触分数、需要理解「平均分」和「几分之一」含义的学生；也适合基础薄弱、想重新打基础的学生。",
                "url": "https://www.bilibili.com/video/BV1sFyPYvE3v/",
            },
            {
                "title": "2025 秋 小学数学三年级上册《分数的认识》第 1 课时",
                "intro": "2025 版教材同步课，约 9 分钟，紧扣教材第六单元，讲清「把整体平均分成几份，每份是几分之一」。",
                "fit": "适合使用 2025 新版教材的三年级学生同步预习或课后复习。",
                "url": "https://www.bilibili.com/video/BV1cUmcBxEsK/",
            },
            {
                "title": "人教版数学三年级上册《分数的简单计算》",
                "intro": "分数初步认识后的延伸内容，讲同分母分数的简单加减，视频约 16 分钟。",
                "fit": "适合已经认识几分之一、想进一步学习同分母分数加减的三年级学生。",
                "url": "https://www.bilibili.com/video/BV1oqHLeJEMw/",
            },
        ],
        "ppts": [
            {
                "title": "人教版小学数学三年级上册《分数的初步认识》课件（30 张 PPT）",
                "intro": "完整教学设计流程（学习准备、学习目标、教学过程、拓展延伸、反馈小测），配 12 张预览图。",
                "fit": "适合老师备课直接参考，或打印出来带学生按流程学习。",
                "url": "https://edu.21cnjy.com/p-26256544.html",
            },
            {
                "title": "《分数的初步认识》PPT 课件（教习网，人教版三年级上册）",
                "intro": "含「几分之一」「几分之几」「同分母分数大小比较」「分数的简单计算」系列课件，多套标注公开课获奖课件。",
                "fit": "适合老师按课时挑选课件，覆盖分数单元全部课时。",
                "url": "https://www.51jiaoxi.com/kejian/shuxue/xxrjbsnjsc-c106842/",
            },
        ],
    },
]


def main() -> None:
    root = shared_zyk_dir()
    for entry in SAMPLE:
        folder = root / entry["grade"] / entry["subject"] / entry["knowledge"]
        folder.mkdir(parents=True, exist_ok=True)
        video_pdf = folder / f"教学视频-{entry['knowledge']}.pdf"
        ppt_pdf = folder / f"公开课件PPT-{entry['knowledge']}.pdf"
        build_link_pdf(video_pdf, f"{entry['grade']}·{entry['subject']}·{entry['knowledge']} 教学视频链接", entry["videos"])
        build_link_pdf(ppt_pdf, f"{entry['grade']}·{entry['subject']}·{entry['knowledge']} 公开课件 PPT 链接", entry["ppts"])
        print(f"已生成 {folder}")
        print(f"  ├─ {video_pdf.name}")
        print(f"  └─ {ppt_pdf.name}")
    print(f"\n共享资源库根目录：{root}")


if __name__ == "__main__":
    main()
