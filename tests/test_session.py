"""Tests for session store."""
from __future__ import annotations

import time
import pytest

from src.soap.session import SessionStore, SyncTask, SyncSession


class TestSessionStore:
    def test_create_and_get(self):
        store = SessionStore()
        session = store.create("natures_storehouse")
        assert session.company_id == "natures_storehouse"
        assert store.active_count() == 1

        retrieved = store.get(session.ticket)
        assert retrieved is not None
        assert retrieved.ticket == session.ticket

    def test_unknown_ticket_returns_none(self):
        store = SessionStore()
        assert store.get("not-a-real-ticket") is None

    def test_delete(self):
        store = SessionStore()
        s = store.create("adk_fragrance")
        store.delete(s.ticket)
        assert store.active_count() == 0
        assert store.get(s.ticket) is None

    def test_multiple_sessions(self):
        store = SessionStore()
        s1 = store.create("natures_storehouse")
        s2 = store.create("adk_fragrance")
        assert store.active_count() == 2
        assert s1.ticket != s2.ticket

    def test_cleanup_expired(self):
        store = SessionStore()
        s = store.create("natures_storehouse")
        # Manually backdate last_activity
        from datetime import timedelta, timezone
        import datetime
        s.last_activity = datetime.datetime.now(timezone.utc) - timedelta(hours=1)
        removed = store.cleanup_expired()
        assert removed == 1
        assert store.active_count() == 0


class TestSyncSession:
    def _make_session(self) -> SyncSession:
        return SyncSession(
            ticket="test-ticket",
            company_id="natures_storehouse",
            company_file="",
            qbxml_version=(13, 0),
        )

    def test_empty_queue_is_done(self):
        s = self._make_session()
        assert s.is_done
        assert s.current_task is None
        assert s.progress_pct == 100

    def test_task_queue_progress(self):
        s = self._make_session()
        s.task_queue = [
            SyncTask("customers", "CustomerQueryRq", False, None),
            SyncTask("invoices", "InvoiceQueryRq", True, "2024-01-01"),
        ]
        s.current_task_index = 0
        assert not s.is_done
        assert s.current_task.entity_type == "customers"
        assert s.progress_pct > 0
        assert s.progress_pct < 100

    def test_advance_task(self):
        s = self._make_session()
        s.task_queue = [
            SyncTask("customers", "CustomerQueryRq", False, None),
            SyncTask("invoices", "InvoiceQueryRq", True, "2024-01-01"),
        ]
        s.current_task_index = 0

        next_task = s.advance_task()
        assert next_task.entity_type == "invoices"
        assert s.current_task_index == 1

        # Advance past end
        result = s.advance_task()
        assert result is None
        assert s.is_done
