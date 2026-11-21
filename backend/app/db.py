"""SQLite persistence: runs (one per invoice), their stage events, email drafts, audit log."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlmodel import JSON, Column, Field, Session, SQLModel, create_engine, select

from .config import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)


def now() -> datetime:
    return datetime.now()


class Run(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=now, index=True)
    updated_at: datetime = Field(default_factory=now)
    source: str = "upload"  # upload | email | folder | sample | seed
    source_meta: dict = Field(default_factory=dict, sa_column=Column(JSON))
    filename: str = ""
    file_path: str = ""
    file_hash: str = Field(default="", index=True)

    status: str = "queued"  # queued | running | done | error
    current_stage: str = ""
    error: str = ""

    # outcome
    decision: str = ""  # APPROVE | HOLD | REQUEST_INFO | REJECT | FRAUD_HOLD
    headline: str = ""
    explanation: list = Field(default_factory=list, sa_column=Column(JSON))
    next_actions: list = Field(default_factory=list, sa_column=Column(JSON))
    rules: list = Field(default_factory=list, sa_column=Column(JSON))

    # extracted / normalized data
    extractor: str = ""
    doc_type: str = ""  # text | scanned
    extracted: dict = Field(default_factory=dict, sa_column=Column(JSON))
    normalized: dict = Field(default_factory=dict, sa_column=Column(JSON))
    match: dict = Field(default_factory=dict, sa_column=Column(JSON))

    vendor_id: str = Field(default="", index=True)
    vendor_name: str = ""
    invoice_number: str = Field(default="", index=True)
    invoice_date: str = ""
    po_number: str = Field(default="", index=True)
    currency: str = ""
    subtotal: float = 0.0
    total: float = 0.0
    duration_ms: int = 0

    # human review / approval policy
    required_approvals: list = Field(default_factory=list, sa_column=Column(JSON))  # ["reviewer", "finance_manager"]
    approvals: list = Field(default_factory=list, sa_column=Column(JSON))  # [{name, role, action, comment, ts}]
    review_status: str = ""  # "" | approved | rejected   (final human outcome)
    review_comment: str = ""
    reviewed_at: Optional[datetime] = None


class RunEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    ts: datetime = Field(default_factory=now)
    stage: str
    status: str  # started | ok | warn | fail | skip | info
    title: str = ""
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON))
    duration_ms: int = 0


class EmailDraft(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=now)
    to: str = ""
    subject: str = ""
    body: str = ""
    in_reply_to: str = ""
    status: str = "draft"  # draft | sent | discarded | failed
    sent_at: Optional[datetime] = None
    error: str = ""


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    ts: datetime = Field(default_factory=now)
    actor: str = "system"
    action: str = ""
    note: str = ""


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Tiny migration: add columns introduced after the DB was first created."""
    from sqlalchemy import text
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info('{table.name}')"))}
            for col in table.columns:
                if col.name not in existing:
                    ddl = "JSON DEFAULT '[]'" if isinstance(col.type, JSON) else "TEXT DEFAULT ''"
                    conn.execute(text(f"ALTER TABLE '{table.name}' ADD COLUMN {col.name} {ddl}"))


def session() -> Session:
    return Session(engine, expire_on_commit=False)


def add_event(run_id: int, stage: str, status: str, title: str = "",
              detail: Optional[dict] = None, duration_ms: int = 0) -> None:
    with session() as s:
        s.add(RunEvent(run_id=run_id, stage=stage, status=status, title=title,
                       detail=_jsonable(detail or {}), duration_ms=duration_ms))
        s.commit()


def audit(run_id: int, action: str, note: str = "", actor: str = "system") -> None:
    with session() as s:
        s.add(AuditLog(run_id=run_id, action=action, note=note, actor=actor))
        s.commit()


def update_run(run_id: int, **fields: Any) -> None:
    with session() as s:
        run = s.get(Run, run_id)
        if not run:
            return
        for k, v in fields.items():
            if isinstance(v, (dict, list)):
                v = _jsonable(v)
            setattr(run, k, v)
        run.updated_at = now()
        s.add(run)
        s.commit()


def get_run(run_id: int) -> Optional[Run]:
    with session() as s:
        return s.get(Run, run_id)


def all_runs() -> list[Run]:
    with session() as s:
        return list(s.exec(select(Run).order_by(Run.created_at.desc())))


def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str))
