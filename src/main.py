"""
FastAPI application — handles SOAP requests for QBWC and exposes REST health/status endpoints.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.soap.service import handle_soap_request, get_wsdl
from src.soap.session import get_session_store
from src.supabase.client import get_supabase_client
from src.supabase.upsert import MetaUpserter
from src.sync.backfill import BackfillJobManager
from src.sync.state import SyncStateManager
from src.sync.write_queue import WriteQueueManager
from src.utils.config import get_settings, get_company_config
from src.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


# ============================================================================
# Request models for write endpoints
# ============================================================================

class BackfillRequest(BaseModel):
    """Request body for POST /backfill/{company_id}/{entity_type}.

    Either modified-date window or txn-date window (transactions only).
    Use 'txn' when there's a calendar-time data gap (e.g. invoices missing
    for Feb-Mar 2024). Use 'modified' (default) when records exist but you
    suspect they were never synced or were synced incorrectly.
    """
    from_date: str = Field(
        ...,
        description="Lower bound of window (ISO datetime for 'modified', YYYY-MM-DD for 'txn')",
        examples=["2024-01-01", "2024-01-01T00:00:00"],
    )
    to_date: str = Field(
        ...,
        description="Upper bound of window (inclusive on QB side)",
        examples=["2024-04-30", "2024-04-30T23:59:59"],
    )
    filter_type: str = Field(
        "modified",
        description="'modified' (TimeModified, default) or 'txn' (TxnDate, transactions only)",
        pattern="^(modified|txn)$",
    )
    requested_by: str | None = Field(None, description="Operator/system that requested the backfill")
    reason: str | None = Field(None, description="Free-text explanation for the audit trail")


class BuildAssemblyRequest(BaseModel):
    assembly_list_id: str = Field(..., description="QB ListID of the assembly item")
    quantity: float = Field(..., gt=0, description="Number of assemblies to build")
    txn_date: str | None = Field(None, description="Build date (YYYY-MM-DD)")
    ref_number: str | None = Field(None, description="Reference/batch number")
    memo: str | None = Field(None, description="Memo/note")
    mark_pending_if_required: bool = Field(
        False,
        description="Allow build even when components are short — QB marks it as a pending "
        "build that can be finalized later. Maps to <MarkPendingIfRequired>true</MarkPendingIfRequired>.",
    )
    inventory_site_name: str | None = Field(None, description="Inventory site (Enterprise only)")
    external_id: str | None = Field(None, description="Caller's reference ID (e.g. MakerHub batch ID)")
    external_source: str | None = Field(None, description="Caller system name (e.g. 'makerhub')")
    depends_on_write_id: int | None = Field(
        None,
        description=(
            "When set, this build is part of a cascade and depends on another write_queue "
            "row's completion. The connector inserts the row as 'cascade_waiting'; the trigger "
            "release_cascade_dependents flips it to 'pending' as soon as the dependency "
            "reaches status='completed'. Used by MakerHub auto-cascading-build-assembly to "
            "enforce parent-build-before-child-build ordering."
        ),
    )


# ============================================================================
# Lifespan
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("starting_up", version="1.0.0", port=settings.port)

    # Register companies in qb_meta.companies
    client = get_supabase_client()
    meta = MetaUpserter(client)
    company_cfg = get_company_config()
    for cid in company_cfg.all_company_ids():
        meta.upsert_company(
            company_id=cid,
            pg_schema=company_cfg.pg_schema(cid),
            display_name=company_cfg.display_name(cid),
        )

    # Clean up expired sessions on startup (serverless-friendly)
    get_session_store().cleanup_expired()

    yield
    logger.info("shutting_down")


# ============================================================================
# App
# ============================================================================

def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="YC QuickBooks Web Connector",
        version="1.0.0",
        description="Syncs QB Desktop data to Supabase for Nature's Storehouse and ADK Fragrance Farm",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ---- SOAP endpoint at /qbwc/ ----
    # QBWC sends SOAP POST requests here
    @app.post("/qbwc/")
    @app.post("/qbwc")
    async def qbwc_soap(request: Request):
        body = await request.body()
        response_xml = handle_soap_request(body)
        return Response(
            content=response_xml,
            media_type="text/xml; charset=utf-8",
        )

    @app.get("/qbwc/")
    @app.get("/qbwc")
    async def qbwc_wsdl(request: Request):
        """Serve WSDL for QBWC discovery."""
        base_url = str(request.base_url).rstrip("/")
        wsdl_content = get_wsdl(base_url)
        return Response(
            content=wsdl_content,
            media_type="text/xml; charset=utf-8",
        )

    # ---- REST endpoints ----

    @app.get("/")
    async def root():
        return {"app": "YC QuickBooks Web Connector", "status": "ok", "version": "1.0.0"}

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/status")
    async def status():
        """Overall sync status for all companies, with staleness flags."""
        from datetime import datetime, timezone, timedelta

        client = get_supabase_client()
        state_mgr = SyncStateManager(client)
        company_cfg = get_company_config()

        STALE_HOURS = 6
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_HOURS)

        result = {}
        for cid in company_cfg.all_company_ids():
            states = state_mgr.get_all_states(cid)
            entities: dict[str, dict] = {}
            stale: list[str] = []
            errored: list[str] = []
            for s in states:
                lsa = s.get("last_synced_at")
                is_stale = False
                if lsa:
                    try:
                        is_stale = datetime.fromisoformat(lsa.replace("Z", "+00:00")) < cutoff
                    except (ValueError, TypeError):
                        is_stale = False
                else:
                    is_stale = True
                if is_stale:
                    stale.append(s["entity_type"])
                if s.get("status") == "error":
                    errored.append(s["entity_type"])
                entities[s["entity_type"]] = {
                    "status": s.get("status"),
                    "last_synced_at": lsa,
                    "last_full_sync_at": s.get("last_full_sync_at"),
                    "records_synced": s.get("records_synced"),
                    "error": s.get("error_message"),
                    "stale": is_stale,
                }
            result[cid] = {
                "display_name": company_cfg.display_name(cid),
                "pg_schema": company_cfg.pg_schema(cid),
                "stale_entities": stale,
                "errored_entities": errored,
                "stale_threshold_hours": STALE_HOURS,
                "entities": entities,
            }
        return result

    @app.get("/status/{company_id}")
    async def company_status(company_id: str):
        """Sync status for a single company."""
        company_cfg = get_company_config()
        try:
            company_cfg.get(company_id)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": f"Unknown company: {company_id}"})

        client = get_supabase_client()
        state_mgr = SyncStateManager(client)
        states = state_mgr.get_all_states(company_id)

        return {
            "company_id": company_id,
            "display_name": company_cfg.display_name(company_id),
            "pg_schema": company_cfg.pg_schema(company_id),
            "entities": states,
        }

    @app.post("/reset/{company_id}")
    async def reset_company(company_id: str):
        """Force a full re-sync of all entities for a company on next QBWC cycle."""
        company_cfg = get_company_config()
        try:
            company_cfg.get(company_id)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": f"Unknown company: {company_id}"})

        client = get_supabase_client()
        state_mgr = SyncStateManager(client)
        state_mgr.reset_company(company_id)

        return {"message": f"Reset {company_id} — next sync will be a full pull"}

    @app.post("/reset/{company_id}/{entity_type}")
    async def reset_entity(company_id: str, entity_type: str):
        """Force a full re-sync of a single entity for a company."""
        company_cfg = get_company_config()
        try:
            company_cfg.get(company_id)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": f"Unknown company: {company_id}"})

        client = get_supabase_client()
        state_mgr = SyncStateManager(client)
        state_mgr.reset_entity(company_id, entity_type)

        return {"message": f"Reset {company_id}/{entity_type}"}

    @app.get("/sessions")
    async def sessions():
        """Active QBWC sessions (for debugging)."""
        store = get_session_store()
        return {"active_sessions": store.active_count()}

    # ---- Backfill endpoints ----

    @app.post("/backfill/{company_id}/{entity_type}")
    async def enqueue_backfill(company_id: str, entity_type: str, body: BackfillRequest):
        """Enqueue a date-windowed re-sync for ONE entity for ONE company."""
        company_cfg = get_company_config()
        try:
            company_cfg.get(company_id)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": f"Unknown company: {company_id}"})

        client = get_supabase_client()
        bf = BackfillJobManager(client)
        try:
            row = bf.enqueue(
                company_id=company_id,
                entity_type=entity_type,
                from_date=body.from_date,
                to_date=body.to_date,
                filter_type=body.filter_type,
                requested_by=body.requested_by,
                reason=body.reason,
            )
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

        return {
            "status": "queued",
            "job_id": row.get("id"),
            "company_id": company_id,
            "entity_type": entity_type,
            "from_date": body.from_date,
            "to_date": body.to_date,
            "filter_type": body.filter_type,
            "message": (
                f"Backfill for {entity_type} [{body.from_date} -> {body.to_date}] "
                f"will run on the next QBWC sync cycle for {company_id}."
            ),
        }

    @app.get("/backfill/{company_id}")
    async def list_backfills(company_id: str, status: str | None = None):
        """List backfill jobs for a company (optionally filtered by status)."""
        company_cfg = get_company_config()
        try:
            company_cfg.get(company_id)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": f"Unknown company: {company_id}"})
        client = get_supabase_client()
        bf = BackfillJobManager(client)
        return {"company_id": company_id, "jobs": bf.list_for_company(company_id, status=status)}

    @app.get("/backfill/job/{job_id}")
    async def get_backfill(job_id: int):
        """Inspect a single backfill job."""
        client = get_supabase_client()
        bf = BackfillJobManager(client)
        job = bf.get_by_id(job_id)
        if not job:
            return JSONResponse(status_code=404, content={"error": "Backfill job not found"})
        return job

    # ---- Company-identity safeguard endpoints ----

    @app.get("/identity")
    async def list_identities():
        """Show what each company is configured to expect, what was last
        observed via CompanyQueryRq, and how many mismatches have been recorded."""
        client = get_supabase_client()
        rows = client.schema("qb_meta").table("companies").select("*").execute().data or []
        result = []
        for r in rows:
            mismatch_count = (
                client.schema("qb_meta").table("company_identity_log")
                .select("id", count="exact")
                .eq("company_id", r["company_id"])
                .eq("matched", False)
                .execute()
            ).count or 0
            result.append({
                "company_id": r["company_id"],
                "display_name": r.get("display_name"),
                "pg_schema": r.get("pg_schema"),
                "expected_company_name": r.get("expected_company_name"),
                "expected_company_file": r.get("expected_company_file"),
                "observed_company_name": r.get("observed_company_name"),
                "observed_company_file": r.get("observed_company_file"),
                "observed_at": r.get("observed_at"),
                "recent_mismatches": mismatch_count,
            })
        return {"companies": result}

    @app.get("/identity/log")
    async def identity_log(company_id: str | None = None, only_mismatches: bool = False, limit: int = 100):
        """Recent identity-check audit log entries (most recent first)."""
        client = get_supabase_client()
        q = (
            client.schema("qb_meta").table("company_identity_log")
            .select("*").order("checked_at", desc=True).limit(limit)
        )
        if company_id:
            q = q.eq("company_id", company_id)
        if only_mismatches:
            q = q.eq("matched", False)
        return {"entries": q.execute().data or []}

    @app.post("/identity/{company_id}/lock-in")
    async def lock_in_identity(company_id: str):
        """Promote the most recently observed company name into expected_company_name.

        Safe to call only when you have verified the right QB file was open
        when the last sync ran. After this, any future session that observes
        a DIFFERENT company_name will be aborted before any data flows.
        """
        company_cfg = get_company_config()
        try:
            company_cfg.get(company_id)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": f"Unknown company: {company_id}"})
        client = get_supabase_client()
        rows = (
            client.schema("qb_meta").table("companies")
            .select("observed_company_name, observed_company_file")
            .eq("company_id", company_id).execute()
        ).data
        if not rows or not rows[0].get("observed_company_name"):
            return JSONResponse(status_code=400, content={
                "error": "No observation yet -- let the connector run at least once before locking in",
            })
        observed_name = rows[0]["observed_company_name"]
        observed_file = rows[0].get("observed_company_file")
        client.schema("qb_meta").table("companies").update({
            "expected_company_name": observed_name,
            "expected_company_file": observed_file,
        }).eq("company_id", company_id).execute()
        logger.info(
            "identity_locked_in",
            company=company_id,
            expected_name=observed_name,
            expected_file=observed_file,
        )
        return {
            "company_id": company_id,
            "expected_company_name": observed_name,
            "expected_company_file": observed_file,
            "message": (
                "Locked in. Future sessions for this company_id will be aborted "
                "if QB reports a different CompanyName."
            ),
        }

    @app.post("/identity/{company_id}/clear")
    async def clear_identity_lock(company_id: str):
        """Remove expected_company_name (revert to observe-only mode)."""
        company_cfg = get_company_config()
        try:
            company_cfg.get(company_id)
        except KeyError:
            return JSONResponse(status_code=404, content={"error": f"Unknown company: {company_id}"})
        client = get_supabase_client()
        client.schema("qb_meta").table("companies").update({
            "expected_company_name": None,
            "expected_company_file": None,
        }).eq("company_id", company_id).execute()
        logger.warning("identity_lock_cleared", company=company_id)
        return {
            "company_id": company_id,
            "message": "Cleared. Connector is back in observe-only mode for this company.",
        }

    # ---- Write queue endpoints ----

    @app.post("/write/{company_id}/build-assembly")
    async def enqueue_build_assembly(company_id: str, body: BuildAssemblyRequest):
        """
        Enqueue a BuildAssembly operation to be sent to QuickBooks
        on the next QBWC sync cycle.
        """
        company_cfg = get_company_config()
        try:
            company_cfg.get(company_id)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": f"Unknown company: {company_id}"},
            )

        client = get_supabase_client()
        wq = WriteQueueManager(client)
        row = wq.enqueue_build_assembly(
            company_id=company_id,
            assembly_list_id=body.assembly_list_id,
            quantity=body.quantity,
            txn_date=body.txn_date,
            ref_number=body.ref_number,
            memo=body.memo,
            mark_pending_if_required=body.mark_pending_if_required,
            inventory_site_name=body.inventory_site_name,
            external_id=body.external_id,
            external_source=body.external_source,
            depends_on_write_id=body.depends_on_write_id,
        )

        return {
            "status": "queued",
            "queue_id": row.get("id"),
            "message": "BuildAssembly will be sent on next QBWC sync cycle",
        }

    @app.get("/write/{company_id}/status")
    async def write_queue_status(company_id: str):
        """Get pending write queue count for a company."""
        company_cfg = get_company_config()
        try:
            company_cfg.get(company_id)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": f"Unknown company: {company_id}"},
            )

        client = get_supabase_client()
        wq = WriteQueueManager(client)
        return {"company_id": company_id, "pending_writes": wq.get_pending_count(company_id)}

    @app.get("/write/queue/{queue_id}")
    async def write_queue_item(queue_id: int):
        """Get status of a specific write queue item."""
        client = get_supabase_client()
        wq = WriteQueueManager(client)
        item = wq.get_by_id(queue_id)
        if not item:
            return JSONResponse(status_code=404, content={"error": "Queue item not found"})
        return item

    return app


app = create_app()
