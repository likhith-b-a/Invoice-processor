"""Email sample invoices to the AP inbox (uses the same mailbox credentials from .env).

usage: .venv/Scripts/python scripts/send_test_emails.py 01 03      (prefixes of sample files; default: all)
"""
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import config  # noqa: E402

if not config.EMAIL_ENABLED:
    sys.exit("Set IMAP_USER and IMAP_PASSWORD in .env first.")
wanted = sys.argv[1:]
files = sorted(p for p in config.SAMPLES_DIR.glob("*.pdf") if not wanted or any(p.name.startswith(w) for w in wanted))
with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
    s.starttls()
    s.login(config.IMAP_USER, config.IMAP_PASSWORD)
    for f in files:
        m = EmailMessage()
        m["From"], m["To"] = config.IMAP_USER, config.IMAP_USER
        m["Subject"] = f"Invoice attached - {f.stem.split('_', 1)[1].replace('_', ' ')}"
        m.set_content("Hello AP team,\n\nPlease find our invoice attached.\n\nRegards")
        m.add_attachment(f.read_bytes(), maintype="application", subtype="pdf", filename=f.name)
        s.send_message(m)
        print("sent", f.name)
