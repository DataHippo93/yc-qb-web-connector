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
from src.sync.state import SyncStateManager
from src.sync.write_queue import WriteQueueManager
from src.utils.config import get_settings, get_company_config
from src.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


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
        """Overall sync status for all companies."""
        client = get_supabase_client()
        state_mgr = SyncStateManager(client)
        company_cfg = get_company_config()

        result = {}
        for cid in company_cfg.all_company_ids():
            states = state_mgr.get_all_states(cid)
            result[cid] = {
                "display_name": company_cfg.display_name(cid),
                "pg_schema": company_cfg.pg_schema(cid),
                "entities": {
                    s["entity_type"]: {
                        "status": s.get("status"),
                        "last_synced_at": s.get("last_synced_at"),
                        "records_synced": s.get("records_synced"),
                        "error": s.get("error_message"),
                    }
                    for s in states
                },
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

    # ---- Write queue endpoints ----

    class BuildAssemblyRequest(BaseModel):
        assembly_list_id: str = Field(..., description="QB ListID of the assembly item")
        quantity: float = Field(..., gt=0, description="Number of assemblies to build")
        txn_date: str | None = Field(None, description="Build date (YYYY-MM-DD)")
        ref_number: str | None = Field(None, description="Reference/batch number")
        memo: str | None = Field(None, description="Memo/note")
        inventory_site_name: str | None = Field(None, description="Inventory site (Enterprise only)")
        external_id: str | None = Field(None, description="Caller's reference ID (e.g. MakerHub batch ID)")
        external_source: str | None = Field(None, description="Caller system name (e.g. 'makerhub')")

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
            inventory_site_name=body.inventory_site_name,
            external_id=body.external_id,
            external_source=body.external_source,
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
