"""
Write queue manager — enqueue, claim, and resolve outbound QB write operations.

Write operations (BuildAssemblyAdd, etc.) are queued in qb_meta.write_queue
and sent to QuickBooks during the next QBWC sync cycle.

Lifecycle: pending → claimed → sent → completed/failed
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from supabase import Client

from src.qbxml.builders import build_build_assembly_add, build_build_assembly_del
from src.supabase.client import META_SCHEMA
from src.utils.config import get_settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

WRITE_QUEUE_TABLE = "write_queue"


def _notify_makerhub(
    queue_id: int,
    status: str,
    qb_txn_id: str | None,
    is_pending: bool | None,
    error_message: str | None,
) -> None:
    """Fire-and-forget POST to MakerHub announcing a write_queue terminal
    transition. The MakerHub-side pg_cron poll is the source-of-truth
    fallback; this just shortens latency from ~60 s to sub-second when the
    QBWC machine has outbound HTTPS to the MakerHub deployment.

    No-op when MAKERHUB_CALLBACK_URL or MAKERHUB_CALLBACK_SECRET are
    unset. Errors are logged at WARNING and never re-raised — failure to
    notify must NOT roll back the QB write.
    """
    settings = get_settings()
    url = settings.makerhub_callback_url
    secret = settings.makerhub_callback_secret
    if not url or not secret:
        return

    payload = json.dumps(
        {
            "queue_id": queue_id,
            "status": status,
            "qb_txn_id": qb_txn_id,
            "is_pending": is_pending,
            "error_message": error_message,
        }
    ).encode("utf-8")

    def _post() -> None:
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {secret}",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status >= 300:
                    logger.warning(
                        "makerhub_callback_non_2xx",
                        queue_id=queue_id,
                        http_status=resp.status,
                    )
        except urllib.error.URLError as e:
            logger.warning(
                "makerhub_callback_failed",
                queue_id=queue_id,
                error=str(e),
            )
        except Exception as e:  # never let this take down the QB write
            logger.warning(
                "makerhub_callback_exception",
                queue_id=queue_id,
                error=str(e),
            )

    # Daemon thread = doesn't block the QBWC response cycle and dies with
    # the process if the connector restarts mid-flight.
    threading.Thread(target=_post, daemon=True).start()


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
        mark_pending_if_required: bool = False,
        inventory_site_name: str | None = None,
        lot_number: str | None = None,
        external_id: str | None = None,
        external_source: str | None = None,
        depends_on_write_id: int | None = None,
    ) -> dict:
        """
        Enqueue a BuildAssembly operation.

        When `mark_pending_if_required=True`, the qbXML request includes
        <MarkPendingIfRequired>true</MarkPendingIfRequired>, so QB records the
        build as pending when any component is short (instead of returning
        error 3370). The response's <IsPending> flag is surfaced back through
        the queue row's `is_pending` column on completion.

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
        if mark_pending_if_required:
            payload["mark_pending_if_required"] = True
        if inventory_site_name:
            payload["inventory_site_name"] = inventory_site_name
        if lot_number:
            payload["lot_number"] = lot_number

        # When a dependency is declared, mark the row 'cascade_waiting' so the
        # dispatcher (which only claims status='pending') skips it. The
        # qb_meta.release_cascade_dependents trigger flips it to 'pending'
        # as soon as the depended-upon row reaches status='completed'.
        initial_status = "cascade_waiting" if depends_on_write_id else "pending"

        row = {
            "company_id": company_id,
            "operation": "build_assembly",
            "payload": payload,
            "status": initial_status,
            "external_id": external_id,
            "external_source": external_source,
            "depends_on_write_id": depends_on_write_id,
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

        Cascade rows (status='cascade_waiting', depends_on_write_id set) are
        skipped here naturally because we filter status='pending'. The
        qb_meta.release_cascade_dependents trigger flips them to 'pending'
        as soon as the parent reaches 'completed', at which point claim_next
        picks them up on the next QBWC poll.
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

    def record_request_xml(self, queue_id: int, xml: str) -> None:
        """
        Capture the qbXML body the connector rendered for this row.
        Diagnostic only - overwrites last_request_xml on every claim/retry
        so we can debug schema rejections (0x80040400 parser errors)
        without round-tripping through QBWC just to see the request shape.
        Truncated to 8KB.
        """
        if not xml:
            return
        truncated = xml if len(xml) <= 8000 else xml[:8000] + "\n...[truncated]"
        try:
            self._table().update({"last_request_xml": truncated}).eq("id", queue_id).execute()
        except Exception as e:
            logger.warning("record_request_xml_failed", queue_id=queue_id, error=str(e))

    def mark_completed(
        self,
        queue_id: int,
        txn_id: str | None = None,
        is_pending: bool | None = None,
    ) -> None:
        """Mark a sent item as completed (QB confirmed success).

        `is_pending` is the `<IsPending>` value QB returned on a BuildAssembly
        response — True means QB recorded the build as pending because one or
        more components were short. Callers (e.g. MakerHub) can surface this
        in their UI to prompt the operator to finalize the build later.
        """
        update: dict[str, Any] = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "qb_txn_id": txn_id,
        }
        if is_pending is not None:
            update["is_pending"] = is_pending
        self._table().update(update).eq("id", queue_id).execute()
        logger.info(
            "write_completed",
            queue_id=queue_id,
            txn_id=txn_id,
            is_pending=is_pending,
        )
        _notify_makerhub(
            queue_id=queue_id,
            status="completed",
            qb_txn_id=txn_id,
            is_pending=is_pending,
            error_message=None,
        )

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
            _notify_makerhub(
                queue_id=queue_id,
                status="failed",
                qb_txn_id=None,
                is_pending=None,
                error_message=error,
            )
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
                mark_pending_if_required=bool(
                    payload.get("mark_pending_if_required", False)
                ),
                inventory_site_name=payload.get("inventory_site_name"),
                inventory_site_list_id=payload.get("inventory_site_list_id"),
                lot_number=payload.get("lot_number"),
                request_id=request_id,
            )

        if operation == "delete_build_assembly":
            txn_id = payload.get("txn_id") or payload.get("qb_txn_id")
            if not txn_id:
                logger.warning(
                    "delete_build_assembly_missing_txn_id",
                    queue_id=queue_item.get("id"),
                )
                return None
            return build_build_assembly_del(txn_id=txn_id, request_id=request_id)

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
