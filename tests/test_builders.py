"""Tests for qbXML request builders."""
from __future__ import annotations

import pytest
from lxml import etree

from src.qbxml.builders import (
    build_customer_query,
    build_invoice_query,
    build_account_query,
    build_generic_query,
    build_query_for_entity,
)


def parse_xml(xml_string: str) -> etree._Element:
    """Parse XML, stripping the qbxml processing instruction."""
    lines = [l for l in xml_string.splitlines() if not l.startswith("<?")]
    return etree.fromstring("\n".join(lines).encode())


class TestCustomerQueryBuilder:
    def test_basic_query(self):
        xml = build_customer_query()
        root = parse_xml(xml)
        rq = root.find(".//CustomerQueryRq")
        assert rq is not None
        assert rq.get("requestID") == "1"

    def test_iterator_start(self):
        xml = build_customer_query(iterator_start=True)
        root = parse_xml(xml)
        rq = root.find(".//CustomerQueryRq")
        assert rq.get("iterator") == "Start"

    def test_iterator_continue(self):
        xml = build_customer_query(
            iterator_continue=True, iterator_id="{ABC-123}", max_returned=50
        )
        root = parse_xml(xml)
        rq = root.find(".//CustomerQueryRq")
        assert rq.get("iterator") == "Continue"
        assert rq.get("iteratorID") == "{ABC-123}"
        assert rq.find("MaxReturned").text == "50"

    def test_date_filter(self):
        xml = build_customer_query(from_modified_date="2024-01-01T00:00:00", iterator_start=True)
        root = parse_xml(xml)
        rq = root.find(".//CustomerQueryRq")
        date_filter = rq.find("ModifiedDateRangeFilter")
        assert date_filter is not None
        assert date_filter.find("FromModifiedDate").text == "2024-01-01T00:00:00"

    def test_no_date_filter_on_continue(self):
        """Date filter must not be included on Continue calls — QB rejects it."""
        xml = build_customer_query(
            from_modified_date="2024-01-01T00:00:00",
            iterator_continue=True,
            iterator_id="{XYZ}",
        )
        root = parse_xml(xml)
        rq = root.find(".//CustomerQueryRq")
        assert rq.find("ModifiedDateRangeFilter") is None

    def test_max_returned(self):
        xml = build_customer_query(max_returned=25)
        root = parse_xml(xml)
        rq = root.find(".//CustomerQueryRq")
        assert rq.find("MaxReturned").text == "25"


class TestInvoiceQueryBuilder:
    def test_includes_line_items(self):
        xml = build_invoice_query()
        root = parse_xml(xml)
        rq = root.find(".//InvoiceQueryRq")
        assert rq.find("IncludeLineItems") is not None
        assert rq.find("IncludeLineItems").text == "true"

    def test_includes_linked_txns(self):
        xml = build_invoice_query()
        root = parse_xml(xml)
        rq = root.find(".//InvoiceQueryRq")
        assert rq.find("IncludeLinkedTxns").text == "true"


class TestGenericQueryBuilder:
    def test_generic_falls_back(self):
        xml = build_generic_query("TimeTrackingQueryRq")
        root = parse_xml(xml)
        rq = root.find(".//TimeTrackingQueryRq")
        assert rq is not None

    def test_dispatcher_uses_specialized(self):
        xml = build_query_for_entity(
            entity_name="customers",
            query_rq="CustomerQueryRq",
            from_modified_date="2024-06-01T00:00:00",
            iterator_start=True,
        )
        root = parse_xml(xml)
        # Specialized builder includes IncludeRetElement fields
        rq = root.find(".//CustomerQueryRq")
        assert rq is not None
        include_fields = [el.text for el in rq.findall("IncludeRetElement")]
        assert "ListID" in include_fields
        assert "Email" in include_fields

    def test_dispatcher_fallback(self):
        xml = build_query_for_entity(
            entity_name="transfers",
            query_rq="TransferQueryRq",
            max_returned=200,
        )
        root = parse_xml(xml)
        rq = root.find(".//TransferQueryRq")
        assert rq is not None
        assert rq.find("MaxReturned").text == "200"

    def test_inventory_items_uses_inventory_query(self):
        xml = build_query_for_entity(
            entity_name="inventory_items",
            query_rq="ItemInventoryQueryRq",
            from_modified_date="2024-06-01T00:00:00",
            iterator_start=True,
        )
        root = parse_xml(xml)
        rq = root.find(".//ItemInventoryQueryRq")
        assert rq is not None
        assert rq.get("iterator") == "Start"
        assert rq.find("FromModifiedDate").text == "2024-06-01T00:00:00"

    def test_qbxml_header(self):
        xml = build_customer_query()
        assert '<?xml version="1.0"' in xml
        assert '<?qbxml version="13.0"?>' in xml
