"""
Supabase upsert logic.

Data is isolated by Postgres schema per company:
  natures_storehouse.customers, natures_storehouse.invoices, etc.
  adk_fragrance.customers, adk_fragrance.invoices, etc.

No company_id column needed — schema isolation provides it.
Shared metadata (sync state) lives in qb_meta schema.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from supabase import Client

from src.supabase.client import META_SCHEMA
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Max records per upsert call
BATCH_SIZE = 500

# entity_type → (table_name, pk_column, has_lines, lines_table)
# table_name is unqualified — schema is provided by the caller
ENTITY_TABLE_MAP: dict[str, tuple[str, str, bool, str | None]] = {
    # List objects
    "accounts":          ("accounts",           "qb_list_id", False, None),
    "classes":           ("classes",            "qb_list_id", False, None),
    "customers":         ("customers",          "qb_list_id", False, None),
    "vendors":           ("vendors",            "qb_list_id", False, None),
    "employees":         ("employees",          "qb_list_id", False, None),
    "items":             ("items",              "qb_list_id", False, None),
    "sales_tax_codes":   ("sales_tax_codes",    "qb_list_id", False, None),
    "payment_methods":   ("payment_methods",    "qb_list_id", False, None),
    "ship_methods":      ("ship_methods",       "qb_list_id", False, None),
    "terms":             ("terms",              "qb_list_id", False, None),
    # Transactions with line items
    "invoices":          ("invoices",           "qb_txn_id",  True,  "invoice_lines"),
    "sales_receipts":    ("sales_receipts",     "qb_txn_id",  True,  "sales_receipt_lines"),
    "credit_memos":      ("credit_memos",       "qb_txn_id",  True,  "credit_memo_lines"),
    "bills":             ("bills",              "qb_txn_id",  True,  "bill_lines"),
    "purchase_orders":   ("purchase_orders",    "qb_txn_id",  True,  "purchase_order_lines"),
    "estimates":         ("estimates",          "qb_txn_id",  True,  "estimate_lines"),
    "sales_orders":      ("sales_orders",       "qb_txn_id",  True,  "sales_order_lines"),
    "checks":            ("checks",             "qb_txn_id",  True,  "check_lines"),
    "credit_card_charges":  ("credit_card_charges",  "qb_txn_id", True, "credit_card_charge_lines"),
    "credit_card_credits":  ("credit_card_credits",  "qb_txn_id", True, "credit_card_credit_lines"),
    "vendor_credits":    ("vendor_credits",     "qb_txn_id",  True,  "vendor_credit_lines"),
    "journal_entries":   ("journal_entries",    "qb_txn_id",  True,  "journal_entry_lines"),
    "deposits":          ("deposits",           "qb_txn_id",  True,  "deposit_lines"),
    "inventory_adjustments": ("inventory_adjustments", "qb_txn_id", True, "inventory_adjustment_lines"),
    # Transactions without lines
    "bill_payments":     ("bill_payments",      "qb_txn_id",  False, None),
    "receive_payments":  ("receive_payments",   "qb_txn_id",  False, None),
    "transfers":         ("transfers",          "qb_txn_id",  False, None),
    "time_tracking":     ("time_tracking",      "qb_txn_id",  False, None),
}


class SupabaseUpserter:
    """
    Upserts QB records into the company's isolated Postgres schema.
    No company_id column — the schema IS the company identifier.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    async def upsert(
        self,
        pg_schema: str,
        entity_type: str,
        records: list[dict | Any],
    ) -> int:
        """
        Upsert records into the given Postgres schema.

        Args:
            pg_schema: e.g. "natures_storehouse" or "adk_fragrance"
            entity_type: e.g. "invoices", "customers"
            records: parsed records from qbXML parser
                     - Simple entities: list[dict]
                     - Transactional with lines: list[{"header": dict, "lines": [dict]}]

        Returns:
            Count of header records upserted.
        """
        if not records:
            return 0

        mapping = ENTITY_TABLE_MAP.get(entity_type)
        if not mapping:
            logger.warning("no_table_mapping", entity=entity_type)
            return 0

        table_name, pk_col, has_lines_in_parser, lines_table = mapping
        now = datetime.now(timezone.utc).isoformat()

        # Detect whether records actually carry line items
        records_have_lines = (
            has_lines_in_parser
            and len(records) > 0
            and isinstance(records[0], dict)
            and "header" in records[0]
        )

        if records_have_lines:
            headers = [r["header"] for r in records]
            all_lines: list[dict] = []
            for r in records:
                all_lines.extend(r.get("lines", []))

            # Stamp sync time on headers
            for h in headers:
                h["synced_at"] = now

            headers_upserted = await self._upsert_batch(
                schema=pg_schema,
                table=table_name,
                records=headers,
                conflict_cols=[pk_col],
            )

            if all_lines and lines_table:
                await self._upsert_batch(
                    schema=pg_schema,
                    table=lines_table,
                    records=all_lines,
                    conflict_cols=["txn_id", "line_seq_no"],
                )

            return headers_upserted

        else:
            for r in records:
                r["synced_at"] = now

            return await self._upsert_batch(
                schema=pg_schema,
                table=table_name,
                records=records,
                conflict_cols=[pk_col],
            )

    async def _upsert_batch(
        self,
        schema: str,
        table: str,
        records: list[dict],
        conflict_cols: list[str],
    ) -> int:
        """
        Batch upsert into schema.table.
        Uses Supabase PostgREST schema switching.
        """
        if not records:
            return 0

        # Strip None values — don't overwrite existing data with NULL
        # unless you explicitly want to clear fields
        clean = [{k: v for k, v in r.items() if v is not None} for r in records]

        total = 0
        for i in range(0, len(clean), BATCH_SIZE):
            batch = clean[i : i + BATCH_SIZE]
            try:
                result = (
                    self._client.schema(schema)
                    .table(table)
                    .upsert(batch, on_conflict=",".join(conflict_cols))
                    .execute()
                )
                total += len(result.data) if result.data else len(batch)
                logger.debug(
                    "batch_upserted",
                    schema=schema,
                    table=table,
                    count=len(batch),
                )
            except Exception as e:
                logger.error(
                    "upsert_batch_failed",
                    schema=schema,
                    table=table,
                    size=len(batch),
                    error=str(e),
                )
                # One retry after a short pause
                await asyncio.sleep(2)
                try:
                    result = (
                        self._client.schema(schema)
                        .table(table)
                        .upsert(batch, on_conflict=",".join(conflict_cols))
                        .execute()
                    )
                    total += len(result.data) if result.data else len(batch)
                except Exception as e2:
                    logger.error(
                        "upsert_retry_failed",
                        schema=schema,
                        table=table,
                        error=str(e2),
                    )
                    raise

        return total


class MetaUpserter:
    """
    Writes to qb_meta schema (sync_state, company_registry).
    Always uses the META_SCHEMA constant.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    def upsert_company(self, company_id: str, pg_schema: str, display_name: str) -> None:
        """Register a company in qb_meta.companies."""
        self._client.schema(META_SCHEMA).table("companies").upsert(
            {
                "company_id": company_id,
                "pg_schema": pg_schema,
                "display_name": display_name,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="company_id",
        ).execute()
