#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性下载中文字体到 assets/fonts/，Linux 服务器作文留痕用。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.grading.cjk_font import bundled_cjk_font_path, ensure_cjk_font_file


def main() -> int:
    print(f"字体目标路径: {bundled_cjk_font_path()}")
    path = ensure_cjk_font_file()
    if path:
        print(f"成功: {path}")
        return 0
    print(
        "失败：未能下载或保存字体。\n"
        "Linux 服务器可手动执行：\n"
        "  curl -L -o assets/fonts/wqy-zenhei.ttc "
        "\"https://cdn.jsdelivr.net/gh/ITboy/font@master/wqy-zenhei/debian/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc\"\n"
        "或把 Windows 的 C:\\Windows\\Fonts\\msyh.ttc 复制到 assets/fonts/\n"
        "或在 .env 设置 GRADING_FONT_PATH=字体绝对路径"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
