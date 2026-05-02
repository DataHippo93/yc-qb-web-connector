"""
Session management for QBWC connections.
Each "ticket" represents one sync session with one company.

Sessions are stored in Supabase (qb_meta.sessions) for serverless compatibility.
Each SOAP request loads/saves session state from the database.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)

SESSION_TTL_MINUTES = 30  # Sessions expire after 30 minutes of inactivity


@dataclass
class SyncTask:
    """Represents one entity to sync within a session."""
    entity_type: str          # e.g., "customers", "invoices"
    query_name: str           # e.g., "CustomerQueryRq"
    is_incremental: bool      # True = use ModifiedDateRangeFilter (incremental or backfill)
    from_date: str | None     # ISO datetime string for filter (FromModifiedDate)
    # Backfill window — set when this task came from qb_meta.backfill_jobs.
    to_date: str | None = None             # ToModifiedDate upper bound
    txn_from_date: str | None = None       # FromTxnDate (txn-filtered backfill)
    txn_to_date: str | None = None         # ToTxnDate
    backfill_job_id: int | None = None     # FK to qb_meta.backfill_jobs.id
    # Sync log row id (for completion update)
    log_id: int | None = None
    # Identity-check task: when True, this is a CompanyQueryRq probe that must
    # run BEFORE any data tasks. If it fails the strict check, the rest of the
    # session is skipped via session.identity_aborted.
    is_identity_check: bool = False
    # Iterator state
    iterator_id: str | None = None
    iterator_remaining: int = 0
    initial_count: int = 0
    records_processed: int = 0
    # Status
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

    @property
    def is_backfill(self) -> bool:
        return self.backfill_job_id is not None

    @property
    def is_done(self) -> bool:
        return self.completed_at is not None

    @property
    def is_iterating(self) -> bool:
        return self.iterator_id is not None and self.iterator_remaining > 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> SyncTask:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SyncSession:
    """A single QBWC sync session."""
    ticket: str
    company_id: str
    company_file: str
    qbxml_version: tuple[int, int]  # (major, minor)
    # Ordered queue of entities to sync
    task_queue: list[SyncTask] = field(default_factory=list)
    current_task_index: int = 0
    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    errors: list[str] = field(default_factory=list)
    total_records_synced: int = 0
    # State machine
    status: str = "active"  # active | done | error | closing | identity_failed
    # Active write operation (if any) — queue item ID being processed
    active_write_id: int | None = None
    # Set when the company-identity verification task aborts the session.
    # All subsequent tasks are skipped without dispatching a single qbXML query.
    identity_aborted: bool = False
    # The QB file path QBWC most recently reported in sendRequestXML — used as
    # a secondary cross-check inside the identity verifier.
    last_known_company_file: str | None = None

    def touch(self) -> None:
        self.last_activity = datetime.now(timezone.utc)

    def is_expired(self) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TTL_MINUTES)
        return self.last_activity < cutoff

    @property
    def current_task(self) -> SyncTask | None:
        if self.current_task_index < len(self.task_queue):
            return self.task_queue[self.current_task_index]
        return None

    def advance_task(self) -> SyncTask | None:
        """Move to the next task. Returns new current task or None if done."""
        self.current_task_index += 1
        return self.current_task

    @property
    def is_done(self) -> bool:
        return self.current_task_index >= len(self.task_queue)

    @property
    def progress_pct(self) -> int:
        """Return 0–99 progress, 100 only when all tasks done."""
        if not self.task_queue:
            return 100
        if self.is_done:
            return 100
        tasks_done = self.current_task_index
        task = self.current_task
        # Add fractional progress for current task
        task_frac = 0.0
        if task and task.initial_count > 0:
            task_frac = min(task.records_processed / task.initial_count, 0.99)
        total = len(self.task_queue)
        pct = int(((tasks_done + task_frac) / total) * 99)
        return max(1, min(pct, 99))  # 1–99 while in progress

    def to_db_row(self) -> dict:
        """Serialize session to a database row."""
        return {
            "ticket": self.ticket,
            "company_id": self.company_id,
            "company_file": self.company_file,
            "qbxml_version": f"{self.qbxml_version[0]},{self.qbxml_version[1]}",
            "task_queue": json.dumps([t.to_dict() for t in self.task_queue]),
            "current_task_index": self.current_task_index,
            "errors": json.dumps(self.errors),
            "total_records_synced": self.total_records_synced,
            "status": self.status,
            "active_write_id": self.active_write_id,
            "identity_aborted": self.identity_aborted,
            "last_known_company_file": self.last_known_company_file,
            "last_activity": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_db_row(cls, row: dict) -> SyncSession:
        """Deserialize session from a database row."""
        ver_parts = row.get("qbxml_version", "13,0").split(",")
        task_data = row.get("task_queue", "[]")
        if isinstance(task_data, str):
            task_data = json.loads(task_data)
        errors_data = row.get("errors", "[]")
        if isinstance(errors_data, str):
            errors_data = json.loads(errors_data)

        created = row.get("created_at", "")
        if isinstance(created, str) and created:
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        else:
            created = datetime.now(timezone.utc)

        last_act = row.get("last_activity", "")
        if isinstance(last_act, str) and last_act:
            last_act = datetime.fromisoformat(last_act.replace("Z", "+00:00"))
        else:
            last_act = datetime.now(timezone.utc)

        return cls(
            ticket=row["ticket"],
            company_id=row["company_id"],
            company_file=row.get("company_file", ""),
            qbxml_version=(int(ver_parts[0]), int(ver_parts[1])),
            task_queue=[SyncTask.from_dict(t) for t in task_data],
            current_task_index=row.get("current_task_index", 0),
            created_at=created,
            last_activity=last_act,
            errors=errors_data,
            total_records_synced=row.get("total_records_synced", 0),
            status=row.get("status", "active"),
            active_write_id=row.get("active_write_id"),
            identity_aborted=bool(row.get("identity_aborted", False)),
            last_known_company_file=row.get("last_known_company_file"),
        )


class SessionStore:
    """Database-backed session store using Supabase qb_meta.sessions."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from src.supabase.client import get_supabase_client, META_SCHEMA
            self._client = get_supabase_client()
        return self._client

    def _table(self):
        from src.supabase.client import META_SCHEMA
        return self._get_client().schema(META_SCHEMA).table("sessions")

    def create(
        self,
        company_id: str,
        company_file: str = "",
        qbxml_version: tuple[int, int] = (13, 0),
    ) -> SyncSession:
        ticket = str(uuid.uuid4())
        session = SyncSession(
            ticket=ticket,
            company_id=company_id,
            company_file=company_file,
            qbxml_version=qbxml_version,
        )
        self._table().insert(session.to_db_row()).execute()
        logger.info("session_created", ticket=ticket, company_id=company_id)
        return session

    def get(self, ticket: str) -> SyncSession | None:
        try:
            result = self._table().select("*").eq("ticket", ticket).execute()
        except Exception as e:
            logger.error("session_get_failed", ticket=ticket, error=str(e))
            return None

        if not result.data:
            return None

        session = SyncSession.from_db_row(result.data[0])

        if session.is_expired():
            logger.warning("session_expired", ticket=ticket)
            self.delete(ticket)
            return None

        session.touch()
        return session

    def save(self, session: SyncSession) -> None:
        """Persist session state back to the database."""
        try:
            self._table().upsert(
                session.to_db_row(), on_conflict="ticket"
            ).execute()
        except Exception as e:
            logger.error("session_save_failed", ticket=session.ticket, error=str(e))

    def delete(self, ticket: str) -> None:
        try:
            self._table().delete().eq("ticket", ticket).execute()
        except Exception as e:
            logger.error("session_delete_failed", ticket=ticket, error=str(e))
        logger.info("session_closed", ticket=ticket)

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=SESSION_TTL_MINUTES)).isoformat()
        try:
            result = self._table().delete().lt("last_activity", cutoff).execute()
            removed = len(result.data) if result.data else 0
            if removed:
                logger.info("expired_sessions_cleaned", count=removed)
            return removed
        except Exception as e:
            logger.error("session_cleanup_failed", error=str(e))
            return 0

    def active_count(self) -> int:
        try:
            result = self._table().select("ticket", count="exact").eq("status", "active").execute()
            return result.count or 0
        except Exception:
            return 0


# Global session store singleton
_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store
