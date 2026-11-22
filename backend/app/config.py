import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
MASTER_DIR = DATA / "master"
SAMPLES_DIR = DATA / "samples"
INBOX_DIR = DATA / "inbox"
UPLOADS_DIR = DATA / "uploads"
PROCESSED_DIR = DATA / "processed"
DB_PATH = DATA / "app.db"
FRONTEND_DIST = ROOT / "frontend" / "dist"

for d in (SAMPLES_DIR, INBOX_DIR, UPLOADS_DIR, PROCESSED_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
# rotated on quota errors; each model has its own free-tier quota
GEMINI_MODELS = [m.strip() for m in os.getenv(
    "GEMINI_MODELS",
    f"{GEMINI_MODEL},gemini-3.5-flash-lite,gemini-flash-lite-latest,gemini-2.5-flash-lite,gemini-3.8-flash").split(",")
    if m.strip()]
GEMINI_TIMEOUT_S = int(os.getenv("GEMINI_TIMEOUT_S", "40"))
# demo mode: reuse an earlier Gemini read of the same file before calling Gemini again
CACHE_FIRST = os.getenv("CACHE_FIRST", "0").strip().lower() in ("1", "true", "yes")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b")

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER", "").strip()
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "").replace(" ", "")
IMAP_POLL_SECONDS = int(_f("IMAP_POLL_SECONDS", 20))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_f("SMTP_PORT", 587))

STAGE_DELAY_MS = int(_f("STAGE_DELAY_MS", 350))
PRICE_TOLERANCE_PCT = _f("PRICE_TOLERANCE_PCT", 2)
AMOUNT_TOLERANCE_PCT = _f("AMOUNT_TOLERANCE_PCT", 2)

# thresholds
CONFIDENCE_THRESHOLD = 0.75
PO_INFER_THRESHOLD = 0.72
FUZZY_DUP_AMOUNT_PCT = 1.0
FUZZY_DUP_DAYS = 14
MAX_INVOICE_AGE_DAYS = 180

# approval policy: invoices above this (USD equivalent) are never auto-approved
APPROVAL_LIMIT_USD = _f("APPROVAL_LIMIT_USD", 10000)
FX_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "INR": 0.012, "CAD": 0.73, "AUD": 0.66}
ROLES = {"reviewer": "AP reviewer", "finance_manager": "Finance manager"}

EMAIL_ENABLED = bool(IMAP_USER and IMAP_PASSWORD)
