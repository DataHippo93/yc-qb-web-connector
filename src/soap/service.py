"""
QBWC SOAP service — lightweight lxml-based implementation (no spyne dependency).
Implements the QBWebConnectorSvcSoap interface required by QB Web Connector.

QBWC calls these methods in order per sync cycle:
  1. authenticate(strUserName, strPassword)
  2. sendRequestXML(ticket, strHCPResponse, strCompanyFileName, ...)
  3. receiveResponseXML(ticket, response, hresult, message)
  4. closeConnection(ticket)
  5. connectionError(ticket, hresult, message)
  6. getLastError(ticket)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from lxml import etree

from src.soap.session import get_session_store
from src.supabase.client import get_supabase_client
from src.supabase.upsert import SupabaseUpserter
from src.sync.coordinator import SyncCoordinator
from src.sync.state import SyncStateManager
from src.sync.write_queue import WriteQueueManager
from src.utils.config import get_settings, get_company_config, company_id_from_ticket_or_file
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Namespace constants
QBWC_NS = "http://developer.intuit.com/"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XSD_NS = "http://www.w3.org/2001/XMLSchema"

NSMAP = {
    "soap": SOAP_NS,
    "tns": QBWC_NS,
    "xsi": XSI_NS,
    "xsd": XSD_NS,
}


def _make_coordinator() -> SyncCoordinator:
    client = get_supabase_client()
    state = SyncStateManager(client)
    upserter = SupabaseUpserter(client)
    write_queue = WriteQueueManager(client)
    return SyncCoordinator(state, upserter, write_queue=write_queue)


# ============================================================================
# SOAP envelope helpers
# ============================================================================

def _soap_envelope(body_xml: etree._Element) -> bytes:
    """Wrap a body element in a SOAP envelope."""
    envelope = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap=NSMAP)
    body = etree.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    body.append(body_xml)
    return etree.tostring(envelope, xml_declaration=True, encoding="utf-8")


def _text_el(parent: etree._Element, tag: str, text: str) -> etree._Element:
    el = etree.SubElement(parent, tag)
    el.text = text
    return el


def _get_text(body: etree._Element, xpath: str) -> str:
    """Extract text from SOAP body using local-name matching."""
    els = body.xpath(xpath, namespaces={"tns": QBWC_NS})
    if els:
        return (els[0].text or "").strip()
    # Fallback: try without namespace
    for el in body.iter():
        local = etree.QName(el.tag).localname if isinstance(el.tag, str) else ""
        parts = xpath.rstrip("]").split("local-name()='")
        if len(parts) > 1:
            target = parts[-1].rstrip("'")
            if local == target:
                return (el.text or "").strip()
    return ""


def _parse_soap_request(raw_xml: bytes) -> tuple[str, etree._Element]:
    """Parse SOAP request, return (method_name, body_element)."""
    doc = etree.fromstring(raw_xml)
    body = doc.find(f"{{{SOAP_NS}}}Body")
    if body is None:
        raise ValueError("No SOAP Body found")
    # First child of Body is the method element
    method_el = body[0]
    method_name = etree.QName(method_el.tag).localname
    return method_name, method_el


def _child_text(parent: etree._Element, local_name: str) -> str:
    """Get text of a child element by local name."""
    for child in parent:
        if etree.QName(child.tag).localname == local_name:
            return (child.text or "").strip()
    return ""


def _child_int(parent: etree._Element, local_name: str) -> int:
    val = _child_text(parent, local_name)
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


# ============================================================================
# SOAP method handlers
# ============================================================================

def _handle_server_version(method_el: etree._Element) -> bytes:
    resp = etree.Element(f"{{{QBWC_NS}}}serverVersionResponse")
    _text_el(resp, f"{{{QBWC_NS}}}serverVersionResult", "1.0.0")
    return _soap_envelope(resp)


def _handle_client_version(method_el: etree._Element) -> bytes:
    resp = etree.Element(f"{{{QBWC_NS}}}clientVersionResponse")
    _text_el(resp, f"{{{QBWC_NS}}}clientVersionResult", "")
    return _soap_envelope(resp)


def _handle_authenticate(method_el: etree._Element) -> bytes:
    str_user = _child_text(method_el, "strUserName")
    str_pass = _child_text(method_el, "strPassword")

    settings = get_settings()

    # Validate credentials — username may have a company suffix (e.g. YCConnector_ADK)
    base_user = settings.qbwc_username
    username_ok = (str_user == base_user or str_user.startswith(base_user + "_"))
    if not username_ok or str_pass != settings.qbwc_password:
        logger.warning("auth_failed", username=str_user)
        ticket = str(uuid.uuid4())
        return _auth_response([ticket, "nvu"])

    company_config = get_company_config()
    company_id = _resolve_company_from_username(str_user, company_config)

    if not company_id:
        logger.error("auth_no_company", username=str_user)
        ticket = str(uuid.uuid4())
        return _auth_response([ticket, "nvu"])

    store = get_session_store()
    session = store.create(company_id=company_id)

    coordinator = _make_coordinator()
    coordinator.build_task_queue(session)

    if not session.task_queue:
        logger.info("nothing_to_sync", company=company_id)
        return _auth_response([session.ticket, "none"])

    store.save(session)

    logger.info(
        "auth_success",
        company=company_id,
        ticket=session.ticket,
        tasks=len(session.task_queue),
        username=str_user,
    )
    return _auth_response([session.ticket, ""])


def _auth_response(values: list[str]) -> bytes:
    resp = etree.Element(f"{{{QBWC_NS}}}authenticateResponse")
    result = etree.SubElement(resp, f"{{{QBWC_NS}}}authenticateResult")
    for v in values:
        _text_el(result, f"{{{QBWC_NS}}}string", v)
    return _soap_envelope(resp)


def _handle_send_request_xml(method_el: etree._Element) -> bytes:
    ticket = _child_text(method_el, "ticket")
    company_file = _child_text(method_el, "strCompanyFileName")
    major = _child_int(method_el, "qbXMLMajorVers")
    minor = _child_int(method_el, "qbXMLMinorVers")

    store = get_session_store()
    session = store.get(ticket)

    if session is None:
        logger.warning("unknown_ticket_send", ticket=ticket)
        return _string_response("sendRequestXMLResponse", "sendRequestXMLResult", "")

    if session.qbxml_version == (13, 0):
        session.qbxml_version = (major or 13, minor or 0)

    if company_file and not session.company_id:
        company_config = get_company_config()
        cid = company_id_from_ticket_or_file(company_file, company_config)
        if cid:
            session.company_id = cid

    coordinator = _make_coordinator()
    xml = coordinator.get_next_request(session)

    if not xml:
        session.status = "done"
        logger.info("session_requests_complete", ticket=ticket, company=session.company_id)

    store.save(session)

    return _string_response("sendRequestXMLResponse", "sendRequestXMLResult", xml or "")


def _handle_receive_response_xml(method_el: etree._Element) -> bytes:
    ticket = _child_text(method_el, "ticket")
    response = _child_text(method_el, "response")
    hresult = _child_text(method_el, "hresult")
    message = _child_text(method_el, "message")

    store = get_session_store()
    session = store.get(ticket)

    if session is None:
        logger.warning("unknown_ticket_recv", ticket=ticket)
        return _int_response("receiveResponseXMLResponse", "receiveResponseXMLResult", 100)

    if hresult and hresult not in ("0x00000000", "0", ""):
        error_msg = f"QB COM error {hresult}: {message}"
        logger.error("qb_com_error", ticket=ticket, hresult=hresult, message=message, company=session.company_id)
        session.errors.append(error_msg)
        if session.current_task:
            state_mgr = SyncStateManager(get_supabase_client())
            state_mgr.mark_error(session.company_id, session.current_task.entity_type, error_msg)
            session.current_task.completed_at = datetime.now(timezone.utc).isoformat()
            session.advance_task()
        store.save(session)
        return _int_response("receiveResponseXMLResponse", "receiveResponseXMLResult", session.progress_pct)

    coordinator = _make_coordinator()
    pct = coordinator.handle_response(session, response)

    store.save(session)

    logger.debug("response_received", ticket=ticket, progress=pct, company=session.company_id)

    return _int_response("receiveResponseXMLResponse", "receiveResponseXMLResult", pct)


def _handle_close_connection(method_el: etree._Element) -> bytes:
    ticket = _child_text(method_el, "ticket")

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

    return _string_response("closeConnectionResponse", "closeConnectionResult", "OK")


def _handle_connection_error(method_el: etree._Element) -> bytes:
    ticket = _child_text(method_el, "ticket")
    hresult = _child_text(method_el, "hresult")
    message = _child_text(method_el, "message")

    logger.error("qbwc_connection_error", ticket=ticket, hresult=hresult, message=message)

    store = get_session_store()
    session = store.get(ticket)
    if session:
        session.status = "error"
        if session.current_task:
            state_mgr = SyncStateManager(get_supabase_client())
            state_mgr.mark_error(
                session.company_id,
                session.current_task.entity_type,
                f"Connection error: {hresult} {message}",
            )
        store.delete(ticket)

    return _string_response("connectionErrorResponse", "connectionErrorResult", "done")


def _handle_get_last_error(method_el: etree._Element) -> bytes:
    ticket = _child_text(method_el, "ticket")

    store = get_session_store()
    session = store.get(ticket)
    error = ""
    if session and session.errors:
        error = session.errors[-1]

    return _string_response("getLastErrorResponse", "getLastErrorResult", error)


# ============================================================================
# Response helpers
# ============================================================================

def _string_response(resp_name: str, result_name: str, value: str) -> bytes:
    resp = etree.Element(f"{{{QBWC_NS}}}{resp_name}")
    _text_el(resp, f"{{{QBWC_NS}}}{result_name}", value)
    return _soap_envelope(resp)


def _int_response(resp_name: str, result_name: str, value: int) -> bytes:
    resp = etree.Element(f"{{{QBWC_NS}}}{resp_name}")
    _text_el(resp, f"{{{QBWC_NS}}}{result_name}", str(value))
    return _soap_envelope(resp)


# ============================================================================
# Method dispatch
# ============================================================================

HANDLERS = {
    "serverVersion": _handle_server_version,
    "clientVersion": _handle_client_version,
    "authenticate": _handle_authenticate,
    "sendRequestXML": _handle_send_request_xml,
    "receiveResponseXML": _handle_receive_response_xml,
    "closeConnection": _handle_close_connection,
    "connectionError": _handle_connection_error,
    "getLastError": _handle_get_last_error,
}


def handle_soap_request(raw_xml: bytes) -> bytes:
    """Parse a SOAP request and dispatch to the appropriate handler."""
    try:
        method_name, method_el = _parse_soap_request(raw_xml)
        handler = HANDLERS.get(method_name)
        if handler is None:
            logger.warning("unknown_soap_method", method=method_name)
            return _soap_fault("Client", f"Unknown method: {method_name}")
        return handler(method_el)
    except Exception as e:
        logger.error("soap_handler_error", error=str(e))
        return _soap_fault("Server", str(e))


def _soap_fault(fault_code: str, fault_string: str) -> bytes:
    envelope = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap=NSMAP)
    body = etree.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    fault = etree.SubElement(body, f"{{{SOAP_NS}}}Fault")
    _text_el(fault, "faultcode", fault_code)
    _text_el(fault, "faultstring", fault_string)
    return etree.tostring(envelope, xml_declaration=True, encoding="utf-8")


# ============================================================================
# WSDL (static, served at /qbwc?wsdl)
# ============================================================================

WSDL = """<?xml version="1.0" encoding="utf-8"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             xmlns:tns="http://developer.intuit.com/"
             xmlns:s="http://www.w3.org/2001/XMLSchema"
             targetNamespace="http://developer.intuit.com/"
             name="QBWebConnectorSvc">

  <types>
    <s:schema targetNamespace="http://developer.intuit.com/">
      <s:element name="serverVersion">
        <s:complexType><s:sequence>
          <s:element name="strVersion" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="serverVersionResponse">
        <s:complexType><s:sequence>
          <s:element name="serverVersionResult" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="clientVersion">
        <s:complexType><s:sequence>
          <s:element name="strVersion" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="clientVersionResponse">
        <s:complexType><s:sequence>
          <s:element name="clientVersionResult" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="authenticate">
        <s:complexType><s:sequence>
          <s:element name="strUserName" type="s:string" minOccurs="0"/>
          <s:element name="strPassword" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="authenticateResponse">
        <s:complexType><s:sequence>
          <s:element name="authenticateResult" type="tns:ArrayOfString" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:complexType name="ArrayOfString">
        <s:sequence>
          <s:element name="string" type="s:string" minOccurs="0" maxOccurs="unbounded"/>
        </s:sequence>
      </s:complexType>
      <s:element name="sendRequestXML">
        <s:complexType><s:sequence>
          <s:element name="ticket" type="s:string" minOccurs="0"/>
          <s:element name="strHCPResponse" type="s:string" minOccurs="0"/>
          <s:element name="strCompanyFileName" type="s:string" minOccurs="0"/>
          <s:element name="qbXMLCountry" type="s:string" minOccurs="0"/>
          <s:element name="qbXMLMajorVers" type="s:int"/>
          <s:element name="qbXMLMinorVers" type="s:int"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="sendRequestXMLResponse">
        <s:complexType><s:sequence>
          <s:element name="sendRequestXMLResult" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="receiveResponseXML">
        <s:complexType><s:sequence>
          <s:element name="ticket" type="s:string" minOccurs="0"/>
          <s:element name="response" type="s:string" minOccurs="0"/>
          <s:element name="hresult" type="s:string" minOccurs="0"/>
          <s:element name="message" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="receiveResponseXMLResponse">
        <s:complexType><s:sequence>
          <s:element name="receiveResponseXMLResult" type="s:int"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="closeConnection">
        <s:complexType><s:sequence>
          <s:element name="ticket" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="closeConnectionResponse">
        <s:complexType><s:sequence>
          <s:element name="closeConnectionResult" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="connectionError">
        <s:complexType><s:sequence>
          <s:element name="ticket" type="s:string" minOccurs="0"/>
          <s:element name="hresult" type="s:string" minOccurs="0"/>
          <s:element name="message" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="connectionErrorResponse">
        <s:complexType><s:sequence>
          <s:element name="connectionErrorResult" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="getLastError">
        <s:complexType><s:sequence>
          <s:element name="ticket" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
      <s:element name="getLastErrorResponse">
        <s:complexType><s:sequence>
          <s:element name="getLastErrorResult" type="s:string" minOccurs="0"/>
        </s:sequence></s:complexType>
      </s:element>
    </s:schema>
  </types>

  <message name="serverVersionSoapIn"><part name="parameters" element="tns:serverVersion"/></message>
  <message name="serverVersionSoapOut"><part name="parameters" element="tns:serverVersionResponse"/></message>
  <message name="clientVersionSoapIn"><part name="parameters" element="tns:clientVersion"/></message>
  <message name="clientVersionSoapOut"><part name="parameters" element="tns:clientVersionResponse"/></message>
  <message name="authenticateSoapIn"><part name="parameters" element="tns:authenticate"/></message>
  <message name="authenticateSoapOut"><part name="parameters" element="tns:authenticateResponse"/></message>
  <message name="sendRequestXMLSoapIn"><part name="parameters" element="tns:sendRequestXML"/></message>
  <message name="sendRequestXMLSoapOut"><part name="parameters" element="tns:sendRequestXMLResponse"/></message>
  <message name="receiveResponseXMLSoapIn"><part name="parameters" element="tns:receiveResponseXML"/></message>
  <message name="receiveResponseXMLSoapOut"><part name="parameters" element="tns:receiveResponseXMLResponse"/></message>
  <message name="closeConnectionSoapIn"><part name="parameters" element="tns:closeConnection"/></message>
  <message name="closeConnectionSoapOut"><part name="parameters" element="tns:closeConnectionResponse"/></message>
  <message name="connectionErrorSoapIn"><part name="parameters" element="tns:connectionError"/></message>
  <message name="connectionErrorSoapOut"><part name="parameters" element="tns:connectionErrorResponse"/></message>
  <message name="getLastErrorSoapIn"><part name="parameters" element="tns:getLastError"/></message>
  <message name="getLastErrorSoapOut"><part name="parameters" element="tns:getLastErrorResponse"/></message>

  <portType name="QBWebConnectorSvcSoap">
    <operation name="serverVersion"><input message="tns:serverVersionSoapIn"/><output message="tns:serverVersionSoapOut"/></operation>
    <operation name="clientVersion"><input message="tns:clientVersionSoapIn"/><output message="tns:clientVersionSoapOut"/></operation>
    <operation name="authenticate"><input message="tns:authenticateSoapIn"/><output message="tns:authenticateSoapOut"/></operation>
    <operation name="sendRequestXML"><input message="tns:sendRequestXMLSoapIn"/><output message="tns:sendRequestXMLSoapOut"/></operation>
    <operation name="receiveResponseXML"><input message="tns:receiveResponseXMLSoapIn"/><output message="tns:receiveResponseXMLSoapOut"/></operation>
    <operation name="closeConnection"><input message="tns:closeConnectionSoapIn"/><output message="tns:closeConnectionSoapOut"/></operation>
    <operation name="connectionError"><input message="tns:connectionErrorSoapIn"/><output message="tns:connectionErrorSoapOut"/></operation>
    <operation name="getLastError"><input message="tns:getLastErrorSoapIn"/><output message="tns:getLastErrorSoapOut"/></operation>
  </portType>

  <binding name="QBWebConnectorSvcSoap" type="tns:QBWebConnectorSvcSoap">
    <soap:binding transport="http://schemas.xmlsoap.org/soap/http"/>
    <operation name="serverVersion"><soap:operation soapAction="http://developer.intuit.com/serverVersion" style="document"/><input><soap:body use="literal"/></input><output><soap:body use="literal"/></output></operation>
    <operation name="clientVersion"><soap:operation soapAction="http://developer.intuit.com/clientVersion" style="document"/><input><soap:body use="literal"/></input><output><soap:body use="literal"/></output></operation>
    <operation name="authenticate"><soap:operation soapAction="http://developer.intuit.com/authenticate" style="document"/><input><soap:body use="literal"/></input><output><soap:body use="literal"/></output></operation>
    <operation name="sendRequestXML"><soap:operation soapAction="http://developer.intuit.com/sendRequestXML" style="document"/><input><soap:body use="literal"/></input><output><soap:body use="literal"/></output></operation>
    <operation name="receiveResponseXML"><soap:operation soapAction="http://developer.intuit.com/receiveResponseXML" style="document"/><input><soap:body use="literal"/></input><output><soap:body use="literal"/></output></operation>
    <operation name="closeConnection"><soap:operation soapAction="http://developer.intuit.com/closeConnection" style="document"/><input><soap:body use="literal"/></input><output><soap:body use="literal"/></output></operation>
    <operation name="connectionError"><soap:operation soapAction="http://developer.intuit.com/connectionError" style="document"/><input><soap:body use="literal"/></input><output><soap:body use="literal"/></output></operation>
    <operation name="getLastError"><soap:operation soapAction="http://developer.intuit.com/getLastError" style="document"/><input><soap:body use="literal"/></input><output><soap:body use="literal"/></output></operation>
  </binding>

  <service name="QBWebConnectorSvc">
    <port name="QBWebConnectorSvcSoap" binding="tns:QBWebConnectorSvcSoap">
      <soap:address location="REPLACE_WITH_URL"/>
    </port>
  </service>
</definitions>"""


def get_wsdl(base_url: str) -> str:
    """Return WSDL with the actual service URL."""
    return WSDL.replace("REPLACE_WITH_URL", f"{base_url.rstrip('/')}/qbwc/")


# ============================================================================
# Username → company_id resolution
# ============================================================================

def _resolve_company_from_username(username: str, company_config: Any) -> str | None:
    """
    Maps QBWC username to a company_id.
    Convention: one QBWC app (.qwc file) per company with distinct usernames.
    """
    lower = username.lower()
    if "ns" in lower or "natures" in lower or "storehouse" in lower:
        return "natures_storehouse"
    if "adk" in lower or "fragrance" in lower or "adirondack" in lower:
        return "adk_fragrance"
    if "ycw" in lower or "yc_works" in lower or "ycworks" in lower:
        return "yc_works"
    if "mm" in lower or "maine_and_maine" in lower or "maine&maine" in lower:
        return "maine_and_maine"
    if "ycc" in lower or "yc_consulting" in lower or "yconsult" in lower:
        return "yc_consulting"

    all_companies = company_config.all_company_ids()
    if len(all_companies) == 1:
        return all_companies[0]

    logger.warning(
        "cannot_resolve_company_from_username",
        username=username,
        hint="Use distinct usernames per .qwc file (e.g., YCConnector_NS, YCConnector_ADK)",
    )
    return None
