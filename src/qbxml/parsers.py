"""
qbXML response parsers.
Parses XML response strings from QB into Python dicts ready for Supabase upsert.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
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


def _parse_line_items(txn_el: etree._Element, txn_id: str, line_tags: list[str] | None = None) -> list[dict]:
    """Extract line items from a transaction element.

    Produces dicts matching the standard line table schema (invoice_lines,
    sales_receipt_lines, credit_memo_lines, estimate_lines, sales_order_lines,
    bill_lines, purchase_order_lines).
    """
    if line_tags is None:
        line_tags = [
            # Sales transaction lines
            "InvoiceLineRet", "SalesReceiptLineRet", "CreditMemoLineRet",
            "EstimateLineRet", "SalesOrderLineRet",
            # Purchase/expense transaction lines (bills, checks, credit cards, etc.)
            "ItemLineRet", "ExpenseLineRet",
            # Specific transaction types
            "PurchaseOrderLineRet",
        ]
    lines = []
    seq = 0
    for line_tag in line_tags:
        for line_el in txn_el.findall(line_tag):
            seq += 1
            line = {
                "txn_id": txn_id,
                "line_seq_no": seq,
                "line_type": line_tag.replace("LineRet", "").replace("Ret", ""),
                "item_name": _ref(line_el, "ItemRef") or _ref(line_el, "AccountRef"),
                "item_list_id": _ref(line_el, "ItemRef", "ListID"),
                "account_name": _ref(line_el, "AccountRef"),
                "description": _text(line_el, "Desc") or _text(line_el, "Memo"),
                "quantity": _amount(line_el, "Quantity"),
                "unit_price": _amount(line_el, "Rate") or _amount(line_el, "Cost") or _amount(line_el, "UnitPrice"),
                "amount": _amount(line_el, "Amount"),
                "sales_tax_code": _ref(line_el, "SalesTaxCodeRef"),
                "class_name": _ref(line_el, "ClassRef"),
                "memo": _text(line_el, "Memo"),
                "service_date": _text(line_el, "ServiceDate"),
                "lot_number": _text(line_el, "LotNumber"),
                "serial_number": _text(line_el, "SerialNumber"),
            }
            lines.append(line)
    return lines


def _parse_journal_lines(txn_el: etree._Element, txn_id: str) -> list[dict]:
    """Extract journal entry debit/credit lines.

    journal_entry_lines columns: txn_id, line_seq_no, line_type, account_name,
    amount, memo, entity_name, class_name
    """
    lines = []
    seq = 0
    for line_tag in ["JournalDebitLineRet", "JournalCreditLineRet"]:
        for line_el in txn_el.findall(line_tag):
            seq += 1
            lines.append({
                "txn_id": txn_id,
                "line_seq_no": seq,
                "line_type": "Debit" if "Debit" in line_tag else "Credit",
                "account_name": _ref(line_el, "AccountRef"),
                "amount": _amount(line_el, "Amount"),
                "memo": _text(line_el, "Memo"),
                "entity_name": _ref(line_el, "EntityRef"),
                "class_name": _ref(line_el, "ClassRef"),
            })
    return lines


def _parse_deposit_lines(txn_el: etree._Element, txn_id: str) -> list[dict]:
    """Extract deposit lines.

    deposit_lines columns: txn_id, line_seq_no, entity_name, account_name,
    memo, amount, payment_method
    """
    lines = []
    seq = 0
    for line_el in txn_el.findall("DepositLineRet"):
        seq += 1
        lines.append({
            "txn_id": txn_id,
            "line_seq_no": seq,
            "entity_name": _ref(line_el, "EntityRef"),
            "account_name": _ref(line_el, "AccountRef"),
            "memo": _text(line_el, "Memo"),
            "amount": _amount(line_el, "Amount"),
            "payment_method": _ref(line_el, "PaymentMethodRef"),
        })
    return lines


def _parse_check_expense_lines(txn_el: etree._Element, txn_id: str) -> list[dict]:
    """Extract check/credit card charge/credit lines.

    check_lines, credit_card_charge_lines, credit_card_credit_lines columns:
    txn_id, line_seq_no, account_name, item_name, description, amount
    """
    lines = []
    seq = 0
    for line_tag in ["ItemLineRet", "ExpenseLineRet"]:
        for line_el in txn_el.findall(line_tag):
            seq += 1
            lines.append({
                "txn_id": txn_id,
                "line_seq_no": seq,
                "account_name": _ref(line_el, "AccountRef"),
                "item_name": _ref(line_el, "ItemRef"),
                "description": _text(line_el, "Desc") or _text(line_el, "Memo"),
                "amount": _amount(line_el, "Amount"),
                "lot_number": _text(line_el, "LotNumber"),
                "serial_number": _text(line_el, "SerialNumber"),
            })
    return lines


def _parse_vendor_credit_lines(txn_el: etree._Element, txn_id: str) -> list[dict]:
    """Extract vendor credit lines.

    vendor_credit_lines columns: txn_id, line_seq_no, account_name, item_name,
    description, amount
    """
    lines = []
    seq = 0
    for line_tag in ["ItemLineRet", "ExpenseLineRet"]:
        for line_el in txn_el.findall(line_tag):
            seq += 1
            lines.append({
                "txn_id": txn_id,
                "line_seq_no": seq,
                "account_name": _ref(line_el, "AccountRef"),
                "item_name": _ref(line_el, "ItemRef"),
                "description": _text(line_el, "Desc") or _text(line_el, "Memo"),
                "amount": _amount(line_el, "Amount"),
                "lot_number": _text(line_el, "LotNumber"),
                "serial_number": _text(line_el, "SerialNumber"),
            })
    return lines


def _parse_inventory_adjustment_lines(txn_el: etree._Element, txn_id: str) -> list[dict]:
    """Extract inventory adjustment lines.

    inventory_adjustment_lines columns: txn_id, line_seq_no, item_name,
    item_list_id, qty_diff, value_diff, new_quantity, new_value
    """
    lines = []
    seq = 0
    for line_el in txn_el.findall("InventoryAdjustmentLineRet"):
        seq += 1
        lines.append({
            "txn_id": txn_id,
            "line_seq_no": seq,
            "item_name": _ref(line_el, "ItemRef"),
            "item_list_id": _ref(line_el, "ItemRef", "ListID"),
            "qty_diff": _amount(line_el, "QuantityDifference"),
            "value_diff": _amount(line_el, "ValueDifference"),
            "new_quantity": _amount(line_el, "QuantityNew"),
            "new_value": _amount(line_el, "ValueNew"),
            "lot_number": _text(line_el, "LotNumber"),
            "serial_number": _text(line_el, "SerialNumber"),
        })
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
                "serial_number": _text(line_el, "SerialNumber"),
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
    lines = _parse_journal_lines(el, txn_id)
    return header, lines


# ============================================================================
# List entity parsers (no line items)
# ============================================================================

def parse_unit_of_measure_set(el: etree._Element) -> list[dict]:
    """Flatten a UnitOfMeasureSetRet into one row per unit.

    QB returns a Set with a BaseUnit + multiple RelatedUnit rows + DefaultUnit
    role mappings. We denormalize so each unit (base or related) becomes one
    row, with conversion_ratio measured in base units per 1 of this unit.
    Base unit gets NULL conversion_ratio (it is 1 by definition).
    """
    list_id = _text(el, "ListID")
    set_name = _text(el, "Name")
    set_type = _text(el, "UnitOfMeasureType")
    is_active = _bool(el, "IsActive")
    time_created = _text(el, "TimeCreated")
    time_modified = _text(el, "TimeModified")
    edit_sequence = _text(el, "EditSequence")

    default_for_by_unit: dict[str, str] = {}
    for du in el.findall("DefaultUnit"):
        unit_name = _text(du, "Unit")
        used_for = _text(du, "UnitUsedFor")
        if unit_name and used_for:
            default_for_by_unit[unit_name] = used_for

    rows: list[dict] = []
    base = el.find("BaseUnit")
    if base is not None:
        bn = _text(base, "Name")
        rows.append({
            "qb_list_id": list_id,
            "set_name": set_name,
            "unit_of_measure_type": set_type,
            "is_active": is_active,
            "unit_name": bn,
            "unit_abbreviation": _text(base, "Abbreviation"),
            "is_base_unit": True,
            "conversion_ratio": None,
            "default_for": default_for_by_unit.get(bn or ""),
            "time_created": time_created,
            "time_modified": time_modified,
            "edit_sequence": edit_sequence,
        })
    for related in el.findall("RelatedUnit"):
        rn = _text(related, "Name")
        rows.append({
            "qb_list_id": list_id,
            "set_name": set_name,
            "unit_of_measure_type": set_type,
            "is_active": is_active,
            "unit_name": rn,
            "unit_abbreviation": _text(related, "Abbreviation"),
            "is_base_unit": False,
            "conversion_ratio": _amount(related, "ConversionRatio"),
            "default_for": default_for_by_unit.get(rn or ""),
            "time_created": time_created,
            "time_modified": time_modified,
            "edit_sequence": edit_sequence,
        })
    return rows


def parse_class(el: etree._Element) -> dict:
    return {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "full_name": _text(el, "FullName"),
        "is_active": _bool(el, "IsActive"),
        "parent_list_id": _ref(el, "ParentRef", "ListID"),
        "sublevel": _text(el, "Sublevel"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_inventory_site(el: etree._Element) -> dict | None:
    """Extract the InventorySite info from an ItemSitesRet row.

    Each ItemSitesRet has a nested <InventorySiteRef> with ListID +
    FullName. We don't care about the per-item quantities here — only
    the site reference. The caller dedupes the returned dicts on
    qb_list_id so 1378 ItemSitesRet rows (689 items × 2 sites) collapse
    into 2 inventory_sites rows.
    """
    site_ref = el.find("InventorySiteRef")
    if site_ref is None:
        return None
    list_id = _text(site_ref, "ListID")
    full_name = _text(site_ref, "FullName")
    if not list_id:
        return None
    return {
        "qb_list_id": list_id,
        "name": full_name,
        "full_name": full_name,
        "is_active": True,  # ItemSitesRet only includes active site refs
        "site_desc": None,
        "contact": None,
        "phone": None,
        "email": None,
        "time_created": None,
        "time_modified": None,
        "edit_sequence": None,
    }


def parse_sales_tax_code(el: etree._Element) -> dict:
    return {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "is_active": _bool(el, "IsActive"),
        "is_taxable": _bool(el, "IsTaxable"),
        "description": _text(el, "Desc"),
        "item_purchase_tax_ref": _ref(el, "ItemPurchaseTaxRef"),
        "item_sales_tax_ref": _ref(el, "ItemSalesTaxRef"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_payment_method(el: etree._Element) -> dict:
    return {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "is_active": _bool(el, "IsActive"),
        "payment_method_type": _text(el, "PaymentMethodType"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_ship_method(el: etree._Element) -> dict:
    return {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "is_active": _bool(el, "IsActive"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_terms(el: etree._Element) -> dict:
    return {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "is_active": _bool(el, "IsActive"),
        "is_standard_terms": True,
        "std_due_days": _amount(el, "StdDueDays"),
        "std_discount_days": _amount(el, "StdDiscountDays"),
        "discount_pct": _amount(el, "DiscountPct"),
        "day_of_month_due": _amount(el, "DayOfMonthDue"),
        "due_next_month_days": _amount(el, "DueNextMonthDays"),
        "discount_day_of_month": _amount(el, "DiscountDayOfMonth"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_employee(el: etree._Element) -> dict:
    return {
        "qb_list_id": _text(el, "ListID"),
        "name": _text(el, "Name"),
        "is_active": _bool(el, "IsActive"),
        "salutation": _text(el, "Salutation"),
        "first_name": _text(el, "FirstName"),
        "middle_name": _text(el, "MiddleName"),
        "last_name": _text(el, "LastName"),
        "suffix": _text(el, "Suffix"),
        "job_title": _text(el, "JobTitle"),
        "address": _address(el, "EmployeeAddress"),
        "phone": _text(el, "Phone"),
        "mobile": _text(el, "Mobile"),
        "email": _text(el, "Email"),
        "employee_type": _text(el, "EmployeeType"),
        "gender": _text(el, "Gender"),
        "hired_date": _text(el, "HiredDate"),
        "released_date": _text(el, "ReleasedDate"),
        "external_guid": _text(el, "ExternalGUID"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


# ============================================================================
# Transaction parsers (with line items)
# ============================================================================

def parse_credit_memo(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "customer_list_id": _ref(el, "CustomerRef", "ListID"),
        "customer_name": _ref(el, "CustomerRef"),
        "class_name": _ref(el, "ClassRef"),
        "ar_account": _ref(el, "ARAccountRef"),
        "memo": _text(el, "Memo"),
        "subtotal": _amount(el, "Subtotal"),
        "sales_tax_total": _amount(el, "SalesTaxTotal"),
        "total_credit_remaining": _amount(el, "CreditRemaining") or _amount(el, "TotalAmount"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_line_items(el, txn_id, ["CreditMemoLineRet"])
    return header, lines


def parse_purchase_order(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "vendor_list_id": _ref(el, "VendorRef", "ListID"),
        "vendor_name": _ref(el, "VendorRef"),
        "class_name": _ref(el, "ClassRef"),
        "ship_address": _address(el, "ShipAddress"),
        "terms": _ref(el, "TermsRef"),
        "due_date": _text(el, "DueDate"),
        "expected_date": _text(el, "ExpectedDate"),
        "ship_method": _ref(el, "ShipMethodRef"),
        "is_manually_closed": _bool(el, "IsManuallyClosed"),
        "is_fully_received": _bool(el, "IsFullyReceived"),
        "memo": _text(el, "Memo"),
        "subtotal": _amount(el, "Subtotal"),
        "total_amount": _amount(el, "TotalAmount"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = []
    seq = 0
    for line_el in el.findall("PurchaseOrderLineRet"):
        seq += 1
        lines.append({
            "txn_id": txn_id,
            "line_seq_no": seq,
            "item_name": _ref(line_el, "ItemRef"),
            "item_list_id": _ref(line_el, "ItemRef", "ListID"),
            "description": _text(line_el, "Desc"),
            "quantity": _amount(line_el, "Quantity"),
            "unit_price": _amount(line_el, "Rate"),
            "amount": _amount(line_el, "Amount"),
            "class_name": _ref(line_el, "ClassRef"),
            "is_manually_closed": _bool(line_el, "IsManuallyClosed"),
            "qty_received_on_items": _amount(line_el, "ReceivedQuantity"),
        })
    return header, lines


def parse_estimate(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "customer_list_id": _ref(el, "CustomerRef", "ListID"),
        "customer_name": _ref(el, "CustomerRef"),
        "class_name": _ref(el, "ClassRef"),
        "is_active": _bool(el, "IsActive"),
        "estimate_state": _text(el, "EstimateState") or _text(el, "IsActive"),
        "expiration_date": _text(el, "ExpirationDate"),
        "memo": _text(el, "Memo"),
        "subtotal": _amount(el, "Subtotal"),
        "sales_tax_total": _amount(el, "SalesTaxTotal"),
        "total_amount": _amount(el, "TotalAmount"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_line_items(el, txn_id, ["EstimateLineRet"])
    return header, lines


def parse_sales_order(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "customer_list_id": _ref(el, "CustomerRef", "ListID"),
        "customer_name": _ref(el, "CustomerRef"),
        "class_name": _ref(el, "ClassRef"),
        "is_manually_closed": _bool(el, "IsManuallyClosed"),
        "is_fully_invoiced": _bool(el, "IsFullyInvoiced"),
        "memo": _text(el, "Memo"),
        "subtotal": _amount(el, "Subtotal"),
        "total_amount": _amount(el, "TotalAmount"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = []
    seq = 0
    for line_el in el.findall("SalesOrderLineRet"):
        seq += 1
        lines.append({
            "txn_id": txn_id,
            "line_seq_no": seq,
            "item_name": _ref(line_el, "ItemRef"),
            "item_list_id": _ref(line_el, "ItemRef", "ListID"),
            "description": _text(line_el, "Desc"),
            "quantity": _amount(line_el, "Quantity"),
            "unit_price": _amount(line_el, "Rate"),
            "amount": _amount(line_el, "Amount"),
            "qty_invoiced": _amount(line_el, "Invoiced"),
            "is_manually_closed": _bool(line_el, "IsManuallyClosed"),
        })
    return header, lines


def parse_check(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "bank_account": _ref(el, "AccountRef"),
        "entity_name": _ref(el, "PayeeEntityRef"),
        "is_to_be_printed": _bool(el, "IsToBePrinted"),
        "memo": _text(el, "Memo"),
        "amount": _amount(el, "Amount"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_check_expense_lines(el, txn_id)
    return header, lines


def parse_credit_card_charge(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "credit_card_account": _ref(el, "AccountRef"),
        "entity_name": _ref(el, "PayeeEntityRef"),
        "memo": _text(el, "Memo"),
        "amount": _amount(el, "Amount"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_check_expense_lines(el, txn_id)
    return header, lines


def parse_credit_card_credit(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "credit_card_account": _ref(el, "AccountRef"),
        "entity_name": _ref(el, "PayeeEntityRef"),
        "memo": _text(el, "Memo"),
        "amount": _amount(el, "Amount"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_check_expense_lines(el, txn_id)
    return header, lines


def parse_vendor_credit(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "vendor_list_id": _ref(el, "VendorRef", "ListID"),
        "vendor_name": _ref(el, "VendorRef"),
        "ap_account": _ref(el, "APAccountRef"),
        "amount": _amount(el, "CreditAmount") or _amount(el, "TotalAmount"),
        "memo": _text(el, "Memo"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_vendor_credit_lines(el, txn_id)
    return header, lines


def parse_deposit(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_date": _text(el, "TxnDate"),
        "deposit_to_account": _ref(el, "DepositToAccountRef"),
        "memo": _text(el, "Memo"),
        "total_amount": _amount(el, "DepositTotal"),
        "cash_back_account": _ref(el, "CashBackInfoRet/AccountRef") if el.find("CashBackInfoRet") else None,
        "cash_back_memo": _text(el, "CashBackInfoRet/Memo") if el.find("CashBackInfoRet") else None,
        "cash_back_amount": _amount(el, "CashBackInfoRet/Amount") if el.find("CashBackInfoRet") else None,
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_deposit_lines(el, txn_id)
    return header, lines


def parse_inventory_adjustment(el: etree._Element) -> tuple[dict, list[dict]]:
    txn_id = _text(el, "TxnID") or ""
    header = {
        "qb_txn_id": txn_id,
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "account_name": _ref(el, "AccountRef"),
        "class_name": _ref(el, "ClassRef"),
        "memo": _text(el, "Memo"),
        "customer_name": _ref(el, "CustomerRef"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }
    lines = _parse_inventory_adjustment_lines(el, txn_id)
    return header, lines


# ============================================================================
# Transaction parsers (no line items)
# ============================================================================

def parse_bill_payment(el: etree._Element) -> dict:
    return {
        "qb_txn_id": _text(el, "TxnID"),
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "vendor_list_id": _ref(el, "PayeeEntityRef", "ListID"),
        "vendor_name": _ref(el, "PayeeEntityRef"),
        "payment_method_type": "Check",
        "bank_account": _ref(el, "BankAccountRef"),
        "ap_account": _ref(el, "APAccountRef"),
        "amount": _amount(el, "Amount"),
        "memo": _text(el, "Memo"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_receive_payment(el: etree._Element) -> dict:
    return {
        "qb_txn_id": _text(el, "TxnID"),
        "txn_number": _text(el, "RefNumber"),
        "txn_date": _text(el, "TxnDate"),
        "customer_list_id": _ref(el, "CustomerRef", "ListID"),
        "customer_name": _ref(el, "CustomerRef"),
        "ar_account": _ref(el, "ARAccountRef"),
        "total_amount": _amount(el, "TotalAmount"),
        "payment_method": _ref(el, "PaymentMethodRef"),
        "memo": _text(el, "Memo"),
        "deposit_to_account": _ref(el, "DepositToAccountRef"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_transfer(el: etree._Element) -> dict:
    return {
        "qb_txn_id": _text(el, "TxnID"),
        "txn_date": _text(el, "TxnDate"),
        "from_account": _ref(el, "TransferFromAccountRef"),
        "from_amount": _amount(el, "FromAccountBalance") or _amount(el, "Amount"),
        "to_account": _ref(el, "TransferToAccountRef"),
        "to_amount": _amount(el, "ToAccountBalance") or _amount(el, "Amount"),
        "memo": _text(el, "Memo"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


def parse_time_tracking(el: etree._Element) -> dict:
    # Parse duration: QB returns "PT8H30M" or hours as text
    duration_text = _text(el, "Duration")
    duration_hours = None
    if duration_text:
        import re as _re
        m = _re.match(r"PT(\d+)H(\d+)M", duration_text)
        if m:
            duration_hours = int(m.group(1)) + int(m.group(2)) / 60.0
        else:
            try:
                duration_hours = float(duration_text)
            except (ValueError, TypeError):
                pass
    return {
        "qb_txn_id": _text(el, "TxnID"),
        "txn_date": _text(el, "TxnDate"),
        "entity_name": _ref(el, "EntityRef"),
        "customer_name": _ref(el, "CustomerRef"),
        "item_service_name": _ref(el, "ItemServiceRef"),
        "class_name": _ref(el, "ClassRef"),
        "duration_hours": duration_hours,
        "notes": _text(el, "Notes"),
        "is_billable": _text(el, "BillableStatus"),
        "billing_status": _text(el, "BillableStatus"),
        "time_created": _text(el, "TimeCreated"),
        "time_modified": _text(el, "TimeModified"),
        "edit_sequence": _text(el, "EditSequence"),
    }


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
# (ret_tag, parser_fn, has_lines)
RESPONSE_PARSERS: dict[str, Any] = {
    # List objects (no lines)
    "AccountQueryRs": ("AccountRet", parse_account, False),
    "ClassQueryRs": ("ClassRet", parse_class, False),
    # Inventory-site discovery rides on ItemSitesQueryRq — see
    # parse_inventory_site() docstring + the special-case dispatch
    # below that dedupes the per-item-per-site rows down to unique
    # site refs.
    "ItemSitesQueryRs": ("ItemSitesRet", parse_inventory_site, False),
    "SalesTaxCodeQueryRs": ("SalesTaxCodeRet", parse_sales_tax_code, False),
    "PaymentMethodQueryRs": ("PaymentMethodRet", parse_payment_method, False),
    "ShipMethodQueryRs": ("ShipMethodRet", parse_ship_method, False),
    "StandardTermsQueryRs": ("StandardTermsRet", parse_terms, False),
    "CustomerQueryRs": ("CustomerRet", parse_customer, False),
    "VendorQueryRs": ("VendorRet", parse_vendor, False),
    "EmployeeQueryRs": ("EmployeeRet", parse_employee, False),
    # Transactions with lines
    "InvoiceQueryRs": ("InvoiceRet", parse_invoice, True),
    "SalesReceiptQueryRs": ("SalesReceiptRet", parse_sales_receipt, True),
    "CreditMemoQueryRs": ("CreditMemoRet", parse_credit_memo, True),
    "BillQueryRs": ("BillRet", parse_bill, True),
    "ItemReceiptQueryRs": ("ItemReceiptRet", parse_item_receipt, True),
    "PurchaseOrderQueryRs": ("PurchaseOrderRet", parse_purchase_order, True),
    "EstimateQueryRs": ("EstimateRet", parse_estimate, True),
    "SalesOrderQueryRs": ("SalesOrderRet", parse_sales_order, True),
    "CheckQueryRs": ("CheckRet", parse_check, True),
    "CreditCardChargeQueryRs": ("CreditCardChargeRet", parse_credit_card_charge, True),
    "CreditCardCreditQueryRs": ("CreditCardCreditRet", parse_credit_card_credit, True),
    "VendorCreditQueryRs": ("VendorCreditRet", parse_vendor_credit, True),
    "DepositQueryRs": ("DepositRet", parse_deposit, True),
    "InventoryAdjustmentQueryRs": ("InventoryAdjustmentRet", parse_inventory_adjustment, True),
    "JournalEntryQueryRs": ("JournalEntryRet", parse_journal_entry, True),
    # Transactions without lines
    "BillPaymentCheckQueryRs": ("BillPaymentCheckRet", parse_bill_payment, False),
    "ReceivePaymentQueryRs": ("ReceivePaymentRet", parse_receive_payment, False),
    "TransferQueryRs": ("TransferRet", parse_transfer, False),
    "TimeTrackingQueryRs": ("TimeTrackingRet", parse_time_tracking, False),
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

    # Special handling for ItemInventoryQueryRs — inventory-only items with qty/cost fields
    elif rs_tag == "ItemInventoryQueryRs" or entity_type == "inventory_items":
        for item_el in rs_el.findall("ItemInventoryRet"):
            records.append(parse_item(item_el, "Inventory"))

    # Special handling for ItemInventoryAssemblyQueryRs — dedicated assembly+BOM query
    elif rs_tag == "ItemInventoryAssemblyQueryRs" or entity_type == "assembly_bom":
        for item_el in rs_el.findall("ItemInventoryAssemblyRet"):
            item_dict = parse_item(item_el, "InventoryAssembly")
            records.append(item_dict)
            bom_lines.extend(_parse_assembly_bom_lines(item_el, item_dict["qb_list_id"]))

    # UoM sets: each Set fans out into multiple rows (one per unit). The
    # upserter treats the resulting list of dicts as ordinary records.
    elif rs_tag == "UnitOfMeasureSetQueryRs" or entity_type == "unit_of_measure_sets":
        for set_el in rs_el.findall("UnitOfMeasureSetRet"):
            records.extend(parse_unit_of_measure_set(set_el))

    # ItemSitesQueryRs returns one row per (item, site). We only need
    # the site refs, deduped by ListID, to build adk_fragrance.inventory_sites.
    elif rs_tag == "ItemSitesQueryRs" or entity_type == "inventory_sites":
        seen_site_ids: set[str] = set()
        for ret_el in rs_el.findall("ItemSitesRet"):
            row = parse_inventory_site(ret_el)
            if not row:
                continue
            site_id = row["qb_list_id"]
            if site_id in seen_site_ids:
                continue
            seen_site_ids.add(site_id)
            records.append(row)

    # Specific parsers
    elif rs_tag in RESPONSE_PARSERS:
        ret_tag, parser_fn, has_lines = RESPONSE_PARSERS[rs_tag]
        for ret_el in rs_el.findall(ret_tag):
            if has_lines:
                header, lines = parser_fn(ret_el)
                records.append({"header": header, "lines": lines})
            else:
                rec = parser_fn(ret_el)
                if rec is not None:
                    records.append(rec)

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


# ============================================================================
# Write response parsers
# ============================================================================

@dataclass
class CompanyIdentity:
    """Result of parsing a CompanyQueryRq response — used to verify which QB
    file QBWC actually connected to before any data is upserted."""
    success: bool
    status_code: int
    status_message: str
    company_name: str | None = None
    legal_company_name: str | None = None
    file_name: str | None = None


def parse_company_query_response(xml_string: str) -> CompanyIdentity:
    """Parse a CompanyQueryRs response — extract <CompanyName>, <LegalCompanyName>,
    <FileName>. Used by the session identity-verification step."""
    if not xml_string or not xml_string.strip():
        return CompanyIdentity(success=False, status_code=-1, status_message="Empty response")
    try:
        root = etree.fromstring(
            xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
        )
    except etree.XMLSyntaxError as e:
        return CompanyIdentity(success=False, status_code=-1, status_message=f"XML parse error: {e}")

    msgs_rs = root.find("QBXMLMsgsRs")
    if msgs_rs is None:
        return CompanyIdentity(success=False, status_code=-1, status_message="No QBXMLMsgsRs")

    rs = None
    for child in msgs_rs:
        if str(child.tag).endswith("CompanyQueryRs"):
            rs = child
            break
    if rs is None:
        return CompanyIdentity(success=False, status_code=-1, status_message="No CompanyQueryRs")

    status_code = int(rs.get("statusCode", "-1"))
    status_message = rs.get("statusMessage", "")
    if status_code != 0:
        return CompanyIdentity(
            success=False, status_code=status_code, status_message=status_message,
        )

    ret = rs.find("CompanyRet")
    if ret is None:
        return CompanyIdentity(
            success=False, status_code=-1, status_message="No CompanyRet element",
        )

    return CompanyIdentity(
        success=True,
        status_code=0,
        status_message=status_message,
        company_name=_text(ret, "CompanyName"),
        legal_company_name=_text(ret, "LegalCompanyName"),
        file_name=_text(ret, "FileName"),
    )


@dataclass
class WriteResponse:
    """Result of parsing a qbXML write (Add/Mod) response."""
    success: bool
    status_code: int
    status_message: str
    request_id: str | None
    txn_id: str | None = None
    txn_number: str | None = None
    edit_sequence: str | None = None
    # For BuildAssemblyAdd: QB sets <IsPending>true</IsPending> when the build
    # was recorded as pending (e.g. because <MarkPendingIfRequired>true</...>
    # was sent and one or more components were short). None when the response
    # didn't include IsPending (e.g. non-build-assembly operations).
    is_pending: bool | None = None


def parse_write_response(xml_string: str) -> WriteResponse:
    """
    Parse a qbXML Add/Mod response (e.g. BuildAssemblyAddRs).

    Returns a WriteResponse with success/failure and the created TxnID.
    """
    # Truncated copy of the raw response we can embed in status_message when
    # the response shape doesn't match what we expect — without it, all we
    # know is "parse failed" and there's no way to diagnose post-hoc.
    raw_preview = (
        xml_string[:3000] if isinstance(xml_string, str) else xml_string.decode("utf-8", "replace")[:3000]
    ) if xml_string else ""

    if not xml_string or not xml_string.strip():
        return WriteResponse(
            success=False, status_code=-1,
            status_message="Empty response", request_id=None,
        )

    try:
        root = etree.fromstring(
            xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
        )
    except etree.XMLSyntaxError as e:
        return WriteResponse(
            success=False, status_code=-1,
            status_message=f"XML parse error: {e} | RAW: {raw_preview}", request_id=None,
        )

    msgs_rs = root.find("QBXMLMsgsRs")
    if msgs_rs is None:
        return WriteResponse(
            success=False, status_code=-1,
            status_message=f"No QBXMLMsgsRs | RAW: {raw_preview}", request_id=None,
        )

    # Find the *AddRs, *ModRs, or *DelRs element. Delete responses use
    # the generic <TxnDelRs> name (which also ends in DelRs).
    rs_el = None
    for child in msgs_rs:
        tag = child.tag
        if tag.endswith("AddRs") or tag.endswith("ModRs") or tag.endswith("DelRs"):
            rs_el = child
            break

    if rs_el is None:
        # Capture the immediate children's tag names + the raw XML for diagnosis.
        child_tags = [str(c.tag) for c in msgs_rs]
        return WriteResponse(
            success=False, status_code=-1,
            status_message=(
                f"No Add/Mod response element found | "
                f"QBXMLMsgsRs children={child_tags} | RAW: {raw_preview}"
            ),
            request_id=None,
        )

    status_code = int(rs_el.get("statusCode", "-1"))
    status_message = rs_el.get("statusMessage", "")
    request_id = rs_el.get("requestID")

    if status_code != 0:
        logger.warning(
            "write_response_error",
            status_code=status_code,
            message=status_message,
        )
        return WriteResponse(
            success=False, status_code=status_code,
            status_message=status_message, request_id=request_id,
        )

    # For Add/Mod responses the Ret element wraps the result
    # (e.g. BuildAssemblyRet). For Del responses (TxnDelRs) the fields
    # are direct children of rs_el (TxnID, TxnDelType, TimeDeleted).
    ret_el = None
    is_del = rs_el.tag.endswith("DelRs")
    if not is_del:
        for child in rs_el:
            if child.tag.endswith("Ret"):
                ret_el = child
                break
    field_source = ret_el if ret_el is not None else (rs_el if is_del else None)

    txn_id = None
    txn_number = None
    edit_sequence = None
    is_pending = None
    if field_source is not None:
        txn_id = _text(field_source, "TxnID")
        txn_number = _text(field_source, "RefNumber")
        edit_sequence = _text(field_source, "EditSequence")
        is_pending = _bool(field_source, "IsPending")

    return WriteResponse(
        success=True,
        status_code=0,
        status_message=status_message,
        request_id=request_id,
        txn_id=txn_id,
        txn_number=txn_number,
        edit_sequence=edit_sequence,
        is_pending=is_pending,
    )
