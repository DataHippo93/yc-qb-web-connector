"""
QBWC SOAP service implemented with spyne.
Implements the full QBWebConnectorSvcSoap interface required by QB Web Connector.

QBWC calls these methods in order per sync cycle:
  1. authenticate(strUserName, strPassword)
        → ["ticket", ""] on success
        → ["ticket", "nvu"] if password wrong
        → ["", "none"] if nothing to do
  2. sendRequestXML(ticket, strHCPResponse, strCompanyFileName, ...)
        → qbXML string to execute, or "" when done
  3. receiveResponseXML(ticket, response, hresult, message)
        → int 0–99 = in progress, 100 = done
  4. closeConnection(ticket)
        → "OK"
  5. connectionError(ticket, hresult, message)
        → "done"  (terminate session)
  6. getLastError(ticket)
        → error string or ""
"""
from __future__ import annotations

import uuid
from typing import Any

from spyne import Application, rpc, ServiceBase, Unicode, Integer
from spyne.protocol.soap import Soap11
from spyne.server import WsgiApplication

from src.soap.session import get_session_store, SyncSession
from src.supabase.client import get_supabase_client
from src.supabase.upsert import SupabaseUpserter
from src.sync.coordinator import SyncCoordinator
from src.sync.state import SyncStateManager
from src.utils.config import get_settings, get_company_config, company_id_from_ticket_or_file
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Namespace required by QBWC
QBWC_NAMESPACE = "http://developer.intuit.com/"


def _make_coordinator() -> SyncCoordinator:
    client = get_supabase_client()
    state = SyncStateManager(client)
    upserter = SupabaseUpserter(client)
    return SyncCoordinator(state, upserter)


class QBWebConnectorSvc(ServiceBase):
    """
    Spyne service that implements the QBWC SOAP contract.
    One instance per request (spyne default).
    """

    @rpc(Unicode, Unicode, _returns=Unicode(max_occurs="unbounded"), _out_variable_name="authenticateResult")
    def authenticate(ctx, strUserName: str, strPassword: str):
        """
        Called by QBWC to authenticate before every sync cycle.
        Returns a 2-element array:
          [ticket, ""]       — authenticated, proceed
          [ticket, "none"]   — authenticated but nothing to sync right now
          [ticket, "nvu"]    — invalid credentials
          [ticket, "busy"]   — server busy, try later
        """
        settings = get_settings()

        # Validate credentials
        if strUserName != settings.qbwc_username or strPassword != settings.qbwc_password:
            logger.warning(
                "auth_failed",
                username=strUserName,
                remote_addr=ctx.transport.req_env.get("REMOTE_ADDR", "?"),
            )
            ticket = str(uuid.uuid4())
            return [ticket, "nvu"]

        # Determine which company this user/connector represents
        # QBWC doesn't pass company context at auth time — we use the username
        # Convention: one QBWC app per company, username encodes company
        company_config = get_company_config()
        company_id = _resolve_company_from_username(strUserName, company_config)

        if not company_id:
            logger.error("auth_no_company", username=strUserName)
            ticket = str(uuid.uuid4())
            return [ticket, "nvu"]

        # Create session and build task queue
        store = get_session_store()
        session = store.create(company_id=company_id)

        coordinator = _make_coordinator()
        coordinator.build_task_queue(session)

        if not session.task_queue:
            logger.info("nothing_to_sync", company=company_id)
            return [session.ticket, "none"]

        logger.info(
            "auth_success",
            company=company_id,
            ticket=session.ticket,
            tasks=len(session.task_queue),
            username=strUserName,
        )
        return [session.ticket, ""]

    @rpc(
        Unicode,  # ticket
        Unicode,  # strHCPResponse (QB company data, often empty)
        Unicode,  # strCompanyFileName
        Unicode,  # qbXMLCountry
        Integer,  # qbXMLMajorVers
        Integer,  # qbXMLMinorVers
        _returns=Unicode,
        _out_variable_name="sendRequestXMLResult",
    )
    def sendRequestXML(
        ctx,
        ticket: str,
        strHCPResponse: str,
        strCompanyFileName: str,
        qbXMLCountry: str,
        qbXMLMajorVers: int,
        qbXMLMinorVers: int,
    ):
        """
        QBWC calls this to get the next request to execute in QB.
        Return qbXML string, or "" to signal completion.
        """
        store = get_session_store()
        session = store.get(ticket)

        if session is None:
            logger.warning("unknown_ticket_send", ticket=ticket)
            return ""

        # Update session with QB version info if first call
        if session.qbxml_version == (13, 0):
            session.qbxml_version = (qbXMLMajorVers or 13, qbXMLMinorVers or 0)

        # If we have a company file path, try to refine company detection
        if strCompanyFileName and not session.company_id:
            company_config = get_company_config()
            cid = company_id_from_ticket_or_file(strCompanyFileName, company_config)
            if cid:
                session.company_id = cid

        coordinator = _make_coordinator()
        xml = coordinator.get_next_request(session)

        if not xml:
            session.status = "done"
            logger.info("session_requests_complete", ticket=ticket, company=session.company_id)

        return xml or ""

    @rpc(
        Unicode,  # ticket
        Unicode,  # response (qbXML response from QB)
        Unicode,  # hresult (COM HRESULT, "0x00000000" on success)
        Unicode,  # message (human-readable error if hresult != 0)
        _returns=Integer,
        _out_variable_name="receiveResponseXMLResult",
    )
    def receiveResponseXML(ctx, ticket: str, response: str, hresult: str, message: str):
        """
        QB has executed our request and returns the result.
        Return:
          0–99  = in progress (QBWC calls sendRequestXML again)
          100   = done (QBWC calls closeConnection)
          negative = error
        """
        store = get_session_store()
        session = store.get(ticket)

        if session is None:
            logger.warning("unknown_ticket_recv", ticket=ticket)
            return 100

        # Check for COM-level error from QB
        if hresult and hresult not in ("0x00000000", "0", ""):
            error_msg = f"QB COM error {hresult}: {message}"
            logger.error(
                "qb_com_error",
                ticket=ticket,
                hresult=hresult,
                message=message,
                company=session.company_id,
            )
            session.errors.append(error_msg)
            # Mark current task as errored and move on
            if session.current_task:
                from src.sync.state import SyncStateManager
                state_mgr = SyncStateManager(get_supabase_client())
                state_mgr.mark_error(session.company_id, session.current_task.entity_type, error_msg)
                session.current_task.completed_at = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                )
                session.advance_task()
            return session.progress_pct

        coordinator = _make_coordinator()
        pct = coordinator.handle_response(session, response)

        logger.debug(
            "response_received",
            ticket=ticket,
            progress=pct,
            company=session.company_id,
        )

        return pct

    @rpc(Unicode, _returns=Unicode, _out_variable_name="closeConnectionResult")
    def closeConnection(ctx, ticket: str):
        """QBWC calls this after receiveResponseXML returns 100."""
        store = get_session_store()
        session = store.get(ticket)

        if session:
            if session.errors:
                logger.warning(
                    "session_closed_with_errors",
                    ticket=ticket,
                    company=session.company_id,
                    error_count=len(session.errors),
                    errors=session.errors[:5],
                    records=session.total_records_synced,
                )
            else:
                logger.info(
                    "session_closed_ok",
                    ticket=ticket,
                    company=session.company_id,
                    records=session.total_records_synced,
                )
            store.delete(ticket)

        return "OK"

    @rpc(
        Unicode,  # ticket
        Unicode,  # hresult
        Unicode,  # message
        _returns=Unicode,
        _out_variable_name="connectionErrorResult",
    )
    def connectionError(ctx, ticket: str, hresult: str, message: str):
        """
        Called when QBWC encounters a connection error (QB not open, file locked, etc.).
        Should return "done" to terminate the session.
        """
        logger.error(
            "qbwc_connection_error",
            ticket=ticket,
            hresult=hresult,
            message=message,
        )
        store = get_session_store()
        session = store.get(ticket)
        if session:
            session.status = "error"
            if session.current_task:
                from src.sync.state import SyncStateManager
                state_mgr = SyncStateManager(get_supabase_client())
                state_mgr.mark_error(
                    session.company_id,
                    session.current_task.entity_type,
                    f"Connection error: {hresult} {message}",
                )
            store.delete(ticket)

        return "done"

    @rpc(Unicode, _returns=Unicode, _out_variable_name="getLastErrorResult")
    def getLastError(ctx, ticket: str):
        """Returns the last error for the session (called by QBWC on retries)."""
        store = get_session_store()
        session = store.get(ticket)
        if session and session.errors:
            return session.errors[-1]
        return ""

    @rpc(Unicode, _returns=Unicode, _out_variable_name="serverVersionResult")
    def serverVersion(ctx, strVersion: str):
        """Optional: returns server version info to QBWC."""
        return "1.0.0"

    @rpc(_returns=Unicode, _out_variable_name="clientVersionResult")
    def clientVersion(ctx):
        """Optional: QBWC passes its version; we accept any."""
        return ""


# ============================================================================
# Username → company_id resolution
# ============================================================================

def _resolve_company_from_username(username: str, company_config: Any) -> str | None:
    """
    Maps QBWC username to a company_id.

    Convention: create one QBWC app (.qwc file) per company.
    The username in each .qwc file distinguishes the company.

    Examples:
      YCConnector_NS  → natures_storehouse
      YCConnector_ADK → adk_fragrance
      YCConnector     → first company (single-company fallback)
    """
    lower = username.lower()
    if "ns" in lower or "natures" in lower or "storehouse" in lower:
        return "natures_storehouse"
    if "adk" in lower or "fragrance" in lower or "adirondack" in lower:
        return "adk_fragrance"

    # Fallback: if only one company, use it
    all_companies = company_config.all_company_ids()
    if len(all_companies) == 1:
        return all_companies[0]

    # If generic username and multiple companies — can't determine
    # The .qwc files should use distinct usernames to avoid this
    logger.warning(
        "cannot_resolve_company_from_username",
        username=username,
        hint="Use distinct usernames per .qwc file (e.g., YCConnector_NS, YCConnector_ADK)",
    )
    return None


# ============================================================================
# Build the WSGI app (used by FastAPI/uvicorn via mount)
# ============================================================================

def build_soap_wsgi_app() -> WsgiApplication:
    """Build and return the spyne WSGI application."""
    application = Application(
        services=[QBWebConnectorSvc],
        tns=QBWC_NAMESPACE,
        name="QBWebConnectorSvc",
        in_protocol=Soap11(validator="lxml"),
        out_protocol=Soap11(),
    )
    return WsgiApplication(application)
