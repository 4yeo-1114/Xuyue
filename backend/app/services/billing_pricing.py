# -*- coding: utf-8 -*-
"""扫描批改 · 计费规则引擎

计费模型对齐七牛云对象存储（Kodo）公开口径：
  - 五大类费用：存储费用 / 流量费用 / 请求费用 / 数据处理费用 / 管理功能费用
  - 按量付费，当月使用、下月初结算
  - 存储量取「月度日均值」：(D1+D2+…+Dn)/n；费用再乘「当月已发生天数/当月总天数」
  - 流量、请求次数按新增累积；不足一个计量单位按一个单位计
  - 抵扣顺序：免费额度 → 资源包 → 阶梯价格
  - 阶梯为「累进阶梯」（类似个税分段），非整体单价

本模块把「试卷扫描批改」这一业务映射到上述模型：

  七牛云计费项             →  本系统计量项            数据来源
  ─────────────────────────────────────────────────────────────
  存储空间费用            →  试卷图片存储            correct_docs 文件（按 mtime 重建日均）
  PUT/DELETE 请求次数     →  上传请求（扫描/上传）    grading_daily_stats.upload_count
  数据处理费用（图片处理） →  AI 批改处理             grading_daily_stats.grade_count
  外网流出流量            →  导出下载流量            （预留，当前无埋点）

单价默认值仅作参考，可在 billing_config.json 中覆盖：
  {"items": {"storage": {"free_quota": 10, "tiers": [...]}}}
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

# ──────────────────────────────────────────────────────────────
# 默认计费规则（单价为参考值，请按实际商务口径调整）
# ──────────────────────────────────────────────────────────────

_DEFAULT_CONFIG: dict[str, Any] = {
    "currency": "CNY",
    "note": (
        "单价默认值参照七牛云对象存储公开口径，仅作参考；"
        "实际计费请以商务合同为准，可通过 billing_config.json 覆盖。"
    ),
    # 抵扣顺序：免费额度 → 资源包 → 阶梯价
    "deduction_order": ["free_quota", "resource_pack", "tiered_price"],
    "items": {
        "storage": {
            "label": "试卷图片存储",
            "category": "存储费用",
            "unit": "GB·月",
            "basis": "monthly_avg",  # 月度日均
            # 容量类计量按实际值计费，不做「不足一单位进位」
            "round_up": False,
            "free_quota": 10.0,
            "resource_pack": 0.0,
            # 累进阶梯：10GB 免费额度之外，50TB 内 0.099，之后递减
            "tiers": [
                {"up_to": 50 * 1024, "price": 0.099},
                {"up_to": 500 * 1024, "price": 0.096},
                {"up_to": None, "price": 0.093},
            ],
        },
        "upload": {
            "label": "上传请求（PUT）",
            "category": "请求费用",
            "unit": "万次",
            "basis": "cumulative",  # 新增累积
            # 次数类计量对齐七牛「不足万次按万次计算」
            "round_up": True,
            "free_quota": 10.0,  # 10 万次
            "resource_pack": 0.0,
            "tiers": [{"up_to": None, "price": 0.0}],  # 上传请求免费
        },
        "grading": {
            "label": "AI 批改处理",
            "category": "数据处理费用",
            "unit": "千次",
            "basis": "cumulative",
            "round_up": True,
            "free_quota": 0.0,
            "resource_pack": 0.0,
            "tiers": [
                {"up_to": 100, "price": 0.60},
                {"up_to": None, "price": 0.45},
            ],
        },
        "download": {
            "label": "导出下载流量",
            "category": "流量费用",
            "unit": "GB",
            "basis": "cumulative",
            "round_up": False,
            "free_quota": 0.0,
            "resource_pack": 0.0,
            "tiers": [
                {"up_to": 100 * 1024, "price": 0.29},
                {"up_to": None, "price": 0.26},
            ],
        },
    },
    # 计量单位换算：业务计数 → 计费单位
    "meter_divisor": {
        "storage": 1.0,  # GB
        "upload": 10000.0,  # 次 → 万次
        "grading": 1000.0,  # 次 → 千次
        "download": 1.0,  # GB
    },
}


def _config_path() -> Path:
    from app.grading.user_paths import project_root

    return project_root() / "billing_config.json"


def load_config() -> dict[str, Any]:
    """加载计费规则：默认值 + billing_config.json 覆盖（文件缺失时用默认值）。"""
    cfg = json.loads(json.dumps(_DEFAULT_CONFIG))  # deep copy
    path = _config_path()
    if not path.is_file():
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            override = json.load(f)
    except Exception:
        return cfg  # 配置损坏时回退默认值，不影响统计接口可用性

    if isinstance(override.get("items"), dict):
        for key, item in override["items"].items():
            if key in cfg["items"] and isinstance(item, dict):
                cfg["items"][key].update(item)
    for key in ("currency", "note"):
        if isinstance(override.get(key), str):
            cfg[key] = override[key]
    return cfg


# ──────────────────────────────────────────────────────────────
# 阶梯计价
# ──────────────────────────────────────────────────────────────


def tiered_price(quantity: float, tiers: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    """累进阶梯计费（类似个税分段）。

    返回 (总金额, 分段明细)。quantity 为已换算到计费单位后的数量，
    且**已扣除**免费额度与资源包。

    示例：tiers=[{up_to:100, price:1},{up_to:None, price:0.5}]，quantity=150
      → 100×1 + 50×0.5 = 125
    """
    if quantity <= 0:
        return 0.0, []

    remaining = float(quantity)
    lower = 0.0
    total = 0.0
    segments: list[dict[str, Any]] = []

    for tier in tiers:
        if remaining <= 0:
            break
        up_to = tier.get("up_to")
        price = float(tier.get("price") or 0.0)
        upper = float("inf") if up_to is None else float(up_to)
        span = upper - lower
        if span <= 0:
            continue
        take = min(remaining, span)
        amount = take * price
        total += amount
        segments.append({
            "from": round(lower, 4),
            "to": (None if up_to is None else round(upper, 4)),
            "quantity": round(take, 4),
            "price": price,
            "amount": round(amount, 4),
        })
        remaining -= take
        lower = upper

    # 若阶梯未覆盖完（配置缺失），按最后一段单价兜底
    if remaining > 0 and segments:
        price = segments[-1]["price"]
        total += remaining * price
        segments.append({
            "from": round(lower, 4),
            "to": None,
            "quantity": round(remaining, 4),
            "price": price,
            "amount": round(remaining * price, 4),
        })

    return round(total, 4), segments


def calc_item_fee(
    key: str,
    raw_quantity: float,
    config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """计算单个计费项：免费额度 → 资源包 → 阶梯价。

    raw_quantity 为业务原始计数（如「次」「GB」）；
    内部换算到计费单位（万次/千次/GB·月）后按抵扣顺序处理。
    """
    cfg = config or load_config()
    item = cfg["items"].get(key)
    if not item:
        return {"key": key, "raw_quantity": raw_quantity, "amount": 0.0}

    divisor = float(cfg["meter_divisor"].get(key, 1.0)) or 1.0
    free_quota = float(item.get("free_quota") or 0.0)
    pack = float(item.get("resource_pack") or 0.0)

    units = raw_quantity / divisor
    # 次数类计量（round_up=True）不足一个单位按一个单位进位，
    # 对齐七牛「不足万次按万次计算」；容量类计量（GB/GB·月）按实际值，不进位。
    if item.get("round_up") and units > 0:
        billed_units = float(int(units) + (1 if units > int(units) else 0))
    else:
        billed_units = round(units, 4) if units > 0 else 0.0

    after_free = max(0.0, billed_units - free_quota)
    after_pack = max(0.0, after_free - pack)
    amount, segments = tiered_price(after_pack, item.get("tiers") or [])

    return {
        "key": key,
        "label": item.get("label"),
        "category": item.get("category"),
        "unit": item.get("unit"),
        "basis": item.get("basis"),
        "raw_quantity": round(float(raw_quantity), 4),
        "billed_units": round(billed_units, 4),
        "free_quota": free_quota,
        "resource_pack": pack,
        "billable_units": round(after_pack, 4),
        "segments": segments,
        "amount": amount,
    }


def calc_total(items_raw: dict[str, float]) -> dict[str, Any]:
    """按抵扣顺序汇总全部计费项。"""
    cfg = load_config()
    rows = [calc_item_fee(k, v, cfg) for k, v in items_raw.items()]
    return {
        "currency": cfg.get("currency", "CNY"),
        "note": cfg.get("note", ""),
        "deduction_order": cfg.get("deduction_order", []),
        "items": rows,
        "total_amount": round(sum(r.get("amount") or 0.0 for r in rows), 4),
    }


# ──────────────────────────────────────────────────────────────
# 存储量计量（按月日均）
# ──────────────────────────────────────────────────────────────


def daily_storage_gb(
    start: date,
    end: date,
    user_id: Optional[str] = None,
) -> dict[str, float]:
    """重建每日存储量（GB）。

    做法：遍历试卷目录下每个文件的 mtime，按日期做「累计求和」——
    某天的存储量 = mtime ≤ 该天的全部文件大小之和。

    注意：已被删除的文件无法回溯，因此历史值会**低估**（当前值准确）。
    这是在不新增存储快照表前提下的近似口径。
    """
    from app.grading.user_paths import get_user_grading_paths, grading_data_all_root

    if user_id:
        docs_dirs = [get_user_grading_paths(user_id).correct_docs]
    else:
        base = grading_data_all_root()
        docs_dirs = (
            [d / "correct_documents" / "test_paper" for d in base.iterdir() if d.is_dir()]
            if base.is_dir()
            else []
        )

    # date -> bytes added on that date
    added: dict[date, int] = {}
    for docs_dir in docs_dirs:
        try:
            if not docs_dir.is_dir():
                continue
            for f in docs_dir.rglob("*"):
                if not f.is_file():
                    continue
                try:
                    st = f.stat()
                except OSError:
                    continue
                d = date.fromtimestamp(st.st_mtime)
                added[d] = added.get(d, 0) + st.st_size
        except OSError:
            continue

    # 累计到 [start, end]
    result: dict[str, float] = {}
    running = sum(size for d, size in added.items() if d < start)
    cursor = start
    while cursor <= end:
        running += added.get(cursor, 0)
        result[cursor.isoformat()] = round(running / (1024**3), 6)
        cursor += timedelta(days=1)
    return result


def monthly_avg_storage_gb(
    year: int,
    month: int,
    user_id: Optional[str] = None,
    up_to_today: bool = True,
) -> dict[str, Any]:
    """月度日均存储量（GB）——对齐七牛「每月平均存储量 = 每天存储量加和 / 月计费天数」。

    up_to_today=True 时只统计到「今天」，用于当月预估；
    否则统计整月。同时返回「已发生天数 / 当月总天数」折算系数。
    """
    import calendar

    days_in_month = calendar.monthrange(year, month)[1]
    first = date(year, month, 1)
    last = date(year, month, days_in_month)

    today = date.today()
    end = min(last, today) if up_to_today else last
    if end < first:
        return {
            "month": f"{year}-{month:02d}",
            "avg_gb": 0.0,
            "elapsed_days": 0,
            "days_in_month": days_in_month,
            "proration": 0.0,
        }

    series = daily_storage_gb(first, end, user_id)
    values = list(series.values())
    avg = sum(values) / len(values) if values else 0.0
    elapsed = len(values)

    return {
        "month": f"{year}-{month:02d}",
        "avg_gb": round(avg, 4),
        "elapsed_days": elapsed,
        "days_in_month": days_in_month,
        # 费用折算系数：当月已发生天数 / 当月总天数
        "proration": round(elapsed / days_in_month, 6),
    }
