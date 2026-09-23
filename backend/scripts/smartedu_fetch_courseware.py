# -*- coding: utf-8 -*-
"""智慧平台「课程教学」课件 PPT + 教学视频下载器（并发 + 幂等）。

数据链（全部公开、无需登录）：
  1) national_lesson/teachingmaterials/version/data_version.json -> part_*.json 教材列表
  2) 每个教材 resources/parts.json -> part_*.json 课时列表（内嵌子资源，含 preview 直链）
  3) 课时子资源：
     - coursewares(pptx): preview.Slide1..N = 每页幻灯片图(公开)  -> 拼成完整 PDF + 封面
     - micro_lesson_video(mp4): preview.frame1 / thumbnails[0] = 视频封面帧(公开)；mp4 本体私桶 -> 封面 + 链接

产出目录：zyk_data/课程教学/{学段}/{学科}/{年级}/{版本}-{册次}/
   课件PPT-{课时}.pdf + .jpg(封面)
   教学视频-{课时}.pdf(链接) + .jpg(视频封面帧)
"""
import argparse
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import requests

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
_scripts = Path(__file__).resolve().parent
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from PIL import Image  # noqa: E402
from app.grading.user_paths import shared_zyk_dir  # noqa: E402
from build_zyk_sample import build_link_pdf  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
NDRS = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/national_lesson"
DV = "https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/national_lesson/teachingmaterials/version/data_version.json"

DEFAULT_SCOPE = [
    ("小学", "语文", "统编版"), ("小学", "数学", "人教版"), ("小学", "英语", "人教版"),
    ("小学", "道德与法治", "统编版"), ("小学", "科学", "教科版"),
    ("初中", "语文", "统编版"), ("初中", "数学", "人教版"), ("初中", "英语", "人教版"),
    ("初中", "物理", "人教版"), ("初中", "化学", "人教版"), ("初中", "生物学", "人教版"),
    ("初中", "历史", "统编版"), ("初中", "道德与法治", "统编版"), ("初中", "地理", "人教版"),
]


def http_get(url, tries=3, timeout=30):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r.content
            if r.status_code in (403, 404):
                return None
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(0.6 * (i + 1))
    return None


def get_json(url):
    data = http_get(url)
    if data is None:
        return None
    try:
        return __import__("json").loads(data)
    except Exception:
        return None


def load_teachingmaterials():
    dv = get_json(DV)
    tms = []
    for u in (dv or {}).get("urls", []):
        part = get_json(u)
        if part:
            tms.extend(part)
    return tms


def tags_of(tm):
    return {t["tag_dimension_id"]: t["tag_name"] for t in tm.get("tag_list", [])}


def match(tags, scope):
    for dan, xk, bb in scope:
        if tags.get("zxxxd") == dan and tags.get("zxxxk") == xk and (not bb or tags.get("zxxbb") == bb):
            return True
    return False


def fetch_lessons(tm_id):
    parts = get_json(f"{NDRS}/teachingmaterials/{tm_id}/resources/parts.json") or []
    lessons = []
    for u in parts:
        part = get_json(u)
        if part:
            lessons.extend(part)
    return lessons


def safe(name):
    return re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name).strip().strip(".")


def slide_urls(preview):
    slides = []
    for k, v in (preview or {}).items():
        m = re.match(r"^Slide(\d+)$", k)
        if m and isinstance(v, str) and v.startswith("http"):
            slides.append((int(m.group(1)), v))
    slides.sort(key=lambda x: x[0])
    return [u for _, u in slides]


def build_pdf_from_images(urls, out, workers):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(http_get, urls))
    imgs = []
    for data in results:
        if not data:
            continue
        try:
            imgs.append(Image.open(BytesIO(data)).convert("RGB"))
        except Exception:
            continue
    if not imgs:
        return False
    imgs[0].save(out, "PDF", save_all=True, append_images=imgs[1:], resolution=100)
    return True


def sub_of(lesson, fmt):
    for s in lesson.get("relations", {}).get("national_course_resource", []):
        if s.get("custom_properties", {}).get("format") == fmt:
            return s
    return None


def catalog_url_of(lesson):
    """视频链接落到该教材的目录页（详情深链需要 contentType/catalogType 精确组合，不可靠）。

    defaultTag 顺序：学段/年级/学科/版本/册次/教材（已浏览器验证可渲染课时列表）。
    """
    tags = {t["tag_dimension_id"]: t["tag_name"] for t in lesson.get("tag_list", [])}
    path = "/".join(tags.get(k, "") for k in ("zxxxd", "zxxnj", "zxxxk", "zxxbb", "zxxcc", "zxxxjjc"))
    return "https://basic.smartedu.cn/syncClassroom?defaultTag=" + urllib.parse.quote(path, safe="/")


def process_lesson(lesson, folder, workers, links_only=False):
    title = safe(lesson.get("title") or (lesson.get("global_title", {}).get("zh-CN") or "未命名"))
    made = []
    pptx = sub_of(lesson, "pptx")
    mp4 = sub_of(lesson, "mp4")

    # 课件 PPT
    if pptx and not links_only:
        cp = pptx.get("custom_properties", {})
        pdf = folder / f"课件PPT-{title}.pdf"
        cover = folder / f"课件PPT-{title}.jpg"
        if not pdf.exists():
            slides = slide_urls(cp.get("preview"))
            if slides:
                build_pdf_from_images(slides, pdf, workers)
        if not cover.exists():
            c = (cp.get("thumbnails") or [None])[0] or (cp.get("preview") or {}).get("Slide1")
            if c:
                cover.write_bytes(http_get(c) or b"")
        if pdf.exists():
            made.append(pdf.name)

    # 教学视频
    if mp4:
        cp = mp4.get("custom_properties", {})
        cover = folder / f"教学视频-{title}.jpg"
        if not links_only and not cover.exists():
            f1 = (cp.get("preview") or {}).get("frame1") or (cp.get("thumbnails") or [None])[0]
            if f1:
                cover.write_bytes(http_get(f1) or b"")
        link = folder / f"教学视频-{title}.pdf"
        if links_only or not link.exists():
            build_link_pdf(
                link, f"{title} 教学视频链接",
                [{"title": title, "intro": f"时长 {cp.get('duration','')}，分辨率 {cp.get('width','')}x{cp.get('height','')}",
                  "fit": "国家中小学智慧教育平台同步课（点此进入教材目录观看）", "url": catalog_url_of(lesson)}],
            )
        made.append(link.name)
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--scope", help="逗号分隔 学段:学科:版本，如 小学:语文:统编版")
    ap.add_argument("--limit-tm", type=int, default=0)
    ap.add_argument("--limit-lessons", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--links-only", action="store_true",
                    help="只重生成「教学视频-*.pdf」链接页（修复 URL），跳过课件/封面下载")
    args = ap.parse_args()

    scope = DEFAULT_SCOPE
    if args.scope:
        scope = [tuple(x.strip().split(":")) for x in args.scope.split(",") if x.strip()]

    root = shared_zyk_dir() / "课程教学"

    print("加载教材列表…", flush=True)
    tms = load_teachingmaterials()
    picked = [tm for tm in tms if match(tags_of(tm), scope)]
    print(f"教材总数 {len(tms)}，命中 {len(picked)}", flush=True)
    if args.limit_tm:
        picked = picked[:args.limit_tm]
    if args.dry_run:
        for tm in picked:
            t = tags_of(tm)
            print(f"  [{t.get('zxxxd')}/{t.get('zxxxk')}/{t.get('zxxnj')}/{t.get('zxxbb')}-{t.get('zxxcc')}] {tm.get('title')}")
        return

    t0 = time.time()
    for i, tm in enumerate(picked, 1):
        t = tags_of(tm)
        folder = root / t.get("zxxxd", "") / t.get("zxxxk", "") / t.get("zxxnj", "") / f"{t.get('zxxbb','')}-{t.get('zxxcc','')}"
        try:
            lessons = fetch_lessons(tm["id"])
            if args.limit_lessons:
                lessons = lessons[:args.limit_lessons]
            folder.mkdir(parents=True, exist_ok=True)
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(process_lesson, l, folder, max(2, args.workers // 2), args.links_only): l for l in lessons}
                for fut in as_completed(futs):
                    try:
                        fut.result()
                    except Exception as e:  # noqa: BLE001
                        print(f"  课时处理失败：{e}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(picked)}] {t.get('zxxxd')}/{t.get('zxxxk')}/{t.get('zxxnj')} 失败：{e}", flush=True)
            continue
        print(f"[{i}/{len(picked)}] {t.get('zxxxd')}/{t.get('zxxxk')}/{t.get('zxxnj')}/{t.get('zxxbb')}-{t.get('zxxcc')} 课时 {len(lessons)} 完成 ({time.time()-t0:.0f}s)", flush=True)

    print(f"\n全部完成，用时 {time.time()-t0:.0f}s，落在 {root}")


if __name__ == "__main__":
    main()
