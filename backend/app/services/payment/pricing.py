# -*- coding: utf-8 -*-
"""口径 B · 价格表（**独立于 `billing_config.json`**）。

设计依据：docs/payment/payment-design.md §1.2 / §1.4 / §3.1 / §4.2 / §7.2。

三条硬约束（照设计稿执行）：
1. ⛔ 不复用口径 A 的 `calc_item_fee` / `calc_total` / `load_config`（绑定 `meter_divisor` /
   `round_up` / `free_quota` / `resource_pack`，全是成本口径语义，§1.3 陷阱 2）。
2. ✅ **复用** `billing_pricing.tiered_price()` —— 纯函数、无 I/O、无全局状态（§1.4）。
   本文件是那个「跨口径共享算法」的 B 侧调用者，改动 `tiered_price` 需同时验证两侧。
3. ⛔ 客户的余额 / 套餐额度**绝不**写入任何 `billing_*` 配置（§1.3 陷阱 1）。

单位纪律：**账本一律「分」整数**。`unit_price_fen` 是整数分/份；`tiers` 只用于只读投影
（预估/账单展示），不参与记账 —— 累进阶梯的「分段金额」无法反解回单价，
若用它记账则 `SUM(amount)` 不再等于「单价 × 份数」，§3.3 I3 的可复算性会断。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# 口径 B 的计价项（§3.1 / §4.2）：grade = 主项；upload = 次项，**默认不收**。
KIND_GRADE = "grade"
KIND_UPLOAD = "upload"

# 兜底默认（配置缺失时也不崩；数值本身是 ① 类未拍项，§10 Q4）
_DEFAULT_ITEM = {
    KIND_GRADE: {"billed": True, "unit_price_fen": 50, "tiers": [{"up_to": None, "price": 0.5}]},
    KIND_UPLOAD: {"billed": False, "unit_price_fen": 0, "tiers": []},
}


def _config_path() -> Path:
    """与 `billing_pricing.project_root()/billing_config.json` 并列，⛔ 不合并。"""
    from app.grading.user_paths import project_root

    return project_root() / "payment_pricing.json"


def load_pricing(path: Optional[Path] = None) -> dict[str, Any]:
    """读取口径 B 价格表；文件缺失/损坏 ⇒ 回落内置默认（不抛，不影响批改主流程）。"""
    p = path or _config_path()
    data: dict[str, Any] = {}
    try:
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
    except Exception:
        data = {}

    items = data.get("items") if isinstance(data.get("items"), dict) else {}
    merged: dict[str, dict[str, Any]] = {}
    for kind, default in _DEFAULT_ITEM.items():
        cfg = items.get(kind) if isinstance(items.get(kind), dict) else {}
        merged[kind] = {
            "billed": bool(cfg.get("billed", default["billed"])),
            "unit_price_fen": int(cfg.get("unit_price_fen", default["unit_price_fen"]) or 0),
            "tiers": cfg.get("tiers") if isinstance(cfg.get("tiers"), list) else default["tiers"],
        }
    merged["currency"] = str(data.get("currency") or "CNY")
    return merged


def is_billable(kind: str) -> bool:
    """该计价项是否参与扣费（§3.1：upload 默认不收 ⇒ 只写事件、不产生分录）。"""
    return bool(load_pricing().get(kind, {}).get("billed"))


def unit_price_fen(kind: str = KIND_GRADE) -> int:
    """每份单价（分）。账本用它把「份的净额变化」折算成金额。"""
    return int(load_pricing().get(kind, {}).get("unit_price_fen", 0) or 0)


def billable_kinds() -> set[str]:
    return {k for k in (KIND_GRADE, KIND_UPLOAD) if is_billable(k)}


def estimate_fee_fen(kind: str, quantity: int) -> dict[str, Any]:
    """只读投影：按阶梯估算 quantity 份的费用（分）。✅ 复用 `tiered_price`（§1.4）。

    ⛔ 不用于记账（理由见模块 docstring 第 3 条）。
    """
    from app.services.billing_pricing import tiered_price

    qty = max(0, int(quantity or 0))
    cfg = load_pricing().get(kind, {})
    tiers = cfg.get("tiers") or []
    if qty <= 0 or not tiers:
        return {"kind": kind, "quantity": qty, "amount_fen": 0, "segments": []}
    amount_yuan, segments = tiered_price(float(qty), tiers)
    return {
        "kind": kind,
        "quantity": qty,
        # 元 → 分：四舍五入到整数分（口径 B 不用浮点记账）
        "amount_fen": int(round(float(amount_yuan) * 100)),
        "segments": segments,
    }
