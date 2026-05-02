"""Tests for delete_build_assembly: builder, parser, and write_queue dispatch."""
from lxml import etree

from src.qbxml.builders import build_txn_del, build_build_assembly_del
from src.qbxml.parsers import parse_write_response


class TestBuildAssemblyDelBuilder:
    def test_emits_txn_del_envelope_with_correct_type(self):
        xml = build_build_assembly_del("11BBB2-1777688615")
        root = etree.fromstring(xml.encode("utf-8"))
        rq = root.find(".//TxnDelRq")
        assert rq is not None, "TxnDelRq element missing"
        assert rq.find("TxnDelType").text == "BuildAssembly"
        assert rq.find("TxnID").text == "11BBB2-1777688615"

    def test_element_order_matches_qbxml_schema(self):
        """qbXML 13.0 schema requires TxnDelType before TxnID."""
        xml = build_build_assembly_del("X")
        root = etree.fromstring(xml.encode("utf-8"))
        rq = root.find(".//TxnDelRq")
        children = list(rq)
        assert children[0].tag == "TxnDelType"
        assert children[1].tag == "TxnID"

    def test_request_id_propagates(self):
        xml = build_build_assembly_del("X", request_id="42")
        root = etree.fromstring(xml.encode("utf-8"))
        rq = root.find(".//TxnDelRq")
        assert rq.get("requestID") == "42"

    def test_generic_txn_del_accepts_other_types(self):
        """build_txn_del should accept Bill, Check, etc., not just BuildAssembly."""
        xml = build_txn_del("Bill", "BILL-123")
        root = etree.fromstring(xml.encode("utf-8"))
        assert root.find(".//TxnDelType").text == "Bill"


class TestBuildAssemblyDelResponseParsing:
    def test_parses_successful_delete_response(self):
        # qbXML response shape for a successful BuildAssembly delete.
        # Note: TxnDelRs has TxnID/TxnDelType/TimeDeleted as DIRECT children
        # (no *Ret wrapper), unlike Add/Mod responses.
        xml = b"""<?xml version="1.0" ?>
        <QBXML>
          <QBXMLMsgsRs>
            <TxnDelRs requestID="1" statusCode="0" statusMessage="Status OK">
              <TxnDelType>BuildAssembly</TxnDelType>
              <TxnID>11BBB2-1777688615</TxnID>
              <TimeDeleted>2026-05-02T20:14:32-04:00</TimeDeleted>
            </TxnDelRs>
          </QBXMLMsgsRs>
        </QBXML>"""
        result = parse_write_response(xml)
        assert result.success is True
        assert result.status_code == 0
        assert result.txn_id == "11BBB2-1777688615"

    def test_parses_failed_delete_response(self):
        # QB returns statusCode != 0 when the delete is rejected (e.g. txn
        # is referenced by a downstream transaction).
        xml = b"""<?xml version="1.0" ?>
        <QBXML>
          <QBXMLMsgsRs>
            <TxnDelRs requestID="1" statusCode="3120" statusMessage="Object specified in the request cannot be found.">
            </TxnDelRs>
          </QBXMLMsgsRs>
        </QBXML>"""
        result = parse_write_response(xml)
        assert result.success is False
        assert result.status_code == 3120
        assert "cannot be found" in result.status_message.lower()

    def test_existing_build_assembly_add_response_still_parses(self):
        # Regression: parser must still handle the original Add shape
        # after the DelRs branch was added.
        xml = b"""<?xml version="1.0" ?>
        <QBXML>
          <QBXMLMsgsRs>
            <BuildAssemblyAddRs requestID="1" statusCode="0" statusMessage="Status OK">
              <BuildAssemblyRet>
                <TxnID>11BA7F-1777642927</TxnID>
                <RefNumber>0501-VYQQ-1</RefNumber>
                <IsPending>false</IsPending>
              </BuildAssemblyRet>
            </BuildAssemblyAddRs>
          </QBXMLMsgsRs>
        </QBXML>"""
        result = parse_write_response(xml)
        assert result.success is True
        assert result.txn_id == "11BA7F-1777642927"
        assert result.is_pending is False
