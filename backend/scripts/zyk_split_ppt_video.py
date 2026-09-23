# -*- coding: utf-8 -*-
"""把每个「册次」文件夹里的 课件PPT-* 和 教学视频-* 拆成两个子文件夹。

结构变化（以 教科版-上册 为例）：
    教科版-上册/{课件PPT-*.pptx|.jpg, 教学视频-*.pdf|.jpg}   （混在一起）
  → 教科版-上册/课件PPT/课件PPT-*.pptx + 封面.jpg
                /教学视频/教学视频-*.pdf + 封面.jpg

同时删除被 .pptx 取代的 课件PPT-*.pdf。封面 .jpg 跟随各自文件移动，保持「同 stem .jpg」封面约定。

运行：venv python scripts/zyk_split_ppt_video.py
幂等：子文件夹已存在则直接搬入。
"""
import sys
import shutil
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from app.grading.user_paths import shared_zyk_dir


def split_folder(folder: Path) -> tuple[int, int]:
    """拆分单个册次文件夹；返回 (移入PPT数, 移入视频数)。"""
    ppt_dir = folder / "课件PPT"
    vid_dir = folder / "教学视频"
    moved_ppt = moved_vid = 0
    for f in list(folder.iterdir()):
        if not f.is_file():
            continue
        name = f.name
        if name.startswith("课件PPT-"):
            if f.suffix.lower() == ".pdf":
                f.unlink()  # 已被 .pptx 取代
            else:
                ppt_dir.mkdir(exist_ok=True)
                shutil.move(str(f), str(ppt_dir / name))
                moved_ppt += 1
        elif name.startswith("教学视频-"):
            vid_dir.mkdir(exist_ok=True)
            shutil.move(str(f), str(vid_dir / name))
            moved_vid += 1
    return moved_ppt, moved_vid


def main() -> None:
    root = shared_zyk_dir() / "课程教学"
    # 只处理直接含 课件PPT-*/教学视频-* 文件的叶子文件夹（先收集再拆，避免动到新子目录）
    leaf_dirs = []
    for d in sorted(root.rglob("*")):
        if not d.is_dir():
            continue
        if any(f.name.startswith(("课件PPT-", "教学视频-")) for f in d.iterdir() if f.is_file()):
            leaf_dirs.append(d)

    print(f"待拆分 {len(leaf_dirs)} 个册次文件夹", flush=True)
    total_ppt = total_vid = deleted_pdf = 0
    for i, d in enumerate(leaf_dirs, 1):
        before_pdf = len(list(d.glob("课件PPT-*.pdf")))
        p, v = split_folder(d)
        total_ppt += p
        total_vid += v
        deleted_pdf += before_pdf
        if i % 50 == 0 or i == len(leaf_dirs):
            print(f"[{i}/{len(leaf_dirs)}] PPT={total_ppt} 视频={total_vid} 删PDF={deleted_pdf}", flush=True)
    print(f"拆分完成：移PPT={total_ppt} 移视频={total_vid} 删PDF={deleted_pdf}", flush=True)


if __name__ == "__main__":
    main()
