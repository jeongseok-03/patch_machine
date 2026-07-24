"""IMAP/SMTP mail client used by the workspace mail page.

We deliberately connect to the company's *existing* mail account (Naver Works,
Gmail, Daou, ...) instead of running a mail server. The IMAP/SMTP classes are
injected so tests can substitute fakes.
"""

from __future__ import annotations

import contextlib
import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from typing import Any

from negotium.archive.mail_accounts import MailAccount

INBOX_LIMIT = 30
SNIPPET_CHARS = 240
BODY_CHARS = 20_000


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _message_text(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    return bytes(payload).decode(charset, errors="ignore") if payload else ""
                except Exception:
                    continue
        for part in message.walk():
            if part.get_content_type() == "text/html" and not part.get_filename():
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    import re as _re

                    html = bytes(payload).decode(charset, errors="ignore") if payload else ""
                    return _re.sub(r"<[^>]+>", " ", html)
                except Exception:
                    continue
        return ""
    try:
        payload = message.get_payload(decode=True)
        charset = message.get_content_charset() or "utf-8"
        return bytes(payload).decode(charset, errors="ignore") if payload else ""
    except Exception:
        return ""


def _connect(account: MailAccount, imap_factory: Any) -> Any:
    client = imap_factory(account.imap_host, account.imap_port)
    client.login(account.username or account.email, account.password)
    return client


def fetch_inbox(
    account: MailAccount,
    *,
    limit: int = INBOX_LIMIT,
    imap_factory: Any = imaplib.IMAP4_SSL,
) -> list[dict[str, Any]]:
    """Latest inbox headers + text snippets, newest first."""

    client = _connect(account, imap_factory)
    try:
        client.select("INBOX", readonly=True)
        _status, data = client.search(None, "ALL")
        uids = (data[0] or b"").split()
        results: list[dict[str, Any]] = []
        for uid in reversed(uids[-limit:]):
            _status, fetched = client.fetch(uid, "(RFC822)")
            if not fetched or not fetched[0]:
                continue
            raw = fetched[0][1] if isinstance(fetched[0], tuple) else fetched[0]
            message = email.message_from_bytes(bytes(raw))
            text = _message_text(message).strip()
            results.append(
                {
                    "uid": uid.decode(),
                    "subject": _decode(message.get("Subject")),
                    "from": _decode(message.get("From")),
                    "date": _decode(message.get("Date")),
                    "snippet": " ".join(text.split())[:SNIPPET_CHARS],
                }
            )
        return results
    finally:
        with contextlib.suppress(Exception):
            client.logout()


def fetch_message(
    account: MailAccount,
    uid: str,
    *,
    imap_factory: Any = imaplib.IMAP4_SSL,
) -> dict[str, Any] | None:
    client = _connect(account, imap_factory)
    try:
        client.select("INBOX", readonly=True)
        _status, fetched = client.fetch(uid.encode(), "(RFC822)")
        if not fetched or not fetched[0]:
            return None
        raw = fetched[0][1] if isinstance(fetched[0], tuple) else fetched[0]
        message = email.message_from_bytes(bytes(raw))
        return {
            "uid": uid,
            "subject": _decode(message.get("Subject")),
            "from": _decode(message.get("From")),
            "to": _decode(message.get("To")),
            "date": _decode(message.get("Date")),
            "body": _message_text(message).strip()[:BODY_CHARS],
        }
    finally:
        with contextlib.suppress(Exception):
            client.logout()


def send_mail(
    account: MailAccount,
    *,
    to: str,
    subject: str,
    body: str,
    smtp_factory: Any = smtplib.SMTP_SSL,
) -> None:
    message = EmailMessage()
    message["From"] = account.email
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtp_factory(account.smtp_host, account.smtp_port) as client:
        client.login(account.username or account.email, account.password)
        client.send_message(message)


def verify_account(account: MailAccount, *, imap_factory: Any = imaplib.IMAP4_SSL) -> None:
    """Raise if the IMAP credentials do not work."""

    client = _connect(account, imap_factory)
    try:
        client.select("INBOX", readonly=True)
    finally:
        with contextlib.suppress(Exception):
            client.logout()
