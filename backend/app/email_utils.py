import smtplib
from email.message import EmailMessage
from typing import Iterable, Mapping, Optional


def send_email(
    to_email: str,
    subject: str,
    body: str,
    attachments: Optional[Iterable[Mapping[str, object]]] = None,
) -> None:
    try:
        from app.config import settings
    except Exception:
        settings = None

    host = str(getattr(settings, "SMTP_HOST", "") or "").strip() if settings is not None else ""
    port = int(getattr(settings, "SMTP_PORT", 587) or 587) if settings is not None else 587
    use_ssl = bool(getattr(settings, "SMTP_USE_SSL", False)) if settings is not None else False
    username = str(getattr(settings, "SMTP_USERNAME", "") or "").strip() if settings is not None else ""
    password = str(getattr(settings, "SMTP_PASSWORD", "") or "").strip() if settings is not None else ""
    from_email = str(getattr(settings, "SMTP_FROM", "") or "").strip() if settings is not None else ""
    if not from_email:
        from_email = username

    if not host or not username or not password or not from_email:
        raise RuntimeError("SMTP 未配置")
    if not to_email:
        raise RuntimeError("收件人邮箱为空")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body or "")
    for item in attachments or []:
        filename = str(item.get("filename") or "attachment.bin")
        content = item.get("content") or b""
        if isinstance(content, str):
            content = content.encode("utf-8")
        maintype = str(item.get("maintype") or "application")
        subtype = str(item.get("subtype") or "octet-stream")
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    if use_ssl or port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as s:
            s.ehlo()
            s.login(username, password)
            s.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=20) as s:
        s.ehlo()
        # M7：STARTTLS 必须协商成功才继续，否则拒绝发送（fail-closed），
        # 避免账号密码以明文在链路上传输。
        try:
            s.starttls()
            s.ehlo()
        except Exception as e:
            raise RuntimeError(f"SMTP STARTTLS 协商失败，拒绝发送以保护凭据: {e}") from e
        s.login(username, password)
        s.send_message(msg)
