"""监护人同意状态机 —— B0 契约 §6。

状态机：
    not_required ─→ granted ─→ withdrawn ─→ granted ─→ ...（可反复撤回/恢复）
                              version 每次恢复 +1

约束：
  - 撤回不删数据：withdraw 仅置 status='withdrawn'，数据完整保留（审计/数据主体权利）
  - 撤回后冻结：结果在家长端/学生端展示为"已冻结"，标签不出现在活跃画像
  - 恢复带版本：每次 restore 使 version+1，可追溯同意/撤回历史次数
  - 版本不可跳：restore 仅当 status='withdrawn' 时可调用，防止重复确认
  - 首测默认：consent_required=true 的题组，首测写入时 status='not_required'
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

CONSENT_NOT_REQUIRED = "not_required"
CONSENT_GRANTED = "granted"
CONSENT_WITHDRAWN = "withdrawn"

VALID_CONSENT_STATUSES = {CONSENT_NOT_REQUIRED, CONSENT_GRANTED, CONSENT_WITHDRAWN}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_consent() -> dict:
    """首测默认：not_required，version=1，时间戳为空。"""
    return {
        "status": CONSENT_NOT_REQUIRED,
        "version": 1,
        "granted_at": None,
        "withdrawn_at": None,
    }


def is_valid_status(status: str) -> bool:
    return status in VALID_CONSENT_STATUSES


def grant(consent: dict, now: Optional[str] = None) -> tuple[dict, str]:
    """首次授予监护人同意（not_required → granted，version 保持 1）。

    B0 §6.1：not_required ─→ granted（监护人确认 / 教师代确认）。version 首次为 1。
    若已是 granted 则幂等返回；若为 withdrawn 则抛 ValueError（须走 restore）。
    """
    if not isinstance(consent, dict):
        raise ValueError("invalid_consent")
    status = consent.get("status", CONSENT_NOT_REQUIRED)
    if status == CONSENT_GRANTED:
        return consent, "监护人同意已授予"
    if status == CONSENT_WITHDRAWN:
        raise ValueError("withdrawn_use_restore")

    ts = now or _utcnow_iso()
    consent = dict(consent)
    consent["status"] = CONSENT_GRANTED
    consent["version"] = int(consent.get("version", 1) or 1) or 1
    consent["granted_at"] = ts
    consent["withdrawn_at"] = None
    return consent, "监护人同意已授予"


def withdraw(consent: dict, now: Optional[str] = None) -> tuple[dict, str]:
    """撤回监护人同意，冻结结果。

    返回 (新 consent, message)；非法状态抛 ValueError：
      - 已是 withdrawn → already_withdrawn
      - 仍 not_required → not_required（无同意可撤回）
    """
    if not isinstance(consent, dict):
        raise ValueError("invalid_consent")
    status = consent.get("status", CONSENT_NOT_REQUIRED)
    if status == CONSENT_WITHDRAWN:
        raise ValueError("already_withdrawn")
    if status != CONSENT_GRANTED:
        raise ValueError("not_required")

    ts = now or _utcnow_iso()
    consent = dict(consent)
    consent["status"] = CONSENT_WITHDRAWN
    consent["withdrawn_at"] = ts
    # granted_at 保留（审计：曾被授予的时间）
    return consent, "已撤回监护人同意，结果冻结"


def restore(consent: dict, now: Optional[str] = None) -> tuple[dict, str]:
    """撤销撤回，恢复监护人同意（version+1）。

    仅当 status='withdrawn' 时可调用，否则 ValueError：
      - 不是 withdrawn → not_withdrawn
    """
    if not isinstance(consent, dict):
        raise ValueError("invalid_consent")
    status = consent.get("status", CONSENT_NOT_REQUIRED)
    if status != CONSENT_WITHDRAWN:
        raise ValueError("not_withdrawn")

    ts = now or _utcnow_iso()
    version = int(consent.get("version", 1) or 1) + 1
    consent = dict(consent)
    consent["status"] = CONSENT_GRANTED
    consent["version"] = version
    consent["granted_at"] = ts
    consent["withdrawn_at"] = None
    return consent, "已撤销撤回，监护人同意恢复"
