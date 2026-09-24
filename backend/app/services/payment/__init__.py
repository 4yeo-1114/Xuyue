"""口径 B（向老师收费）服务层。

设计依据：docs/payment/payment-design.md。
⛔ 与口径 A（平台成本核算，`app/services/billing_pricing.py` + `grading_daily_stats`）物理分离：
  两套端点、两套数据源、两套配置（`payment_pricing.json` vs `billing_config.json`）。
"""
