"""
Backfill job manager — enqueue, claim, and resolve on-demand date-windowed
re-syncs.

A backfill job is a request to re-pull one entity for a SPECIFIC time window
without resetting the entity's incremental state. Useful for repairing data
gaps (e.g. "we have 0 invoices for 2024-02 — re-pull invoices modified
between 2024-01-01 and 2024-04-30 from QB").

Lifecycle: pending -> claimed -> running -> done | error

The coordinator pops the oldest pending backfill job for the company at
session start and inserts it as a SyncTask at the front of the task queue,
so the backfill runs before regular incremental sync work.
"""
from __future__ import annotations

from datetime import datetime, timezone

from supabase import Client

from src.supabase.client import META_SCHEMA
from src.utils.logging import get_logger

logger = get_logger(__name__)

BACKFILL_TABLE = "backfill_jobs"


class BackfillJobManager:
    """Manages qb_meta.backfill_jobs."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(META_SCHEMA).table(BACKFILL_TABLE)

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    def enqueue(
        self,
        company_id: str,
        entity_type: str,
        from_date: str,
        to_date: str,
        filter_type: str = "modified",
        requested_by: str | None = None,
        reason: str | None = None,
    ) -> dict:
        """
        Enqueue a backfill job. The connector will pick it up on the next
        QBWC cycle for this company and run a windowed query against QB.

        Args:
            company_id: e.g. "adk_fragrance"
            entity_type: e.g. "invoices", "bills"
            from_date: ISO datetime, lower bound (inclusive)
            to_date: ISO datetime, upper bound (exclusive in our filter, but
                     QB itself treats both bounds as inclusive — be explicit
                     in the value you pass)
            filter_type: "modified" (TimeModified) or "txn" (TxnDate). Use
                         "txn" when you know records are missing for a window
                         of activity (the slow Q1 2024 case). Use "modified"
                         when records exist but were synced incorrectly.
            requested_by: caller identifier for audit
            reason: free-text note about why this backfill is needed

        Returns the created queue row.
        """
        if filter_type not in ("modified", "txn"):
            raise ValueError(f"filter_type must be 'modified' or 'txn', got {filter_type!r}")

        row = {
            "company_id": company_id,
            "entity_type": entity_type,
            "from_date": from_date,
            "to_date": to_date,
            "filter_type": filter_type,
            "status": "pending",
            "requested_by": requested_by,
            "reason": reason,
        }

        result = self._table().insert(row).execute()
        created = result.data[0] if result.data else row
        logger.info(
            "backfill_enqueued",
            company=company_id,
            entity=entity_type,
            from_date=from_date,
            to_date=to_date,
            filter_type=filter_type,
            job_id=created.get("id"),
        )
        return created

    # ------------------------------------------------------------------
    # Claim
    # ------------------------------------------------------------------

    def claim_pending_for_company(self, company_id: str) -> list[dict]:
        """
        Return all pending backfill jobs for a company, oldest first, marking
        them as 'claimed'. Called once per session at task-queue build time.

        Returns the list of claimed job rows. Caller is responsible for
        calling mark_running -> mark_done/mark_error as the task progresses.
        """
        result = (
            self._table()
            .select("*")
            .eq("company_id", company_id)
            .eq("status", "pending")
            .order("created_at")
            .execute()
        )
        rows = result.data or []
        if not rows:
            return []

        now = datetime.now(timezone.utc).isoformat()
        claimed: list[dict] = []
        for r in rows:
            if r.get("attempts", 0) >= r.get("max_attempts", 3):
                # Permanently fail
                self._table().update({
                    "status": "error",
                    "error_message": "Max attempts exceeded",
                    "completed_at": now,
                    "updated_at": now,
                }).eq("id", r["id"]).execute()
                logger.warning("backfill_max_attempts", job_id=r["id"])
                continue

            self._table().update({
                "status": "claimed",
                "claimed_at": now,
                "attempts": r.get("attempts", 0) + 1,
                "updated_at": now,
            }).eq("id", r["id"]).eq("status", "pending").execute()
            r["status"] = "claimed"
            claimed.append(r)
            logger.info(
                "backfill_claimed",
                company=company_id,
                entity=r["entity_type"],
                job_id=r["id"],
            )
        return claimed

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def mark_running(self, job_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table().update({
            "status": "running",
            "started_at": now,
            "updated_at": now,
        }).eq("id", job_id).execute()

    def mark_done(self, job_id: int, records_synced: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table().update({
            "status": "done",
            "completed_at": now,
            "records_synced": records_synced,
            "error_message": None,
            "updated_at": now,
        }).eq("id", job_id).execute()
        logger.info("backfill_done", job_id=job_id, records=records_synced)

    def mark_error(self, job_id: int, error: str) -> None:
        """
        Record an error. If attempts remain, reset to 'pending' so the next
        QBWC cycle retries; otherwise mark permanently failed.
        """
        now = datetime.now(timezone.utc).isoformat()
        row = self._table().select("attempts, max_attempts").eq("id", job_id).execute()
        if row.data:
            attempts = row.data[0].get("attempts", 1)
            max_attempts = row.data[0].get("max_attempts", 3)
        else:
            attempts = 1
            max_attempts = 3

        if attempts >= max_attempts:
            self._table().update({
                "status": "error",
                "error_message": error[:2000],
                "completed_at": now,
                "updated_at": now,
            }).eq("id", job_id).execute()
            logger.error("backfill_permanently_failed", job_id=job_id, error=error)
        else:
            self._table().update({
                "status": "pending",
                "error_message": error[:2000],
                "claimed_at": None,
                "updated_at": now,
            }).eq("id", job_id).execute()
            logger.warning(
                "backfill_retry",
                job_id=job_id,
                attempts=attempts,
                max_attempts=max_attempts,
                error=error,
            )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_for_company(self, company_id: str, status: str | None = None) -> list[dict]:
        q = self._table().select("*").eq("company_id", company_id).order("created_at", desc=True)
        if status:
            q = q.eq("status", status)
        result = q.execute()
        return result.data or []

    def get_by_id(self, job_id: int) -> dict | None:
        result = self._table().select("*").eq("id", job_id).execute()
        return result.data[0] if result.data else None
