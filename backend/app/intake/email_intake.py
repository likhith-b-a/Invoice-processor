"""Email intake (IMAP poll) + outbound vendor emails (SMTP). Uses a dedicated mailbox + app password."""
from __future__ import annotations

import email
import imaplib
import smtplib
import threading
import time
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

from .. import config
from ..worker import create_run

state = {"enabled": config.EMAIL_ENABLED, "mailbox": config.IMAP_USER, "last_poll": None,
         "last_error": None, "picked_up": 0, "interval_s": config.IMAP_POLL_SECONDS}


def _h(v) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:  # noqa: BLE001
        return v or ""


def poll_once() -> int:
    n = 0
    with imaplib.IMAP4_SSL(config.IMAP_HOST) as M:
        M.login(config.IMAP_USER, config.IMAP_PASSWORD)
        M.select("INBOX")
        typ, ids = M.search(None, "UNSEEN")
        for num in (ids[0].split() if ids and ids[0] else []):
            typ, msg_data = M.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            sender = parseaddr(msg.get("From", ""))[1].lower()
            meta = {"from": sender, "from_display": _h(msg.get("From")), "subject": _h(msg.get("Subject")),
                    "received": _h(msg.get("Date")), "message_id": msg.get("Message-ID", ""),
                    "internal_forward": sender == config.IMAP_USER.lower()}
            for part in msg.walk():
                fname = _h(part.get_filename())
                ctype = part.get_content_type()
                if part.get_content_disposition() in ("attachment", "inline") and \
                        (fname.lower().endswith(".pdf") or ctype == "application/pdf"):
                    data = part.get_payload(decode=True)
                    if data:
                        create_run(data, fname or "attachment.pdf", "email", meta)
                        n += 1
            M.store(num, "+FLAGS", "\\Seen")
    return n


def _loop():
    while True:
        try:
            got = poll_once()
            state["picked_up"] += got
            state["last_error"] = None
        except Exception as e:  # noqa: BLE001
            state["last_error"] = str(e)[:200]
        state["last_poll"] = time.strftime("%H:%M:%S")
        time.sleep(config.IMAP_POLL_SECONDS)


def start() -> None:
    if config.EMAIL_ENABLED:
        threading.Thread(target=_loop, daemon=True, name="imap-poller").start()


def send_email(to: str, subject: str, body: str, in_reply_to: str = "") -> None:
    if not config.EMAIL_ENABLED:
        raise RuntimeError("Email not configured (IMAP_USER / IMAP_PASSWORD in .env)")
    msg = EmailMessage()
    msg["From"] = config.IMAP_USER
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
        s.starttls()
        s.login(config.IMAP_USER, config.IMAP_PASSWORD)
        s.send_message(msg)
