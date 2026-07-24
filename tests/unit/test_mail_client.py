"""Tests for the IMAP/SMTP mail client with fake servers."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import ClassVar

from negotium.app.mail_client import fetch_inbox, fetch_message, send_mail
from negotium.archive.mail_accounts import MailAccount, MailAccountStore


def _raw_mail(subject: str, body: str, sender: str = "kim@partner.co.kr") -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "me@company.co.kr"
    message["Subject"] = subject
    message.set_content(body)
    return bytes(message)


class FakeImap:
    def __init__(self, host: str, port: int) -> None:
        self.mails = {
            b"1": _raw_mail("납품 단가 문의", "단가표 회신 부탁드립니다."),
            b"2": _raw_mail("[광고] 특가 안내", "이번 주 특가!"),
        }

    def login(self, username: str, password: str) -> None:
        if password != "app-pass":
            raise RuntimeError("auth failed")

    def select(self, mailbox: str, readonly: bool = False) -> None:
        pass

    def search(self, charset: object, criteria: str) -> tuple[str, list[bytes]]:
        return "OK", [b" ".join(sorted(self.mails.keys()))]

    def fetch(self, uid: bytes, parts: str) -> tuple[str, list[object]]:
        raw = self.mails.get(bytes(uid))
        if raw is None:
            return "OK", [None]
        return "OK", [(b"1 (RFC822)", raw)]

    def logout(self) -> None:
        pass


class FakeSmtp:
    sent: ClassVar[list[EmailMessage]] = []

    def __init__(self, host: str, port: int) -> None:
        pass

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def login(self, username: str, password: str) -> None:
        pass

    def send_message(self, message: EmailMessage) -> None:
        FakeSmtp.sent.append(message)


ACCOUNT = MailAccount(
    email="me@company.co.kr",
    imap_host="imap.test",
    smtp_host="smtp.test",
    password="app-pass",
)


def test_fetch_inbox_parses_headers_and_snippets() -> None:
    items = fetch_inbox(ACCOUNT, imap_factory=FakeImap)
    assert len(items) == 2
    assert items[0]["uid"] == "2"  # newest first
    subjects = {item["subject"] for item in items}
    assert "납품 단가 문의" in subjects
    first = next(item for item in items if item["uid"] == "1")
    assert "단가표" in first["snippet"]


def test_fetch_single_message_body() -> None:
    message = fetch_message(ACCOUNT, "1", imap_factory=FakeImap)
    assert message is not None
    assert message["subject"] == "납품 단가 문의"
    assert "단가표 회신" in message["body"]


def test_send_mail_uses_smtp() -> None:
    FakeSmtp.sent.clear()
    send_mail(
        ACCOUNT,
        to="kim@partner.co.kr",
        subject="Re: 문의",
        body="회신드립니다.",
        smtp_factory=FakeSmtp,
    )
    assert len(FakeSmtp.sent) == 1
    assert FakeSmtp.sent[0]["To"] == "kim@partner.co.kr"


def test_mail_account_store_roundtrip(tmp_path: Path) -> None:
    store = MailAccountStore(tmp_path, master_key="test-master-key")
    store.upsert("alice", ACCOUNT)
    loaded = store.read("alice")
    assert loaded is not None and loaded.password == "app-pass"
    assert loaded.masked()["password"] == "****"
    raw = (tmp_path / "secrets" / "mail_accounts.enc.json").read_text(encoding="utf-8")
    assert "app-pass" not in raw  # encrypted at rest
    store.delete("alice")
    assert store.read("alice") is None
