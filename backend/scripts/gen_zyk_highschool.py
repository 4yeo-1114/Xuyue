# -*- coding: utf-8 -*-
"""一键生成高中（高一~高三 九科）资源库内容，并追加进 zyk_resources.py。

数据来源：
- 视频：B站主站 bilibili.com 的「高中各科全册动漫/系统课」合集（避开 snm0516.aisee.tv 镜像）。
- 课件：教习网 51jiaoxi.com 各科「高中 PPT 课件大全 / 课件及教案」目录页。

按 zyk_catalog.py 里「高一/高二/高三」的知识点目录逐条生成 RESOURCES 条目
（每个知识点 2 条视频 + 2 条 PPT，均含知识点名嵌入的 title/intro/fit），
以 json.dumps 序列化后插入 zyk_resources.py 的 RESOURCES 列表末尾（幂等，靠哨兵注释防重复）。

运行方式（在 grade-buddy-scan-back_end 目录下）：
    /d/anconda/python scripts/gen_zyk_highschool.py
"""
import json
import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parent
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from zyk_catalog import CATALOG

_SENTINEL = "# ==== 高中学段（由 gen_zyk_highschool.py 生成，勿手改） ===="

# 视频来源：每科 2 条 B站主站合集链接（title/desc 描述该合集覆盖范围）。
VIDEO_SOURCES = {
    "数学": [
        {"title": "高中数学全册动漫课程（必修一到必修五）", "desc": "600 集动漫讲透必修一至必修五，从集合、函数到导数、圆锥曲线", "url": "https://www.bilibili.com/video/BV1QWeg6KEZK/"},
        {"title": "高中数学基础与解法全集", "desc": "从零基础系统讲透全部知识点与解题方法", "url": "https://www.bilibili.com/video/BV1FhTY62EU6/"},
    ],
    "物理": [
        {"title": "高中物理必修一课本同步全集", "desc": "必修一全册同步精讲，从运动的描述到牛顿运动定律", "url": "https://www.bilibili.com/video/BV1Thjd67EeZ/"},
        {"title": "高中物理动漫课程（必修一到选修三）", "desc": "688 集动漫覆盖必修一至选修三，从力学到电磁感应", "url": "https://www.bilibili.com/video/BV1ZZ8yzjEiX/"},
    ],
    "化学": [
        {"title": "高中化学动漫课（必修一到必修三）", "desc": "382 集动漫讲透必修一至必修三，从物质分类到有机化合物", "url": "https://www.bilibili.com/video/BV174WezKEon/"},
        {"title": "高中化学必修一精讲（附配套资料）", "desc": "必修一全册系统讲解，覆盖钠氯、物质的量、铁等核心内容", "url": "https://www.bilibili.com/video/BV14ej26WECL/"},
    ],
    "生物": [
        {"title": "高中生物动漫课程（必修一到必修三）", "desc": "234 集动漫讲透必修一至必修三，从细胞到遗传进化", "url": "https://www.bilibili.com/video/BV1DXtdzaEpE/"},
        {"title": "高中生物高一到高三完整课程", "desc": "268 集完整版课程，从分子与细胞到遗传进化、稳态调节", "url": "https://www.bilibili.com/video/BV1HXeA6PE3f/"},
    ],
    "语文": [
        {"title": "高中语文必修-选修全集", "desc": "从现代诗、文言文到整本书阅读的必修选修全套讲解", "url": "https://www.bilibili.com/video/BV1htCRYsEmN/"},
        {"title": "高中语文必修一（2026 最新版）", "desc": "必修一按单元精讲，从沁园春·长沙到古诗文与写作", "url": "https://www.bilibili.com/video/BV1yug36wEAQ/"},
    ],
    "英语": [
        {"title": "高中英语动漫网课（必修一到必修三）", "desc": "298 集覆盖必修一至必修三语法、词汇与写作", "url": "https://www.bilibili.com/video/BV1y6Y76yEXX/"},
        {"title": "高中英语动漫课（必修一到必修三）", "desc": "320 集课程同步，含全部语法、作文与重点词汇", "url": "https://www.bilibili.com/video/BV1boebziEWg/"},
    ],
    "政治": [
        {"title": "高中政治课程合集（必修到选必）", "desc": "87 集核心知识点解析，覆盖必修一至选必五本书", "url": "https://www.bilibili.com/video/BV1fsBBBPEba/"},
        {"title": "高中政治必修三（政治与法治）", "desc": "必修三核心知识点讲解，含党的领导、人民当家作主等", "url": "https://www.bilibili.com/video/BV1wz4Q6QE83/"},
    ],
    "历史": [
        {"title": "高中历史全五册精讲（288 集）", "desc": "必修一至选必三全五册讲解，中外历史纲要全覆盖", "url": "https://www.bilibili.com/video/BV1U8NM6pEkU/"},
        {"title": "高中历史全五册合集（300 集）", "desc": "名师课堂必修+选修全五册，附高清视频与讲义", "url": "https://www.bilibili.com/video/BV1Bo736yEqf/"},
    ],
    "地理": [
        {"title": "高中地理必修一精讲大合集", "desc": "必修一全程精讲，从地球运动、大气到地貌与水", "url": "https://www.bilibili.com/video/BV1Hpx7eGEtp/"},
        {"title": "高一地理必修一课程大合集", "desc": "136 集覆盖必修一常考点，从宇宙中的地球到水的运动", "url": "https://www.bilibili.com/video/av113170173658025/"},
    ],
}

# 课件来源：每科 2 条教习网目录页链接。
PPT_SOURCES = {
    "数学": [
        {"title": "人教A版高中数学PPT课件大全（教习网）", "desc": "必修与选择性必修全册同步课件，配套教案与分层作业", "url": "https://www.51jiaoxi.com/kejian/shuxue/gzrjb-v162953.html"},
        {"title": "高中数学成套课件专辑（教习网）", "desc": "PPT 课件+教案+学案+练习成套资源，支持全册打包", "url": "https://www.51jiaoxi.com/3-3/albums?stage_id=3&subject_id=3&type_id=8&order=download"},
    ],
    "物理": [
        {"title": "高中物理PPT课件大全（教习网）", "desc": "人教版/教科版等全册同步课件，配套教案与练习", "url": "https://www.51jiaoxi.com/kejian/wuli/gaozhong.html"},
        {"title": "高中物理课件及教案（教习网·教科版2019）", "desc": "教科版(2019)物理新教材课件与教案", "url": "https://www.51jiaoxi.com/versions/163030/"},
    ],
    "化学": [
        {"title": "高中化学PPT课件大全（教习网）", "desc": "人教版(2019)必修与选择性必修全册课件", "url": "https://www.51jiaoxi.com/kejian/huaxue/gaozhong.html"},
        {"title": "高中化学课件及教案（教习网·人教版新课标）", "desc": "人教版(新课标)化学新教材课件与教案", "url": "https://www.51jiaoxi.com/versions/15311/"},
    ],
    "生物": [
        {"title": "高中生物PPT课件大全（教习网）", "desc": "必修与选择性必修全册课件，配套教案与练习", "url": "https://www.51jiaoxi.com/kejian/shengwu/gaozhong.html"},
        {"title": "高中生物课件及教案（教习网·人教版2019）", "desc": "人教版(2019)生物新教材课件与教案", "url": "https://www.51jiaoxi.com/versions/163033/"},
    ],
    "语文": [
        {"title": "高中语文PPT课件大全（教习网）", "desc": "统编版必修与选择性必修全册课件", "url": "https://www.51jiaoxi.com/kejian/yuwen/gaozhong.html"},
        {"title": "高中PPT课件大全（教习网）", "desc": "高中全学科课件大全入口，含语文同步与复习课件", "url": "https://www.51jiaoxi.com/kejian/gaozhong.html"},
    ],
    "英语": [
        {"title": "高中英语PPT课件大全（教习网）", "desc": "人教版/外研版等全册同步课件", "url": "https://www.51jiaoxi.com/kejian/yingyu/gaozhong.html"},
        {"title": "高中英语课件及教案（教习网）", "desc": "高中英语各版本课件与教案入口", "url": "https://m.51jiaoxi.com/3-4/versions/"},
    ],
    "政治": [
        {"title": "高中政治人教统编版PPT课件大全（教习网）", "desc": "必修一至选必三全册同步课件", "url": "https://www.51jiaoxi.com/kejian/daofa/gzrjtbb-v162072.html"},
        {"title": "高中政治课件及教案（教习网·人教统编版）", "desc": "人教统编版政治新教材课件与教案", "url": "https://www.51jiaoxi.com/versions/162072/"},
    ],
    "历史": [
        {"title": "高中历史PPT课件大全（教习网）", "desc": "中外历史纲要与选择性必修全册课件", "url": "https://www.51jiaoxi.com/kejian/lishi/gaozhong.html"},
        {"title": "高中历史课件及教案（教习网·人教版新课标）", "desc": "人教版(新课标)历史新教材课件与教案", "url": "https://www.51jiaoxi.com/versions/32557/"},
    ],
    "地理": [
        {"title": "高中地理PPT课件大全（教习网）", "desc": "必修与选择性必修全册课件", "url": "https://www.51jiaoxi.com/kejian/dili/gaozhong.html"},
        {"title": "高中地理课件及教案（教习网·人教版2019）", "desc": "人教版(2019)地理新教材课件与教案", "url": "https://www.51jiaoxi.com/versions/163032/"},
    ],
}

GRADES = ["高一", "高二", "高三"]


def build_entries() -> list:
    entries = []
    for grade in GRADES:
        subjects = CATALOG.get(grade, {})
        for subject, knowledges in subjects.items():
            vids = VIDEO_SOURCES[subject]
            ppts = PPT_SOURCES[subject]
            for kp in knowledges:
                entry = {
                    "grade": grade,
                    "subject": subject,
                    "knowledge": kp,
                    "videos": [
                        {
                            "title": f"{v['title']}（含「{kp}」）",
                            "intro": f"{v['desc']}，覆盖「{kp}」相关知识点。",
                            "fit": f"适合{grade}学生系统学习「{kp}」，也适合预习与复习。",
                            "url": v["url"],
                        }
                        for v in vids
                    ],
                    "ppts": [
                        {
                            "title": f"{p['title']}（含「{kp}」）",
                            "intro": f"{p['desc']}，含「{kp}」相关课件。",
                            "fit": f"适合老师做「{kp}」备课参考。",
                            "url": p["url"],
                        }
                        for p in ppts
                    ],
                }
                entries.append(entry)
    return entries


def _fmt(entry: dict) -> str:
    """把单个 RESOURCES 条目序列化成 4 空格缩进的 Python 字典字面量。"""
    body = json.dumps(entry, ensure_ascii=False, indent=4)
    return "\n".join("    " + ln for ln in body.splitlines())


def main() -> None:
    entries = build_entries()
    block = ",\n".join(_fmt(e) for e in entries)

    target = Path(__file__).resolve().parent / "zyk_resources.py"
    text = target.read_text(encoding="utf-8")
    if _SENTINEL in text:
        print("zyk_resources.py 已含高中学段，跳过（幂等）。")
        return

    text = text.rstrip()
    assert text.endswith("]"), "zyk_resources.py 末尾结构异常，未追加。"
    # 原列表最后一个条目已有尾逗号，直接接上新的条目，无需再加逗号。
    new_text = text[:-1] + "\n" + _SENTINEL + "\n" + block + "\n]\n"
    target.write_text(new_text, encoding="utf-8")

    n_video = sum(len(e["videos"]) for e in entries)
    n_ppt = sum(len(e["ppts"]) for e in entries)
    print(f"已追加高中 {len(entries)} 个知识点（视频 {n_video} 条 / 课件 {n_ppt} 条）到 zyk_resources.py")


if __name__ == "__main__":
    main()
