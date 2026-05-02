"""
Sync coordinator — builds the task queue and drives the
sendRequestXML / receiveResponseXML cycle for one QBWC session.
"""
from __future__ import annotations

from datetime import datetime, timezone

from lxml import etree

from src.qbxml.builders import build_company_query, build_query_for_entity
from src.qbxml.entities import get_entities_for_company, get_entity, ENTITY_BY_NAME
from src.qbxml.parsers import parse_company_query_response, parse_qbxml_response, parse_write_response
from src.soap.session import SyncSession, SyncTask
from src.supabase.upsert import SupabaseUpserter
from src.sync.backfill import BackfillJobManager
from src.sync.identity import CompanyIdentityChecker
from src.sync.state import SyncStateManager
from src.sync.write_queue import WriteQueueManager
from src.utils.config import get_settings, get_company_config
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _looks_like_write_response(response_xml: str) -> bool:
    """Return True if the qbXML response is shaped like an Add/Mod result.

    Used to route receiveResponseXML payloads. Read responses (anything ending
    in QueryRs, plus iterator continuations) must NOT be routed to the write
    handler even if session.active_write_id is set — otherwise a read response
    delivered while a write was in flight will be parsed as a write, fail,
    and the actual read data will be lost.
    """
    if not response_xml or not response_xml.strip():
        return False
    try:
        root = etree.fromstring(
            response_xml.encode("utf-8") if isinstance(response_xml, str) else response_xml
        )
    except etree.XMLSyntaxError:
        return False
    msgs_rs = root.find("QBXMLMsgsRs")
    if msgs_rs is None:
        return False
    for child in msgs_rs:
        tag = str(child.tag)
        if tag.endswith("AddRs") or tag.endswith("ModRs") or tag.endswith("DelRs"):
            return True
        if tag.endswith("QueryRs") or tag.endswith("ReportQueryRs"):
            return False
    return False


class SyncCoordinator:
    """Drives sync for one QBWC session."""

    def __init__(
        self,
        state_manager: SyncStateManager,
        upserter: SupabaseUpserter,
        write_queue: WriteQueueManager | None = None,
        backfill_manager: BackfillJobManager | None = None,
        identity_checker: CompanyIdentityChecker | None = None,
    ) -> None:
        self._state = state_manager
        self._upserter = upserter
        self._write_queue = write_queue
        self._backfill = backfill_manager
        self._identity = identity_checker
        self._settings = get_settings()
        self._company_cfg = get_company_config()

    def build_task_queue(self, session: SyncSession) -> None:
        """
        Populate session.task_queue with entities to sync, in priority order.

        Order: identity-check FIRST, then backfill jobs, then regular incremental
        syncs. The identity check sets session.identity_aborted on mismatch and
        all later tasks are skipped without dispatching qbXML.
        """
        company_id = session.company_id
        enabled = self._company_cfg.enabled_entities(company_id)
        entity_defs = get_entities_for_company(enabled)

        tasks: list[SyncTask] = []

        # 0) Company-identity verification — runs CompanyQueryRq before any data
        tasks.append(SyncTask(
            entity_type="__company_identity__",
            query_name="CompanyQueryRq",
            is_incremental=False,
            from_date=None,
            is_identity_check=True,
        ))

        # 1) Backfill tasks — claim any pending jobs
        backfill_tasks = self._build_backfill_tasks(company_id)
        tasks.extend(backfill_tasks)

        # 2) Regular per-entity sync tasks
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

        full_count = sum(
            1 for t in tasks if not t.is_incremental and not t.is_backfill and not t.is_identity_check
        )
        logger.info(
            "task_queue_built",
            company=company_id,
            total=len(tasks),
            backfill=len(backfill_tasks),
            full_sync=full_count,
            incremental=len(tasks) - full_count - len(backfill_tasks) - 1,
        )

    def _build_backfill_tasks(self, company_id: str) -> list[SyncTask]:
        """Claim pending backfill jobs and convert them to SyncTask front-runners."""
        if self._backfill is None:
            return []
        try:
            jobs = self._backfill.claim_pending_for_company(company_id)
        except Exception as e:
            logger.error("backfill_claim_failed", company=company_id, error=str(e))
            return []
        tasks: list[SyncTask] = []
        for job in jobs:
            entity_name = job["entity_type"]
            edef = ENTITY_BY_NAME.get(entity_name)
            if edef is None:
                logger.error("backfill_unknown_entity", job_id=job["id"], entity=entity_name)
                self._backfill.mark_error(job["id"], f"Unknown entity_type {entity_name!r}")
                continue
            filter_type = job.get("filter_type", "modified")
            from_d = job["from_date"]
            to_d = job["to_date"]
            if filter_type == "txn":
                if not edef.supports_txn_date_filter:
                    self._backfill.mark_error(
                        job["id"],
                        f"Entity {entity_name} does not support TxnDateRangeFilter — use filter_type='modified'",
                    )
                    continue
                tasks.append(SyncTask(
                    entity_type=entity_name, query_name=edef.query_rq,
                    is_incremental=True, from_date=None, to_date=None,
                    txn_from_date=from_d[:10] if isinstance(from_d, str) else from_d,
                    txn_to_date=to_d[:10] if isinstance(to_d, str) else to_d,
                    backfill_job_id=job["id"],
                ))
            else:
                tasks.append(SyncTask(
                    entity_type=entity_name, query_name=edef.query_rq,
                    is_incremental=True, from_date=from_d, to_date=to_d,
                    backfill_job_id=job["id"],
                ))
        return tasks

    def get_next_request(self, session: SyncSession) -> str:
        """
        Returns the next qbXML request string.
        Called by the SOAP handler on each sendRequestXML call.
        Returns "" when all tasks are done (signals QBWC to close).

        Write queue items are dispatched BEFORE read queries — they take
        priority so that builds are recorded promptly.
        """
        # If a write is in flight (active_write_id set) we've lost track of its
        # response — handle_response either never fired, or fired with a non-
        # write-shaped XML (in which case it's already been routed to the read
        # handler by the content-based router below). Mark the orphaned write
        # as failed so we don't dispatch a *read* while QBWC is expecting us
        # to consume the write's response next, and so we don't infinite-loop
        # claiming the same row.
        if session.active_write_id is not None and self._write_queue:
            orphan_id = session.active_write_id
            logger.warning(
                "orphaned_active_write",
                queue_id=orphan_id,
                ticket=session.ticket,
                company=session.company_id,
                current_task_index=session.current_task_index,
            )
            self._write_queue.mark_failed(
                orphan_id,
                "Write response not received before next sendRequestXML — "
                "orphaned active_write_id; will retry on next session",
            )
            session.active_write_id = None

        # Check write queue before read queries (unless we're mid-iteration)
        task = session.current_task
        mid_iteration = task and task.iterator_id is not None
        if (
            self._write_queue
            and not mid_iteration
            and session.active_write_id is None
        ):
            write_xml = self._dispatch_next_write(session)
            if write_xml:
                return write_xml

        # If a previous identity-check aborted us, skip every remaining task.
        if session.identity_aborted:
            while session.current_task and not session.current_task.is_done:
                session.current_task.completed_at = datetime.now(timezone.utc).isoformat()
                session.current_task.error = "identity_aborted"
                session.advance_task()
            return ""

        # Skip tasks already marked done
        while session.current_task and session.current_task.is_done:
            session.advance_task()

        task = session.current_task
        if task is None:
            return ""

        # Identity-check task uses the special CompanyQueryRq path
        if task.is_identity_check:
            if task.started_at is None:
                task.started_at = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "company_identity_check_start",
                    company=session.company_id,
                    ticket=session.ticket,
                )
            return build_company_query(request_id=str(session.current_task_index + 1))

        company_cfg = self._company_cfg.get(session.company_id)
        max_returned = company_cfg.get("max_returned", self._settings.qbxml_max_returned)

        if task.started_at is None:
            task.started_at = datetime.now(timezone.utc).isoformat()
            # Append-only history row so silent failures get an audit trail.
            task.log_id = self._state.log_run_started(
                company_id=session.company_id,
                entity_type=task.entity_type,
                is_full_sync=not task.is_incremental,
                ticket=session.ticket,
            )
            if task.is_backfill and self._backfill is not None:
                # Backfill tasks have their OWN lifecycle. Do NOT touch sync_state
                # — that would corrupt the entity's incremental cursor.
                self._backfill.mark_running(task.backfill_job_id)
                logger.info(
                    "backfill_start", company=session.company_id,
                    entity=task.entity_type, job_id=task.backfill_job_id,
                    from_modified=task.from_date, to_modified=task.to_date,
                    from_txn=task.txn_from_date, to_txn=task.txn_to_date,
                )
            else:
                self._state.mark_running(session.company_id, task.entity_type)
                logger.info(
                    "entity_start", company=session.company_id,
                    entity=task.entity_type, incremental=task.is_incremental,
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
            # Continue an in-progress iterator — must NOT include any filter
            xml = build_query_for_entity(
                entity_name=task.entity_type,
                query_rq=task.query_name,
                request_id=str(session.current_task_index + 1),
                max_returned=max_returned,
                iterator_continue=True,
                iterator_id=task.iterator_id,
            )
        else:
            xml = build_query_for_entity(
                entity_name=task.entity_type,
                query_rq=task.query_name,
                request_id=str(session.current_task_index + 1),
                from_modified_date=task.from_date,
                to_modified_date=task.to_date,
                from_txn_date=task.txn_from_date,
                to_txn_date=task.txn_to_date,
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
        # Route by response *shape*, not just by active_write_id. A read response
        # delivered while active_write_id happens to be set must NOT be routed to
        # the write handler — that would double-fail the write on a parser error
        # AND drop the actual read response on the floor.
        is_write_resp = _looks_like_write_response(response_xml)
        if is_write_resp and self._write_queue:
            if session.active_write_id is None:
                logger.warning(
                    "stray_write_response",
                    ticket=session.ticket,
                    company=session.company_id,
                )
                # Nothing to attribute it to — drop, but advance so we don't loop.
                return session.progress_pct
            return self._handle_write_response(session, response_xml)

        # Read-shaped response. If active_write_id is somehow set, this is the
        # symptom we saw on 2026-04-25: write was dispatched, response never
        # came back, then a read response arrived and the old code routed it to
        # the write handler. Clear the orphan and mark the write failed before
        # processing the read normally.
        if session.active_write_id is not None and self._write_queue:
            orphan_id = session.active_write_id
            logger.warning(
                "read_response_while_write_active",
                queue_id=orphan_id,
                ticket=session.ticket,
                company=session.company_id,
            )
            self._write_queue.mark_failed(
                orphan_id,
                "Read response received while write was in flight — "
                "write response was lost; will retry on next session",
            )
            session.active_write_id = None

        task = session.current_task
        if task is None:
            return 100

        # Identity-check response is parsed and evaluated separately. On a
        # failed check we set session.identity_aborted=True so all remaining
        # tasks are skipped without any data flowing into the schema.
        if task.is_identity_check:
            return self._handle_identity_response(session, response_xml)

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
                backfill_job_id=task.backfill_job_id,
            )
            task.completed_at = datetime.now(timezone.utc).isoformat()
            if task.is_backfill and self._backfill is not None:
                self._backfill.mark_done(task.backfill_job_id, records_synced=0)
            else:
                self._state.mark_done(
                    company_id=session.company_id,
                    entity_type=task.entity_type,
                    records_synced=0,
                    is_full_sync=not task.is_incremental,
                )
            # Stash the raw response so we can introspect WHY it was empty
            # (Multi-Site / lot-tracking permission, missing IncludeRetElement,
            # legitimately no rows, etc). Truncated to 4KB on the row.
            self._state.log_run_done(
                task.log_id,
                records_synced=0,
                debug_response_xml=response_xml,
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
                backfill_job_id=task.backfill_job_id,
            )
            task.error = msg
            session.errors.append(f"{task.entity_type}: {msg}")
            if task.is_backfill and self._backfill is not None:
                self._backfill.mark_error(task.backfill_job_id, msg)
            else:
                self._state.mark_error(session.company_id, task.entity_type, msg)
            self._state.log_run_error(task.log_id, msg)
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

            if task.is_backfill and self._backfill is not None:
                self._backfill.mark_done(task.backfill_job_id, records_synced=task.records_processed)
                logger.info(
                    "backfill_done", company=session.company_id,
                    entity=task.entity_type, job_id=task.backfill_job_id,
                    records=task.records_processed, schema=pg_schema,
                )
            else:
                self._state.mark_done(
                    company_id=session.company_id,
                    entity_type=task.entity_type,
                    records_synced=task.records_processed,
                    is_full_sync=not task.is_incremental,
                )
                logger.info(
                    "entity_done", company=session.company_id,
                    entity=task.entity_type, records=task.records_processed,
                    schema=pg_schema,
                )
            self._state.log_run_done(
                task.log_id,
                records_synced=task.records_processed,
                debug_response_xml=response_xml if task.records_processed == 0 else None,
            )
            session.advance_task()

        return session.progress_pct

    # ------------------------------------------------------------------
    # Company-identity verification
    # ------------------------------------------------------------------

    def _handle_identity_response(
        self, session: SyncSession, response_xml: str
    ) -> int:
        """Process the CompanyQueryRq response. If the QB-reported company name
        doesn't match the configured expected_company_name, set
        session.identity_aborted=True so all subsequent tasks are skipped."""
        task = session.current_task
        identity = parse_company_query_response(response_xml)

        # DB column wins over YAML default — set via /identity/{cid}/lock-in.
        expected_name = None
        expected_file = None
        if self._identity is not None:
            expected_name = self._identity.get_expected_name(session.company_id)
            expected_file = self._identity.get_expected_file(session.company_id)
        if expected_name is None:
            expected_name = self._company_cfg.expected_company_name(session.company_id)
        if expected_file is None:
            expected_file = self._company_cfg.expected_company_file(session.company_id)

        if self._identity is None:
            logger.warning(
                "company_identity_no_checker",
                company=session.company_id,
                observed_name=identity.company_name,
            )
            allowed, action = True, "observe_only"
        else:
            allowed, action = self._identity.evaluate(
                company_id=session.company_id,
                ticket=session.ticket,
                identity=identity,
                expected_company_name=expected_name,
                observed_file_path=session.last_known_company_file,
                expected_file_substr=expected_file,
            )

        task.completed_at = datetime.now(timezone.utc).isoformat()
        task.records_processed = 0

        if not allowed:
            session.identity_aborted = True
            session.status = "identity_failed"
            session.errors.append(
                f"Company identity mismatch: expected={expected_name!r} observed={identity.company_name!r} "
                f"file={session.last_known_company_file!r} action={action}"
            )
            logger.error(
                "session_aborted_identity_mismatch",
                company=session.company_id,
                ticket=session.ticket,
                expected_name=expected_name,
                observed_name=identity.company_name,
                action=action,
            )
            session.advance_task()
            return 100

        session.advance_task()
        return session.progress_pct

    # ------------------------------------------------------------------
    # Write queue integration
    # ------------------------------------------------------------------

    def _dispatch_next_write(self, session: SyncSession) -> str | None:
        """
        Claim and build the next pending write operation.
        Returns qbXML string or None if nothing to send.
        """
        item = self._write_queue.claim_next(session.company_id)
        if not item:
            return None

        request_id = f"W{item['id']}"
        xml = self._write_queue.build_request_xml(item, request_id=request_id)
        if xml is None:
            self._write_queue.mark_failed(item["id"], "Unknown operation type")
            return None

        # Track the active write so handle_response can route correctly
        session.active_write_id = item["id"]
        self._write_queue.mark_sent(item["id"], request_id)

        logger.info(
            "write_dispatched",
            company=session.company_id,
            queue_id=item["id"],
            operation=item["operation"],
            request_id=request_id,
        )
        return xml

    def _handle_write_response(
        self, session: SyncSession, response_xml: str
    ) -> int:
        """
        Process QB's response to a write (Add/Mod) operation.
        Returns progress percentage.
        """
        queue_id = session.active_write_id
        session.active_write_id = None  # Clear regardless of outcome

        parsed = parse_write_response(response_xml)

        if parsed.success:
            self._write_queue.mark_completed(
                queue_id,
                txn_id=parsed.txn_id,
                is_pending=parsed.is_pending,
            )
            logger.info(
                "write_succeeded",
                company=session.company_id,
                queue_id=queue_id,
                txn_id=parsed.txn_id,
                is_pending=parsed.is_pending,
            )
        else:
            error = f"QB error {parsed.status_code}: {parsed.status_message}"
            self._write_queue.mark_failed(queue_id, error)
            logger.error(
                "write_failed",
                company=session.company_id,
                queue_id=queue_id,
                error=error,
            )

        return session.progress_pct
