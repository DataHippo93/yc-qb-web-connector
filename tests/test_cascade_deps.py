"""Tests for cascade dependency wiring on BuildAssembly enqueue.

Covers the contract that BuildAssemblyRequest accepts the new
`depends_on_write_id` field and that WriteQueueManager.enqueue_build_assembly
sets the row's status to 'cascade_waiting' (not 'pending') when a dependency
is declared. Mocks the Supabase client so the test runs without a database.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.main import BuildAssemblyRequest
from src.sync.write_queue import WriteQueueManager


class TestBuildAssemblyRequestModel:
    def test_accepts_depends_on_write_id(self):
        req = BuildAssemblyRequest(
            assembly_list_id="80000042-1234567890",
            quantity=1.0,
            depends_on_write_id=42,
        )
        assert req.depends_on_write_id == 42

    def test_depends_on_write_id_defaults_to_none(self):
        req = BuildAssemblyRequest(
            assembly_list_id="80000042-1234567890",
            quantity=1.0,
        )
        assert req.depends_on_write_id is None

    def test_rejects_non_int_depends_on_write_id(self):
        with pytest.raises(ValueError):
            BuildAssemblyRequest(
                assembly_list_id="80000042-1234567890",
                quantity=1.0,
                depends_on_write_id="not-a-number",  # type: ignore[arg-type]
            )


class _FakeTable:
    """Captures the row passed to insert() so tests can inspect it."""

    def __init__(self) -> None:
        self.last_insert_row: dict | None = None

    def insert(self, row: dict):
        self.last_insert_row = row
        execute = MagicMock()
        execute.execute.return_value = MagicMock(data=[{**row, "id": 999}])
        return execute


def _make_manager() -> tuple[WriteQueueManager, _FakeTable]:
    table = _FakeTable()
    fake_schema = MagicMock()
    fake_schema.table.return_value = table
    fake_client = MagicMock()
    fake_client.schema.return_value = fake_schema
    return WriteQueueManager(fake_client), table


class TestEnqueueWithDependency:
    def test_pending_status_when_no_dependency(self):
        wq, table = _make_manager()
        wq.enqueue_build_assembly(
            company_id="adk_fragrance",
            assembly_list_id="80000042-1",
            quantity=1.0,
        )
        assert table.last_insert_row is not None
        assert table.last_insert_row["status"] == "pending"
        assert table.last_insert_row["depends_on_write_id"] is None

    def test_cascade_waiting_status_when_dependency_declared(self):
        wq, table = _make_manager()
        wq.enqueue_build_assembly(
            company_id="adk_fragrance",
            assembly_list_id="80000042-2",
            quantity=1.0,
            depends_on_write_id=123,
        )
        assert table.last_insert_row is not None
        # When a parent is declared the row goes in waiting; the
        # release_cascade_dependents trigger will flip it to 'pending' once
        # the parent reaches status='completed'.
        assert table.last_insert_row["status"] == "cascade_waiting"
        assert table.last_insert_row["depends_on_write_id"] == 123

    def test_dependency_persisted_on_row(self):
        wq, table = _make_manager()
        wq.enqueue_build_assembly(
            company_id="adk_fragrance",
            assembly_list_id="80000042-3",
            quantity=2.5,
            depends_on_write_id=7,
            external_id="batch-abc",
            external_source="makerhub",
        )
        row = table.last_insert_row
        assert row is not None
        assert row["depends_on_write_id"] == 7
        assert row["external_id"] == "batch-abc"
        assert row["external_source"] == "makerhub"
        assert row["operation"] == "build_assembly"
        assert row["payload"]["assembly_list_id"] == "80000042-3"
        assert row["payload"]["quantity"] == 2.5
