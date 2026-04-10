"""
Sync coordinator — builds the task queue and drives the
sendRequestXML / receiveResponseXML cycle for one QBWC session.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.qbxml.builders import build_query_for_entity
from src.qbxml.entities import get_entities_for_company, get_entity
from src.qbxml.parsers import parse_qbxml_response
from src.soap.session import SyncSession, SyncTask
from src.supabase.upsert import SupabaseUpserter
from src.sync.state import SyncStateManager
from src.utils.config import get_settings, get_company_config
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SyncCoordinator:
    """Drives sync for one QBWC session."""

    def __init__(
        self,
        state_manager: SyncStateManager,
        upserter: SupabaseUpserter,
    ) -> None:
        self._state = state_manager
        self._upserter = upserter
        self._settings = get_settings()
        self._company_cfg = get_company_config()

    def build_task_queue(self, session: SyncSession) -> None:
        """
        Populate session.task_queue with entities to sync, in priority order.
        Synchronous — state reads are fast Supabase selects.
        """
        company_id = session.company_id
        enabled = self._company_cfg.enabled_entities(company_id)
        entity_defs = get_entities_for_company(enabled)

        tasks: list[SyncTask] = []
        for edef in entity_defs:
            from_date = self._state.get_from_date(
                company_id,
                edef.name,
                self._settings.sync_lookback_minutes,
            )
            tasks.append(
                SyncTask(
                    entity_type=edef.name,
                    query_name=edef.query_rq,
                    is_incremental=(from_date is not None),
                    from_date=from_date,
                )
            )

        session.task_queue = tasks
        session.current_task_index = 0

        full_count = sum(1 for t in tasks if not t.is_incremental)
        logger.info(
            "task_queue_built",
            company=company_id,
            total=len(tasks),
            full_sync=full_count,
            incremental=len(tasks) - full_count,
        )

    def get_next_request(self, session: SyncSession) -> str:
        """
        Returns the next qbXML request string.
        Called by the SOAP handler on each sendRequestXML call.
        Returns "" when all tasks are done (signals QBWC to close).
        """
        # Skip tasks already marked done
        while session.current_task and session.current_task.is_done:
            session.advance_task()

        task = session.current_task
        if task is None:
            return ""

        company_cfg = self._company_cfg.get(session.company_id)
        max_returned = company_cfg.get("max_returned", self._settings.qbxml_max_returned)

        if task.started_at is None:
            task.started_at = datetime.now(timezone.utc).isoformat()
            self._state.mark_running(session.company_id, task.entity_type)
            logger.info(
                "entity_start",
                company=session.company_id,
                entity=task.entity_type,
                incremental=task.is_incremental,
                from_date=task.from_date,
            )

        # Check if this entity supports iterators
        try:
            edef = get_entity(task.entity_type)
            use_iterator = edef.supports_iterator
        except KeyError:
            use_iterator = False

        # Build request
        if task.iterator_id is not None and use_iterator:
            # Continue an in-progress iterator
            xml = build_query_for_entity(
                entity_name=task.entity_type,
                query_rq=task.query_name,
                request_id=str(session.current_task_index + 1),
                max_returned=max_returned,
                iterator_continue=True,
                iterator_id=task.iterator_id,
            )
        else:
            # Start fresh (with optional date filter)
            xml = build_query_for_entity(
                entity_name=task.entity_type,
                query_rq=task.query_name,
                request_id=str(session.current_task_index + 1),
                from_modified_date=task.from_date,
                max_returned=max_returned,
                iterator_start=use_iterator,
            )

        logger.debug(
            "request_built",
            entity=task.entity_type,
            iterator_id=task.iterator_id,
            iterator_remaining=task.iterator_remaining,
        )
        return xml

    def handle_response(self, session: SyncSession, response_xml: str) -> int:
        """
        Parses response, upserts to company schema, updates state.
        Returns progress percentage (0–100).
        Called by the SOAP handler on each receiveResponseXML call.
        """
        task = session.current_task
        if task is None:
            return 100

        pg_schema = self._company_cfg.pg_schema(session.company_id)

        # Parse
        parsed = parse_qbxml_response(response_xml, task.entity_type)

        # Status code 1 = "no matching object found" — not an error, just empty
        if parsed.status_code == 1:
            logger.info(
                "no_records_found",
                company=session.company_id,
                entity=task.entity_type,
                message=parsed.status_message,
            )
            task.completed_at = datetime.now(timezone.utc).isoformat()
            self._state.mark_done(
                company_id=session.company_id,
                entity_type=task.entity_type,
                records_synced=0,
                is_full_sync=not task.is_incremental,
            )
            session.advance_task()
            return session.progress_pct

        if not parsed.is_success:
            msg = f"QB error {parsed.status_code}: {parsed.status_message}"
            logger.error(
                "qb_error",
                company=session.company_id,
                entity=task.entity_type,
                code=parsed.status_code,
                message=parsed.status_message,
            )
            task.error = msg
            session.errors.append(f"{task.entity_type}: {msg}")
            self._state.mark_error(session.company_id, task.entity_type, msg)
            # Skip entity
            task.completed_at = datetime.now(timezone.utc).isoformat()
            session.advance_task()
            return session.progress_pct

        # Upsert records into company's Postgres schema
        if parsed.records:
            try:
                upserted = self._upserter.upsert(pg_schema, task.entity_type, parsed.records)
                task.records_processed += upserted
                session.total_records_synced += upserted
            except Exception as e:
                logger.error(
                    "upsert_error",
                    company=session.company_id,
                    schema=pg_schema,
                    entity=task.entity_type,
                    error=str(e),
                )
                session.errors.append(f"{task.entity_type} upsert: {e}")

        # Upsert BOM lines for assembly items
        if parsed.bom_lines:
            try:
                self._upserter.upsert_bom_lines(pg_schema, parsed.bom_lines)
                logger.info(
                    "bom_lines_upserted",
                    company=session.company_id,
                    schema=pg_schema,
                    count=len(parsed.bom_lines),
                )
            except Exception as e:
                logger.error(
                    "bom_upsert_error",
                    company=session.company_id,
                    schema=pg_schema,
                    error=str(e),
                )
                session.errors.append(f"assembly_bom_lines upsert: {e}")

        # Update iterator state
        if parsed.has_more:
            task.iterator_id = parsed.iterator_id
            task.iterator_remaining = parsed.iterator_remaining
            if task.initial_count == 0:
                task.initial_count = (
                    task.records_processed
                    + parsed.iterator_remaining
                    + len(parsed.records)
                )
        else:
            # Entity fully synced
            task.iterator_id = None
            task.iterator_remaining = 0
            task.completed_at = datetime.now(timezone.utc).isoformat()

            self._state.mark_done(
                company_id=session.company_id,
                entity_type=task.entity_type,
                records_synced=task.records_processed,
                is_full_sync=not task.is_incremental,
            )
            logger.info(
                "entity_done",
                company=session.company_id,
                entity=task.entity_type,
                records=task.records_processed,
                schema=pg_schema,
            )
            session.advance_task()

        return session.progress_pct
