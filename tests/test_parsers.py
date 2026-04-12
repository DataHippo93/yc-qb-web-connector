"""Tests for qbXML parsers."""
from __future__ import annotations

import pytest
from src.qbxml.parsers import parse_qbxml_response


CUSTOMER_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="13.0"?>
<QBXML>
  <QBXMLMsgsRs>
    <CustomerQueryRs requestID="1" statusCode="0" statusMessage="Status OK" iteratorRemainingCount="0">
      <CustomerRet>
        <ListID>80000001-1234567890</ListID>
        <TimeCreated>2023-01-15T10:00:00</TimeCreated>
        <TimeModified>2024-03-01T14:30:00</TimeModified>
        <EditSequence>1234567890</EditSequence>
        <Name>Acme Corp</Name>
        <FullName>Acme Corp</FullName>
        <IsActive>true</IsActive>
        <CompanyName>Acme Corporation</CompanyName>
        <Email>billing@acme.com</Email>
        <Phone>555-1234</Phone>
        <OpenBalance>1500.00</OpenBalance>
        <TotalBalance>1500.00</TotalBalance>
        <BillAddress>
          <Addr1>123 Main St</Addr1>
          <City>Canton</City>
          <State>NY</State>
          <PostalCode>13617</PostalCode>
        </BillAddress>
      </CustomerRet>
      <CustomerRet>
        <ListID>80000002-1234567890</ListID>
        <TimeCreated>2023-06-01T09:00:00</TimeCreated>
        <TimeModified>2024-03-15T11:00:00</TimeModified>
        <EditSequence>9876543210</EditSequence>
        <Name>Jane Smith</Name>
        <FullName>Jane Smith</FullName>
        <IsActive>true</IsActive>
        <FirstName>Jane</FirstName>
        <LastName>Smith</LastName>
        <Email>jane@example.com</Email>
        <Phone>555-5678</Phone>
        <OpenBalance>0.00</OpenBalance>
        <TotalBalance>250.00</TotalBalance>
      </CustomerRet>
    </CustomerQueryRs>
  </QBXMLMsgsRs>
</QBXML>'''

INVOICE_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="13.0"?>
<QBXML>
  <QBXMLMsgsRs>
    <InvoiceQueryRs requestID="1" statusCode="0" statusMessage="Status OK" iteratorRemainingCount="0">
      <InvoiceRet>
        <TxnID>1234-1234567890</TxnID>
        <TimeCreated>2024-01-10T09:00:00</TimeCreated>
        <TimeModified>2024-01-15T10:00:00</TimeModified>
        <EditSequence>1111111111</EditSequence>
        <TxnDate>2024-01-10</TxnDate>
        <RefNumber>INV-001</RefNumber>
        <CustomerRef>
          <ListID>80000001-1234567890</ListID>
          <FullName>Acme Corp</FullName>
        </CustomerRef>
        <DueDate>2024-02-10</DueDate>
        <Subtotal>500.00</Subtotal>
        <SalesTaxTotal>44.00</SalesTaxTotal>
        <BalanceRemaining>544.00</BalanceRemaining>
        <IsPaid>false</IsPaid>
        <InvoiceLineRet>
          <Desc>Widget A</Desc>
          <Quantity>10</Quantity>
          <Rate>50.00</Rate>
          <Amount>500.00</Amount>
        </InvoiceLineRet>
      </InvoiceRet>
    </InvoiceQueryRs>
  </QBXMLMsgsRs>
</QBXML>'''

ITERATOR_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="13.0"?>
<QBXML>
  <QBXMLMsgsRs>
    <CustomerQueryRs requestID="1" statusCode="0" statusMessage="Status OK"
        iteratorID="{ABC123}" iteratorRemainingCount="150">
      <CustomerRet>
        <ListID>80000003-0000000001</ListID>
        <Name>Batch Customer</Name>
        <FullName>Batch Customer</FullName>
        <IsActive>true</IsActive>
        <TimeCreated>2024-01-01T00:00:00</TimeCreated>
        <TimeModified>2024-01-01T00:00:00</TimeModified>
      </CustomerRet>
    </CustomerQueryRs>
  </QBXMLMsgsRs>
</QBXML>'''

ERROR_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="13.0"?>
<QBXML>
  <QBXMLMsgsRs>
    <CustomerQueryRs requestID="1" statusCode="3120"
        statusMessage="The query request has not been submitted. Feature is not available in this version of QuickBooks.">
    </CustomerQueryRs>
  </QBXMLMsgsRs>
</QBXML>'''

INVENTORY_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="13.0"?>
<QBXML>
  <QBXMLMsgsRs>
    <ItemInventoryQueryRs requestID="1" statusCode="0" statusMessage="Status OK" iteratorRemainingCount="0">
      <ItemInventoryRet>
        <ListID>80000010-1234567890</ListID>
        <TimeCreated>2024-01-15T10:00:00</TimeCreated>
        <TimeModified>2024-03-01T14:30:00</TimeModified>
        <EditSequence>1234567890</EditSequence>
        <Name>Inventory Widget</Name>
        <FullName>Inventory Widget</FullName>
        <IsActive>true</IsActive>
        <QuantityOnHand>42</QuantityOnHand>
        <AverageCost>12.50</AverageCost>
      </ItemInventoryRet>
    </ItemInventoryQueryRs>
  </QBXMLMsgsRs>
</QBXML>'''


class TestCustomerParser:
    def test_basic_parse(self):
        result = parse_qbxml_response(CUSTOMER_RESPONSE, "customers")
        assert result.is_success
        assert result.status_code == 0
        assert len(result.records) == 2

    def test_customer_fields(self):
        result = parse_qbxml_response(CUSTOMER_RESPONSE, "customers")
        first = result.records[0]
        assert first["qb_list_id"] == "80000001-1234567890"
        assert first["name"] == "Acme Corp"
        assert first["company_name"] == "Acme Corporation"
        assert first["email"] == "billing@acme.com"
        assert first["open_balance"] == 1500.0
        assert first["is_active"] is True

    def test_bill_address(self):
        result = parse_qbxml_response(CUSTOMER_RESPONSE, "customers")
        addr = result.records[0]["bill_address"]
        assert addr is not None
        assert addr["addr1"] == "123 Main St"
        assert addr["city"] == "Canton"
        assert addr["state"] == "NY"
        assert addr["postal_code"] == "13617"

    def test_no_iterator_when_done(self):
        result = parse_qbxml_response(CUSTOMER_RESPONSE, "customers")
        assert result.iterator_id is None
        assert result.iterator_remaining == 0
        assert not result.has_more


class TestInvoiceParser:
    def test_invoice_with_lines(self):
        result = parse_qbxml_response(INVOICE_RESPONSE, "invoices")
        assert result.is_success
        assert len(result.records) == 1
        record = result.records[0]
        assert "header" in record
        assert "lines" in record

    def test_invoice_header_fields(self):
        result = parse_qbxml_response(INVOICE_RESPONSE, "invoices")
        header = result.records[0]["header"]
        assert header["qb_txn_id"] == "1234-1234567890"
        assert header["txn_number"] == "INV-001"
        assert header["txn_date"] == "2024-01-10"
        assert header["customer_name"] == "Acme Corp"
        assert header["customer_list_id"] == "80000001-1234567890"
        assert header["balance_remaining"] == 544.0
        assert header["is_paid"] is False

    def test_invoice_line_items(self):
        result = parse_qbxml_response(INVOICE_RESPONSE, "invoices")
        lines = result.records[0]["lines"]
        assert len(lines) == 1
        line = lines[0]
        assert line["description"] == "Widget A"
        assert line["quantity"] == 10.0
        assert line["unit_price"] == 50.0
        assert line["amount"] == 500.0


class TestIterator:
    def test_iterator_detected(self):
        result = parse_qbxml_response(ITERATOR_RESPONSE, "customers")
        assert result.is_success
        assert result.iterator_id == "{ABC123}"
        assert result.iterator_remaining == 150
        assert result.has_more
        assert len(result.records) == 1

    def test_iterator_progress(self):
        result = parse_qbxml_response(ITERATOR_RESPONSE, "customers")
        # When there are remaining records, has_more is True
        assert result.has_more


class TestInventoryItemParser:
    def test_inventory_item_parse(self):
        result = parse_qbxml_response(INVENTORY_RESPONSE, "inventory_items")
        assert result.is_success
        assert len(result.records) == 1
        item = result.records[0]
        assert item["qb_list_id"] == "80000010-1234567890"
        assert item["item_type"] == "Inventory"
        assert item["quantity_on_hand"] == 42.0
        assert item["avg_cost"] == 12.5


class TestErrorHandling:
    def test_error_status(self):
        result = parse_qbxml_response(ERROR_RESPONSE, "customers")
        assert not result.is_success
        assert result.status_code == 3120
        assert len(result.records) == 0

    def test_empty_response(self):
        result = parse_qbxml_response("", "customers")
        assert not result.is_success
        assert result.status_code == -1

    def test_malformed_xml(self):
        result = parse_qbxml_response("<broken>xml", "customers")
        assert not result.is_success
