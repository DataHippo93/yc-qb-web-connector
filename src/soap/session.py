"""
Session management for QBWC connections.
Each "ticket" represents one sync session with one company.
Sessions are stored in memory (thread-safe dict) or optionally Redis.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
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
    is_incremental: bool      # True = use ModifiedDateRangeFilter
    from_date: str | None     # ISO datetime string for filter
    # Iterator state
    iterator_id: str | None = None
    iterator_remaining: int = 0
    initial_count: int = 0
    records_processed: int = 0
    # Status
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    @property
    def is_done(self) -> bool:
        return self.completed_at is not None

    @property
    def is_iterating(self) -> bool:
        return self.iterator_id is not None and self.iterator_remaining > 0


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
    status: str = "active"  # active | done | error | closing

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


class SessionStore:
    """Thread-safe in-memory session store."""

    def __init__(self) -> None:
        self._sessions: dict[str, SyncSession] = {}
        self._lock = threading.Lock()

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
        with self._lock:
            self._sessions[ticket] = session
        logger.info("session_created", ticket=ticket, company_id=company_id)
        return session

    def get(self, ticket: str) -> SyncSession | None:
        with self._lock:
            session = self._sessions.get(ticket)
            if session and session.is_expired():
                logger.warning("session_expired", ticket=ticket)
                del self._sessions[ticket]
                return None
            if session:
                session.touch()
            return session

    def delete(self, ticket: str) -> None:
        with self._lock:
            session = self._sessions.pop(ticket, None)
        if session:
            logger.info(
                "session_closed",
                ticket=ticket,
                company_id=session.company_id,
                records_synced=session.total_records_synced,
                duration_secs=(
                    datetime.now(timezone.utc) - session.created_at
                ).total_seconds(),
            )

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        with self._lock:
            expired = [t for t, s in self._sessions.items() if s.is_expired()]
            for t in expired:
                del self._sessions[t]
        return len(expired)

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)


# Global session store singleton
_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store
