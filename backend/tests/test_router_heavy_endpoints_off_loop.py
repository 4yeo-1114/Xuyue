# -*- coding: utf-8 -*-
"""识别/答案表重活端点不许是 async def（2026-10-16「本地叙阅点不进去」根因）。

答案表重建=逐槽 VL 转写+PIL 裁剪，分钟级同步重活；跑在 async def 端点里会
堵死事件循环 → 整站所有请求超时（实况：重建 3~4 分钟，期间登录/点文件夹全挂）。
修法 = 改成 def（FastAPI 自动进线程池）+ heavy_slot 总闸排队。
本测锁住：这些端点不得悄悄改回 async def。
"""
from __future__ import annotations

import inspect


def test_recognition_heavy_endpoints_are_sync_defs():
    from app.grading.router import (
        api_apply_scoring_config,
        api_auto_scoring_config,
        api_get_answer_sheet,
        api_get_reference_answer_table,
        api_prepare_reference_layout,
        api_rebuild_reference_answer_table,
        api_save_answer_sheet,
    )

    for fn in (
        api_prepare_reference_layout,
        api_get_reference_answer_table,
        api_rebuild_reference_answer_table,
        api_get_answer_sheet,
        api_save_answer_sheet,
        # 统分：VL 读每题满分也是分钟级重活（2026-10-16 标准答题区路径必触发）
        api_auto_scoring_config,
        api_apply_scoring_config,
    ):
        assert not inspect.iscoroutinefunction(fn), (
            f"{fn.__name__} 必须是 def（进线程池跑）；async def 会把分钟级 VL 重活"
            "堵在事件循环上，整站点不进去"
        )
