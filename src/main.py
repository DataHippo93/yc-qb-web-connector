"""
FastAPI application — handles SOAP requests for QBWC and exposes REST health/status endpoints.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.soap.service import handle_soap_request, get_wsdl
from src.soap.session import get_session_store
from src.supabase.client import get_supabase_client
from src.supabase.upsert import MetaUpserter
from src.sync.state import SyncStateManager
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

    return app


app = create_app()
