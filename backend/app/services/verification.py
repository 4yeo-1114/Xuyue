"""验证码签发 / 校验（登录/注册合规）。

- generate_code：6 位数字。
- issue_code：60s 冷却 + 当日发送量上限，按 channel 走 send_email / send_sms，只存 sha256。
- verify_code：匹配哈希、未过期、未消费；通过后置 consumed=1（一次性，防重放）。

时间口径：统一用 naive UTC（datetime.utcnow()），与 MySQL DATETIME 存储一致，
避免 aware/naive 比较抛 TypeError，也避免依赖服务器本地时区的 func.now()。
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.verification_code import VerificationCode

CODE_LENGTH = 6
CODE_TTL_MINUTES = 10          # 验证码有效期
COOLDOWN_SECONDS = 60          # 同一 target+channel 重发冷却

# 临时旁路：固定短信验证码（config.FIXED_VERIFICATION_CODE）。非空时**仅手机号短信通道**用该
# 固定码（发码不真发、校验固定码直接通过）；邮箱通道始终走真实 SMTP 发送 + 哈希校验。
# 接好阿里云短信后必须清空该配置（见 config.py 注释）。
_FIXED_CODE = (getattr(settings, "FIXED_VERIFICATION_CODE", "") or "").strip()


def generate_code() -> str:
    """6 位数字验证码（首位可为 0，故用 randbelow 而非 randint）。"""
    return "".join(str(secrets.randbelow(10)) for _ in range(CODE_LENGTH))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_target(target: str, channel: str) -> str:
    value = (target or "").strip()
    if channel == "email":
        return value.lower()
    # 手机号：去空格/横线，其余保持（中国号 11 位）
    return value.replace(" ", "").replace("-", "")


def _daily_limit(channel: str) -> int:
    if channel == "email":
        return int(getattr(settings, "EMAIL_DAILY_LIMIT", 20) or 20)
    return int(getattr(settings, "SMS_DAILY_LIMIT", 20) or 20)


def issue_code(db: Session, target: str, channel: str, purpose: str) -> str:
    """签发验证码并发送。返回 code（仅此一次在内存中出现，落库的是哈希）。

    抛 ValueError(消息) 表示业务校验失败（冷却/限频）；抛 RuntimeError 表示通道发送失败。
    """
    from app.email_utils import send_email
    from app.services.sms import send_sms

    if channel not in ("email", "sms"):
        raise ValueError("未知发送渠道")
    if purpose not in ("register", "login", "bind"):
        raise ValueError("未知验证码用途")

    normalized = _normalize_target(target, channel)
    now = datetime.utcnow()

    # 手机号暂用固定验证码（阿里云短信未接通前）：不真发短信、不落库，直接返回固定码。
    # 邮箱始终走下方真实 SMTP 发送。
    if channel == "sms" and _FIXED_CODE:
        return _FIXED_CODE

    # 60s 冷却：同 target+channel 最近一条（不限 purpose）未过冷却期则拒绝
    recent = (
        db.query(VerificationCode)
        .filter(VerificationCode.target == normalized, VerificationCode.channel == channel)
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    if recent is not None and recent.created_at is not None:
        if (now - recent.created_at).total_seconds() < COOLDOWN_SECONDS:
            raise ValueError("发送过于频繁，请稍后再试")

    # 当日发送量上限（防短信轰炸 / 开放邮件转发滥用）
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.target == normalized,
            VerificationCode.channel == channel,
            VerificationCode.created_at >= day_start,
        )
        .count()
    )
    if sent_today >= _daily_limit(channel):
        raise ValueError("今日发送次数已达上限，请明天再试")

    code = generate_code()
    expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)
    db.add(
        VerificationCode(
            target=normalized,
            channel=channel,
            purpose=purpose,
            code_hash=_sha256(code),
            expires_at=expires_at,
            created_at=now,  # 显式 naive UTC，不依赖服务器本地时区的 server_default
        )
    )
    db.commit()

    # 先落库后发送：发送失败也不会留下一条「验证码已在途」的孤儿记录导致的限频占坑
    if channel == "email":
        send_email(
            to_email=normalized,
            subject="叙阅 · 邮箱验证码",
            body=f"您的验证码是 {code}，{CODE_TTL_MINUTES} 分钟内有效。若非本人操作请忽略。",
        )
    else:
        send_sms(normalized, code)

    return code


def verify_code(db: Session, target: str, channel: str, purpose: str, code: str) -> bool:
    """校验验证码；通过后一次性消费。失败原因统一返回 False（由路由层给出笼统提示）。"""
    if not code or not target:
        return False
    # 手机号暂用固定验证码：固定码直接通过；邮箱仍走下方真实哈希校验
    if channel == "sms" and _FIXED_CODE and code.strip() == _FIXED_CODE:
        return True
    normalized = _normalize_target(target, channel)
    code_hash = _sha256(code.strip())

    # 取最近几条未消费、用途匹配的码；匹配哈希且未过期即通过
    rows = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.target == normalized,
            VerificationCode.channel == channel,
            VerificationCode.purpose == purpose,
            VerificationCode.consumed.is_(False),
        )
        .order_by(VerificationCode.created_at.desc())
        .limit(3)
        .all()
    )

    now = datetime.utcnow()
    for row in rows:
        if row.expires_at is not None and now > row.expires_at:
            continue
        if row.code_hash != code_hash:
            continue
        # 命中：一次性消费，防重放
        row.consumed = True
        db.commit()
        return True

    return False
