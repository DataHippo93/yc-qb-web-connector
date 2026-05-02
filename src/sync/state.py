"""
Sync state management — reads/writes qb_meta.sync_state in Supabase.
Tracks last sync per (company_id, entity_type).
No per-company schema needed here — this is shared metadata.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import Client

from src.supabase.client import META_SCHEMA
from src.utils.logging import get_logger

logger = get_logger(__name__)

TABLE = "sync_state"


class SyncStateManager:
    """Manages sync state in qb_meta.sync_state."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(META_SCHEMA).table(TABLE)

    def get_state(self, company_id: str, entity_type: str) -> dict | None:
        try:
            result = (
                self._table()
                .select("*")
                .eq("company_id", company_id)
                .eq("entity_type", entity_type)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error("sync_state_get_failed", company=company_id, entity=entity_type, error=str(e))
            return None

    def get_from_date(
        self, company_id: str, entity_type: str, lookback_minutes: int = 5
    ) -> str | None:
        """
        Return ISO datetime string for incremental sync, or None for full sync.
        Applies a lookback buffer to catch near-boundary modifications.
        """
        state = self.get_state(company_id, entity_type)
        if not state or not state.get("last_synced_at"):
            logger.info("full_sync_needed", company=company_id, entity=entity_type)
            return None

        last_sync = datetime.fromisoformat(state["last_synced_at"].replace("Z", "+00:00"))
        from_date = last_sync - timedelta(minutes=lookback_minutes)
        return from_date.strftime("%Y-%m-%dT%H:%M:%S")

    def mark_running(self, company_id: str, entity_type: str) -> None:
        try:
            self._table().upsert(
                {
                    "company_id": company_id,
                    "entity_type": entity_type,
                    "status": "running",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="company_id,entity_type",
            ).execute()
        except Exception as e:
            logger.warning("mark_running_failed", error=str(e))

    def mark_done(
        self,
        company_id: str,
        entity_type: str,
        records_synced: int,
        is_full_sync: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "company_id": company_id,
            "entity_type": entity_type,
            "status": "done",
            "last_synced_at": now,
            "records_synced": records_synced,
            "error_message": None,
            "updated_at": now,
        }
        if is_full_sync:
            row["last_full_sync_at"] = now
        try:
            self._table().upsert(row, on_conflict="company_id,entity_type").execute()
            logger.info(
                "sync_state_done",
                company=company_id,
                entity=entity_type,
                records=records_synced,
                full_sync=is_full_sync,
            )
        except Exception as e:
            logger.error("mark_done_failed", error=str(e))

    def mark_error(self, company_id: str, entity_type: str, error_message: str) -> None:
        try:
            self._table().upsert(
                {
                    "company_id": company_id,
                    "entity_type": entity_type,
                    "status": "error",
                    "error_message": error_message[:2000],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="company_id,entity_type",
            ).execute()
        except Exception as e:
            logger.warning("mark_error_failed", error=str(e))

    def get_all_states(self, company_id: str) -> list[dict]:
        try:
            result = (
                self._table()
                .select("*")
                .eq("company_id", company_id)
                .order("entity_type")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error("get_all_states_failed", company=company_id, error=str(e))
            return []

    def reset_entity(self, company_id: str, entity_type: str) -> None:
        """Force a full re-sync for one entity."""
        try:
            self._table().upsert(
                {
                    "company_id": company_id,
                    "entity_type": entity_type,
                    "status": "pending",
                    "last_synced_at": None,
                    "last_full_sync_at": None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="company_id,entity_type",
            ).execute()
        except Exception as e:
            logger.error("reset_entity_failed", error=str(e))

    def reset_company(self, company_id: str) -> None:
        """Force a full re-sync of all entities for a company."""
        try:
            self._client.schema(META_SCHEMA).table(TABLE).update(
                {
                    "last_synced_at": None,
                    "last_full_sync_at": None,
                    "status": "pending",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("company_id", company_id).execute()
            logger.info("company_reset", company=company_id)
        except Exception as e:
            logger.error("reset_company_failed", company=company_id, error=str(e))

    # ------------------------------------------------------------------
    # Sync log (append-only history) — fixes the silent-failure gap where
    # qb_meta.sync_log was never written to and we couldn't audit past runs.
    # ------------------------------------------------------------------

    def log_run_started(
        self,
        company_id: str,
        entity_type: str,
        is_full_sync: bool,
        ticket: str | None = None,
    ) -> int | None:
        """Insert a sync_log row at run start. Returns the row id."""
        try:
            row = (
                self._client.schema(META_SCHEMA)
                .table("sync_log")
                .insert({
                    "company_id": company_id,
                    "entity_type": entity_type,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "is_full_sync": is_full_sync,
                    "status": "running",
                    "ticket": ticket,
                })
                .execute()
            )
            return row.data[0]["id"] if row.data else None
        except Exception as e:
            logger.warning("sync_log_insert_failed", error=str(e))
            return None

    def log_run_done(
        self,
        log_id: int | None,
        records_synced: int,
        debug_response_xml: str | None = None,
    ) -> None:
        """Mark a sync_log row as done. When records_synced=0 and a raw qbXML
        response is supplied, stash a truncated copy on the row so empty-result
        mysteries can be diagnosed without log-tailing the connector."""
        if log_id is None:
            return
        try:
            update: dict = {
                "status": "done",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "records_synced": records_synced,
            }
            if records_synced == 0 and debug_response_xml:
                update["debug_response_xml"] = debug_response_xml[:4000]
            else:
                # Clear any prior debug payload on a successful (non-zero) sync
                update["debug_response_xml"] = None
            self._client.schema(META_SCHEMA).table("sync_log").update(update).eq(
                "id", log_id
            ).execute()
        except Exception as e:
            logger.warning("sync_log_update_failed", error=str(e))

    def log_run_error(self, log_id: int | None, error_message: str) -> None:
        if log_id is None:
            return
        try:
            self._client.schema(META_SCHEMA).table("sync_log").update({
                "status": "error",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": error_message[:2000],
            }).eq("id", log_id).execute()
        except Exception as e:
            logger.warning("sync_log_error_update_failed", error=str(e))
