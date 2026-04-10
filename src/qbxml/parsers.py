"""
qbXML response parsers.
Parses XML response strings from QB into Python dicts ready for Supabase upsert.
"""
from __future__ import annotations

import re
from typing import Any

from lxml import etree

from src.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Response Metadata
# ============================================================================

class ParsedResponse:
    """Result of parsing a qbXML response."""

    def __init__(
        self,
        entity_type: str,
        records: list[dict[str, Any]],
        iterator_id: str | None,
        iterator_remaining: int,
        status_code: int,
        status_message: str,
        request_id: str | None,
        bom_lines: list[dict[str, Any]] | None = None,
    ) -> None:
        self.entity_type = entity_type
        self.records = records
        self.iterator_id = iterator_id
        self.iterator_remaining = iterator_remaining
        self.status_code = status_code
        self.status_message = status_message
        self.request_id = request_id
        self.bom_lines = bom_lines or []

    @property
    def is_success(self) -> bool:
        return self.status_code == 0

    @property
    def has_more(self) -> bool:
        return self.iterator_remaining > 0 and self.iterator_id is not None

    def __repr__(self) -> str:
        return (
            f"ParsedResponse(entity={self.entity_type}, records={len(self.records)}, "
            f"status={self.status_code}, remaining={self.iterator_remaining})"
        )


# ============================================================================
# XML Helpers
# ============================================================================

def _text(element: etree._Element, path: str) -> str | None:
    """Get text content at xpath, or None."""
    el = element.find(path)
    return el.text if el is not None else None


def _bool(element: etree._Element, path: str) -> bool | None:
    t = _text(element, path)
    if t is None:
        return None
    return t.lower() == "true"


def _amount(element: etree._Element, path: str) -> float | None:
    t = _text(element, path)
    if t is None:
        return None
    try:
        return float(t)
    except (ValueError, TypeError):
        return None


def _ref(element: etree._Element, ref_path: str, name_field: str = "FullName") -> str | None:
    """Extract the FullName or ListID from a *Ref element."""
    ref = element.find(ref_path)
    if ref is None:
        return None
    return _text(ref, name_field) or _text(ref, "ListID")


def _address(element: etree._Element, path: str) -> dict | None:
    """Parse an address block to dict."""
    addr = element.find(path)
    if addr is None:
        return None
    return {
        "addr1": _text(addr, "Addr1"),
        "addr2": _text(addr, "Addr2"),
        "addr3": _text(addr, "Addr3"),
        "addr4": _text(addr, "Addr4"),
        "addr5": _text(addr, "Addr5"),
        "city": _text(addr, "City"),
        "state": _text(addr, "State"),
        "postal_code": _text(addr, "PostalCode"),
        "country": _text(addr, "Country"),
        "note": _text(addr, "Note"),
    }


# ============================================================================
# Entity-specific parsers
# ============================================================================

def parse_account(el: etree._Element) -> dict:
    return {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "full_name": _text(el, "FullName"),
        "is_active": _bool(el, "IsActive"),
        "parent_list_id": _ref(el, "ParentRef", "ListID"),
        "sublevel": _text(el, "Sublevel"),
        "account_type": _text(el, "AccountType"),
        "special_account_type": _text(el, "SpecialAccountType"),
        "account_number": _text(el, "AccountNumber"),
        "bank_number": _text(el, "BankNumber"),
        "description": _text(el, "Desc"),
        "balance": _amount(el, "Balance"),
        "total_balance": _amount(el, "TotalBalance"),
        "cash_flow_classification": _text(el, "CashFlowClassification"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_customer(el: etree._Element) -> dict:
    return {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "full_name": _text(el, "FullName"),
        "is_active": _bool(el, "IsActive"),
        "parent_list_id": _ref(el, "ParentRef", "ListID"),
        "sublevel": _text(el, "Sublevel"),
        "company_name": _text(el, "CompanyName"),
        "salutation": _text(el, "Salutation"),
        "first_name": _text(el, "FirstName"),
        "middle_name": _text(el, "MiddleName"),
        "last_name": _text(el, "LastName"),
        "suffix": _text(el, "Suffix"),
        "job_title": _text(el, "JobTitle"),
        "bill_address": _address(el, "BillAddress"),
        "ship_address": _address(el, "ShipAddress"),
        "phone": _text(el, "Phone"),
        "alt_phone": _text(el, "AltPhone"),
        "fax": _text(el, "Fax"),
        "email": _text(el, "Email"),
        "cc": _text(el, "Cc"),
        "contact": _text(el, "Contact"),
        "alt_contact": _text(el, "AltContact"),
        "customer_type": _ref(el, "CustomerTypeRef"),
        "terms": _ref(el, "TermsRef"),
        "sales_rep": _ref(el, "SalesRepRef"),
        "open_balance": _amount(el, "OpenBalance"),
        "total_balance": _amount(el, "TotalBalance"),
        "sales_tax_code": _ref(el, "SalesTaxCodeRef"),
        "item_sales_tax": _ref(el, "ItemSalesTaxRef"),
        "resale_number": _text(el, "ResaleNumber"),
        "account_number": _text(el, "AccountNumber"),
        "credit_limit": _amount(el, "CreditLimit"),
        "preferred_payment_method": _ref(el, "PreferredPaymentMethodRef"),
        "job_status": _text(el, "JobStatus"),
        "job_start_date": _text(el, "JobStartDate"),
        "job_projected_end_date": _text(el, "JobProjectedEndDate"),
        "job_end_date": _text(el, "JobEndDate"),
        "job_desc": _text(el, "JobDesc"),
        "job_type": _ref(el, "JobTypeRef"),
        "notes": _text(el, "Notes"),
        "is_statement_with_parent": _bool(el, "IsStatementWithParent"),
        "preferred_delivery_method": _text(el, "PreferredDeliveryMethod"),
        "price_level": _ref(el, "PriceLevelRef"),
        "external_guid": _text(el, "ExternalGUID"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_vendor(el: etree._Element) -> dict:
    return {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "is_active": _bool(el, "IsActive"),
        "company_name": _text(el, "CompanyName"),
        "salutation": _text(el, "Salutation"),
        "first_name": _text(el, "FirstName"),
        "middle_name": _text(el, "MiddleName"),
        "last_name": _text(el, "LastName"),
        "job_title": _text(el, "JobTitle"),
        "vendor_address": _address(el, "VendorAddress"),
        "phone": _text(el, "Phone"),
        "alt_phone": _text(el, "AltPhone"),
        "fax": _text(el, "Fax"),
        "email": _text(el, "Email"),
        "contact": _text(el, "Contact"),
        "alt_contact": _text(el, "AltContact"),
        "name_on_check": _text(el, "NameOnCheck"),
        "account_number": _text(el, "AccountNumber"),
        "notes": _text(el, "Notes"),
        "vendor_type": _ref(el, "VendorTypeRef"),
        "terms": _ref(el, "TermsRef"),
        "credit_limit": _amount(el, "CreditLimit"),
        "vendor_tax_ident": _text(el, "VendorTaxIdent"),
        "is_vendor_eligible_for_1099": _bool(el, "IsVendorEligibleFor1099"),
        "open_balance": _amount(el, "OpenBalance"),
        "external_guid": _text(el, "ExternalGUID"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def _parse_line_items(txn_el: etree._Element, txn_id: str) -> list[dict]:
    """Extract line items from a transaction element.

    QB uses different tag names depending on transaction type:
    - InvoiceLineRet, SalesReceiptLineRet, CreditMemoLineRet, EstimateLineRet,
      SalesOrderLineRet — for sales transactions
    - ItemLineRet — for item-based lines on bills, checks, credit cards, POs, etc.
    - ExpenseLineRet — for expense lines on bills, checks, credit cards, etc.
    - JournalDebitLineRet, JournalCreditLineRet — for journal entries
    - PurchaseOrderLineRet — for purchase orders
    - DepositLineRet — for deposits
    - InventoryAdjustmentLineRet — for inventory adjustments
    """
    lines = []
    seq = 0
    for line_tag in [
        # Sales transaction lines
        "InvoiceLineRet", "SalesReceiptLineRet", "CreditMemoLineRet",
        "EstimateLineRet", "SalesOrderLineRet",
        # Purchase/expense transaction lines (bills, checks, credit cards, etc.)
        "ItemLineRet", "ExpenseLineRet",
        # Specific transaction types
        "PurchaseOrderLineRet",
        "JournalDebitLineRet", "JournalCreditLineRet",
        "DepositLineRet",
        "InventoryAdjustmentLineRet",
        "CheckLineRet", "CreditCardChargeLineRet", "CreditCardCreditLineRet",
        "VendorCreditLineRet",
    ]:
        for line_el in txn_el.findall(line_tag):
            seq += 1
            line = {
                "txn_id": txn_id,
                "line_seq_no": seq,
                "line_type": line_tag.replace("LineRet", "").replace("Ret", ""),
                "item_name": _ref(line_el, "ItemRef") or _ref(line_el, "AccountRef"),
                "item_list_id": _ref(line_el, "ItemRef", "ListID"),
                "description": _text(line_el, "Desc") or _text(line_el, "Memo"),
                "quantity": _amount(line_el, "Quantity"),
                "unit_price": _amount(line_el, "Rate") or _amount(line_el, "Cost") or _amount(line_el, "UnitPrice"),
                "amount": _amount(line_el, "Amount"),
                "sales_tax_code": _ref(line_el, "SalesTaxCodeRef"),
                "class_name": _ref(line_el, "ClassRef"),
                "account_name": _ref(line_el, "AccountRef"),
                "memo": _text(line_el, "Memo"),
                "service_date": _text(line_el, "ServiceDate"),
            }
            lines.append(line)
    return lines


def parse_invoice(el: etree._Element) -> tuple[dict, list[dict]]:
    """Returns (header_dict, [line_dict, ...])."""
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "customer_list_id": _ref(el, "CustomerRef", "ListID"),
        "customer_name": _ref(el, "CustomerRef"),
        "class_name": _ref(el, "ClassRef"),
        "ar_account": _ref(el, "ARAccountRef"),
        "template_name": _ref(el, "TemplateRef"),
        "bill_address": _address(el, "BillAddress"),
        "ship_address": _address(el, "ShipAddress"),
        "is_pending": _bool(el, "IsPending"),
        "is_finance_charge": _bool(el, "IsFinanceCharge"),
        "po_number": _text(el, "PONumber"),
        "terms": _ref(el, "TermsRef"),
        "due_date": _text(el, "DueDate"),
        "sales_rep": _ref(el, "SalesRepRef"),
        "ship_date": _text(el, "ShipDate"),
        "ship_method": _ref(el, "ShipMethodRef"),
        "subtotal": _amount(el, "Subtotal"),
        "item_sales_tax": _ref(el, "ItemSalesTaxRef"),
        "sales_tax_percentage": _amount(el, "SalesTaxPercentage"),
        "sales_tax_total": _amount(el, "SalesTaxTotal"),
        "applied_amount": _amount(el, "AppliedAmount"),
        "balance_remaining": _amount(el, "BalanceRemaining"),
        "memo": _text(el, "Memo"),
        "is_paid": _bool(el, "IsPaid"),
        "external_guid": _text(el, "ExternalGUID"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_line_items(el, txn_id)
    return header, lines


def parse_sales_receipt(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "customer_list_id": _ref(el, "CustomerRef", "ListID"),
        "customer_name": _ref(el, "CustomerRef"),
        "class_name": _ref(el, "ClassRef"),
        "ar_account": _ref(el, "DepositToAccountRef"),
        "payment_method": _ref(el, "PaymentMethodRef"),
        "memo": _text(el, "Memo"),
        "check_number": _text(el, "CheckNumber"),
        "bill_address": _address(el, "BillAddress"),
        "ship_address": _address(el, "ShipAddress"),
        "subtotal": _amount(el, "Subtotal"),
        "sales_tax_total": _amount(el, "SalesTaxTotal"),
        "total_amount": _amount(el, "TotalAmount"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_line_items(el, txn_id)
    return header, lines


def parse_bill(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "vendor_list_id": _ref(el, "VendorRef", "ListID"),
        "vendor_name": _ref(el, "VendorRef"),
        "ap_account": _ref(el, "APAccountRef"),
        "due_date": _text(el, "DueDate"),
        "amount_due": _amount(el, "AmountDue"),
        "memo": _text(el, "Memo"),
        "is_paid": _bool(el, "IsPaid"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_line_items(el, txn_id)
    return header, lines


def parse_item_receipt(el: etree._Element) -> tuple[dict, list[dict]]:
    """Parse ItemReceiptRet — receiving transaction with line items."""
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "vendor_list_id": _ref(el, "VendorRef", "ListID"),
        "vendor_name": _ref(el, "VendorRef"),
        "ap_account": _ref(el, "APAccountRef"),
        "ref_number": _text(el, "RefNumber"),
        "memo": _text(el, "Memo"),
        "total_amount": _amount(el, "TotalAmount"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    # Parse item receipt line items
    # QB uses ItemLineRet for item lines and ExpenseLineRet for expense lines
    lines = []
    seq = 0
    for line_tag in ["ItemLineRet", "ExpenseLineRet", "ItemGroupLineRet"]:
        for line_el in el.findall(line_tag):
            seq += 1
            line = {
                "txn_id": txn_id,
                "line_seq_no": seq,
                "item_name": _ref(line_el, "ItemRef") or _ref(line_el, "AccountRef"),
                "item_list_id": _ref(line_el, "ItemRef", "ListID"),
                "description": _text(line_el, "Desc"),
                "quantity": _amount(line_el, "Quantity"),
                "unit_price": _amount(line_el, "Cost") or _amount(line_el, "UnitPrice"),
                "amount": _amount(line_el, "Amount"),
                "lot_number": _text(line_el, "LotNumber"),
                "expiration_date": _text(line_el, "ExpirationDateForLot"),
                "class_name": _ref(line_el, "ClassRef"),
            }
            lines.append(line)
    return header, lines


def parse_journal_entry(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "is_adjustment": _bool(el, "IsAdjustment"),
        "memo": _text(el, "Memo"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_line_items(el, txn_id)
    return header, lines


def parse_item(el: etree._Element, item_type: str) -> dict:
    """Generic item parser — handles all item types."""
    item = {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "full_name": _text(el, "FullName"),
        "item_type": item_type,
        "is_active": _bool(el, "IsActive"),
        "parent_list_id": _ref(el, "ParentRef", "ListID"),
        "sublevel": _text(el, "Sublevel"),
        "manufacturer_part_number": _text(el, "ManufacturerPartNumber"),
        "unit_of_measure_set": _ref(el, "UnitOfMeasureSetRef"),
        "sales_desc": _text(el, "SalesDesc") or _text(el, "Desc"),
        "sales_price": _amount(el, "SalesPrice") or _amount(el, "Price"),
        "income_account": _ref(el, "IncomeAccountRef"),
        "purchase_desc": _text(el, "PurchaseDesc"),
        "purchase_cost": _amount(el, "PurchaseCost"),
        "cogs_account": _ref(el, "COGSAccountRef"),
        "asset_account": _ref(el, "AssetAccountRef"),
        "preferred_vendor": _ref(el, "PrefVendorRef"),
        "sales_tax_code": _ref(el, "SalesTaxCodeRef"),
        "quantity_on_hand": _amount(el, "QuantityOnHand"),
        "avg_cost": _amount(el, "AverageCost"),
        "quantity_on_order": _amount(el, "QuantityOnOrder"),
        "quantity_on_sales_order": _amount(el, "QuantityOnSalesOrder"),
        "reorder_point": _amount(el, "ReorderPoint"),
        "external_guid": _text(el, "ExternalGUID"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    return item


def _parse_assembly_bom_lines(el: etree._Element, assembly_list_id: str) -> list[dict]:
    """Extract bill of materials lines from an ItemInventoryAssemblyRet."""
    lines = []
    seq = 0
    for line_el in el.findall("ItemInventoryAssemblyLine"):
        seq += 1
        lines.append({
            "assembly_list_id": assembly_list_id,
            "line_seq_no": seq,
            "item_list_id": _ref(line_el, "ItemInventoryRef", "ListID"),
            "item_name": _ref(line_el, "ItemInventoryRef"),
            "quantity": _amount(line_el, "Quantity"),
        })
    return lines


# ============================================================================
# Master response parser
# ============================================================================

# Map item ret element names to item types
ITEM_RET_TYPES = {
    "ItemServiceRet": "Service",
    "ItemInventoryRet": "Inventory",
    "ItemNonInventoryRet": "NonInventory",
    "ItemOtherChargeRet": "OtherCharge",
    "ItemGroupRet": "Group",
    "ItemInventoryAssemblyRet": "InventoryAssembly",
    "ItemDiscountRet": "Discount",
    "ItemPaymentRet": "Payment",
    "ItemSalesTaxRet": "SalesTax",
    "ItemSalesTaxGroupRet": "SalesTaxGroup",
    "ItemSubtotalRet": "Subtotal",
    "ItemFixedAssetRet": "FixedAsset",
}

# Map Rs element names to parser functions and record structure
RESPONSE_PARSERS: dict[str, Any] = {
    "AccountQueryRs": ("AccountRet", parse_account, False),
    "CustomerQueryRs": ("CustomerRet", parse_customer, False),
    "VendorQueryRs": ("VendorRet", parse_vendor, False),
    "InvoiceQueryRs": ("InvoiceRet", parse_invoice, True),
    "SalesReceiptQueryRs": ("SalesReceiptRet", parse_sales_receipt, True),
    "BillQueryRs": ("BillRet", parse_bill, True),
    "ItemReceiptQueryRs": ("ItemReceiptRet", parse_item_receipt, True),
    "JournalEntryQueryRs": ("JournalEntryRet", parse_journal_entry, True),
}


def parse_qbxml_response(xml_string: str, entity_type: str) -> ParsedResponse:
    """
    Parse a full qbXML response string.

    Returns a ParsedResponse with records and iterator metadata.
    For entities with line items (invoices, bills), records contains
    {'header': dict, 'lines': [dict, ...]} per record.
    """
    if not xml_string or not xml_string.strip():
        return ParsedResponse(
            entity_type=entity_type,
            records=[],
            iterator_id=None,
            iterator_remaining=0,
            status_code=-1,
            status_message="Empty response",
            request_id=None,
        )

    try:
        root = etree.fromstring(xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string)
    except etree.XMLSyntaxError as e:
        logger.error("xml_parse_error", error=str(e), entity=entity_type)
        return ParsedResponse(
            entity_type=entity_type,
            records=[],
            iterator_id=None,
            iterator_remaining=0,
            status_code=-1,
            status_message=f"XML parse error: {e}",
            request_id=None,
        )

    msgs_rs = root.find("QBXMLMsgsRs")
    if msgs_rs is None:
        logger.warning("no_QBXMLMsgsRs", entity=entity_type)
        return ParsedResponse(entity_type, [], None, 0, -1, "No QBXMLMsgsRs", None)

    # Find the *QueryRs element — handle both specific and generic
    rs_el = None
    rs_tag = None
    for child in msgs_rs:
        if child.tag.endswith("QueryRs") or child.tag.endswith("Rs"):
            rs_el = child
            rs_tag = child.tag
            break

    if rs_el is None:
        return ParsedResponse(entity_type, [], None, 0, -1, "No response element found", None)

    # Extract status
    status_code = int(rs_el.get("statusCode", "-1"))
    status_message = rs_el.get("statusMessage", "")
    request_id = rs_el.get("requestID")
    iterator_id = rs_el.get("iteratorID")
    iterator_remaining = int(rs_el.get("iteratorRemainingCount", "0"))

    if status_code != 0:
        logger.warning(
            "qbxml_error_status",
            entity=entity_type,
            status_code=status_code,
            message=status_message,
        )
        return ParsedResponse(entity_type, [], iterator_id, iterator_remaining,
                              status_code, status_message, request_id)

    records = []

    # Special handling for ItemQueryRs — mixed item types
    bom_lines: list[dict] = []
    if rs_tag == "ItemQueryRs" or entity_type == "items":
        for item_tag, item_type in ITEM_RET_TYPES.items():
            for item_el in rs_el.findall(item_tag):
                item_dict = parse_item(item_el, item_type)
                records.append(item_dict)
                if item_tag == "ItemInventoryAssemblyRet":
                    bom_lines.extend(_parse_assembly_bom_lines(item_el, item_dict["qb_list_id"]))

    # Special handling for ItemInventoryAssemblyQueryRs — dedicated assembly+BOM query
    elif rs_tag == "ItemInventoryAssemblyQueryRs" or entity_type == "assembly_bom":
        for item_el in rs_el.findall("ItemInventoryAssemblyRet"):
            item_dict = parse_item(item_el, "InventoryAssembly")
            records.append(item_dict)
            bom_lines.extend(_parse_assembly_bom_lines(item_el, item_dict["qb_list_id"]))

    # Specific parsers
    elif rs_tag in RESPONSE_PARSERS:
        ret_tag, parser_fn, has_lines = RESPONSE_PARSERS[rs_tag]
        for ret_el in rs_el.findall(ret_tag):
            if has_lines:
                header, lines = parser_fn(ret_el)
                records.append({"header": header, "lines": lines})
            else:
                records.append(parser_fn(ret_el))

    # Generic fallback: serialize each Ret element to dict
    else:
        for child in rs_el:
            if child.tag.endswith("Ret"):
                records.append(_element_to_dict(child))

    logger.debug(
        "parsed_response",
        entity=entity_type,
        record_count=len(records),
        iterator_remaining=iterator_remaining,
    )

    return ParsedResponse(
        entity_type=entity_type,
        records=records,
        iterator_id=iterator_id,
        iterator_remaining=iterator_remaining,
        status_code=status_code,
        status_message=status_message,
        request_id=request_id,
        bom_lines=bom_lines,
    )


def _element_to_dict(el: etree._Element) -> dict:
    """Generic element-to-dict conversion for unrecognized entities."""
    result = {}
    for child in el:
        tag = child.tag
        # Convert CamelCase to snake_case
        key = re.sub(r"(?<!^)(?=[A-Z])", "_", tag).lower()
        if len(child) > 0:
            result[key] = _element_to_dict(child)
        else:
            result[key] = child.text
    return result
