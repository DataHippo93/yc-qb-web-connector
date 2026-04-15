"""
Write queue manager — enqueue, claim, and resolve outbound QB write operations.

Write operations (BuildAssemblyAdd, etc.) are queued in qb_meta.write_queue
and sent to QuickBooks during the next QBWC sync cycle.

Lifecycle: pending → claimed → sent → completed/failed
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from supabase import Client

from src.qbxml.builders import build_build_assembly_add
from src.supabase.client import META_SCHEMA
from src.utils.logging import get_logger

logger = get_logger(__name__)

WRITE_QUEUE_TABLE = "write_queue"


class WriteQueueManager:
    """Manages the qb_meta.write_queue table."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def _table(self):
        return self._client.schema(META_SCHEMA).table(WRITE_QUEUE_TABLE)

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    def enqueue_build_assembly(
        self,
        company_id: str,
        assembly_list_id: str,
        quantity: float,
        txn_date: str | None = None,
        ref_number: str | None = None,
        memo: str | None = None,
        inventory_site_name: str | None = None,
        external_id: str | None = None,
        external_source: str | None = None,
    ) -> dict:
        """
        Enqueue a BuildAssembly operation.

        Returns the created queue row.
        """
        payload = {
            "assembly_list_id": assembly_list_id,
            "quantity": quantity,
        }
        if txn_date:
            payload["txn_date"] = txn_date
        if ref_number:
            payload["ref_number"] = ref_number
        if memo:
            payload["memo"] = memo
        if inventory_site_name:
            payload["inventory_site_name"] = inventory_site_name

        row = {
            "company_id": company_id,
            "operation": "build_assembly",
            "payload": payload,
            "status": "pending",
            "external_id": external_id,
            "external_source": external_source,
        }

        result = self._table().insert(row).execute()
        created = result.data[0] if result.data else row
        logger.info(
            "write_enqueued",
            operation="build_assembly",
            company=company_id,
            assembly_list_id=assembly_list_id,
            quantity=quantity,
            queue_id=created.get("id"),
        )
        return created

    # ------------------------------------------------------------------
    # Claim & send
    # ------------------------------------------------------------------

    def claim_next(self, company_id: str) -> dict | None:
        """
        Claim the next pending write operation for a company.

        Returns the queue row or None if the queue is empty.
        Uses status transition pending → claimed to prevent double-sends.
        """
        # Find oldest pending item that hasn't exceeded max attempts
        result = (
            self._table()
            .select("*")
            .eq("company_id", company_id)
            .eq("status", "pending")
            .order("created_at")
            .limit(1)
            .execute()
        )

        if not result.data:
            return None

        row = result.data[0]

        if row.get("attempts", 0) >= row.get("max_attempts", 3):
            # Permanently fail this item
            self._table().update({
                "status": "failed",
                "error_message": "Max attempts exceeded",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", row["id"]).execute()
            logger.warning("write_max_attempts", queue_id=row["id"])
            # Try to claim the next one
            return self.claim_next(company_id)

        # Claim it
        now = datetime.now(timezone.utc).isoformat()
        self._table().update({
            "status": "claimed",
            "claimed_at": now,
            "attempts": row.get("attempts", 0) + 1,
        }).eq("id", row["id"]).eq("status", "pending").execute()

        row["status"] = "claimed"
        row["attempts"] = row.get("attempts", 0) + 1

        logger.info("write_claimed", queue_id=row["id"], operation=row["operation"])
        return row

    def mark_sent(self, queue_id: int, request_id: str) -> None:
        """Mark a claimed item as sent (qbXML dispatched to QB)."""
        self._table().update({
            "status": "sent",
            "qb_request_id": request_id,
        }).eq("id", queue_id).execute()

    def mark_completed(
        self, queue_id: int, txn_id: str | None = None
    ) -> None:
        """Mark a sent item as completed (QB confirmed success)."""
        self._table().update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "qb_txn_id": txn_id,
        }).eq("id", queue_id).execute()
        logger.info("write_completed", queue_id=queue_id, txn_id=txn_id)

    def mark_failed(self, queue_id: int, error: str) -> None:
        """
        Mark a sent item as failed. If attempts remain, reset to pending
        for retry; otherwise permanently fail.
        """
        row = self._table().select("attempts, max_attempts").eq("id", queue_id).execute()
        if row.data:
            attempts = row.data[0].get("attempts", 1)
            max_attempts = row.data[0].get("max_attempts", 3)
        else:
            attempts = 1
            max_attempts = 3

        if attempts >= max_attempts:
            self._table().update({
                "status": "failed",
                "error_message": error,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", queue_id).execute()
            logger.error("write_permanently_failed", queue_id=queue_id, error=error)
        else:
            # Reset to pending for retry on next cycle
            self._table().update({
                "status": "pending",
                "error_message": error,
            }).eq("id", queue_id).execute()
            logger.warning(
                "write_retry",
                queue_id=queue_id,
                attempt=attempts,
                max_attempts=max_attempts,
                error=error,
            )

    # ------------------------------------------------------------------
    # Build qbXML for a claimed queue item
    # ------------------------------------------------------------------

    def build_request_xml(self, queue_item: dict, request_id: str = "1") -> str | None:
        """
        Generate the qbXML request string for a claimed queue item.

        Returns the XML string, or None if the operation type is unknown.
        """
        operation = queue_item["operation"]
        payload = queue_item["payload"]

        if operation == "build_assembly":
            return build_build_assembly_add(
                assembly_list_id=payload["assembly_list_id"],
                quantity=payload["quantity"],
                txn_date=payload.get("txn_date"),
                ref_number=payload.get("ref_number"),
                memo=payload.get("memo"),
                inventory_site_name=payload.get("inventory_site_name"),
                request_id=request_id,
            )

        logger.warning("unknown_write_operation", operation=operation)
        return None

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_pending_count(self, company_id: str) -> int:
        """Count pending writes for a company."""
        result = (
            self._table()
            .select("id", count="exact")
            .eq("company_id", company_id)
            .eq("status", "pending")
            .execute()
        )
        return result.count or 0

    def get_by_id(self, queue_id: int) -> dict | None:
        """Get a single queue item by ID."""
        result = self._table().select("*").eq("id", queue_id).execute()
        return result.data[0] if result.data else None

    def get_by_external_id(
        self, external_source: str, external_id: str
    ) -> list[dict]:
        """Look up queue items by external reference."""
        result = (
            self._table()
            .select("*")
            .eq("external_source", external_source)
            .eq("external_id", external_id)
            .execute()
        )
        return result.data or []
