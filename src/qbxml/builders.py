"""
qbXML request builders.
Generates properly formatted qbXML query strings for each entity type.
"""
from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


QBXML_VERSION = "13.0"
QBXML_HEADER = '<?xml version="1.0" encoding="utf-8"?>\n<?qbxml version="{version}"?>\n'


def _pretty_xml(element: Element) -> str:
    """Serialize element to pretty XML string."""
    raw = tostring(element, encoding="unicode")
    parsed = minidom.parseString(raw)
    # Return without XML declaration (we prepend our own)
    lines = parsed.toprettyxml(indent="  ").split("\n")
    # Remove the first XML declaration line added by toprettyxml
    if lines[0].startswith("<?xml"):
        lines = lines[1:]
    return "\n".join(line for line in lines if line.strip())


def _build_qbxml_envelope(request_element: Element) -> str:
    """Wrap a request element in the standard QBXML envelope."""
    qbxml = Element("QBXML")
    msgs = SubElement(qbxml, "QBXMLMsgsRq", onError="stopOnError")
    msgs.append(request_element)
    header = QBXML_HEADER.format(version=QBXML_VERSION)
    return header + _pretty_xml(qbxml)


def build_generic_query(
    query_rq: str,
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 100,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
    is_transaction: bool = False,
    include_line_items: bool = False,
) -> str:
    """
    Generic qbXML query builder for any entity.

    Args:
        query_rq: e.g. "CustomerQueryRq"
        request_id: Unique ID for this request within the session
        from_modified_date: ISO datetime for incremental sync filter
        max_returned: Batch size
        iterator_start: Start a new iterator
        iterator_continue: Continue an existing iterator
        iterator_id: Required when iterator_continue=True
        is_transaction: True for transactions (use ModifiedDateRangeFilter),
                        False for lists (use bare FromModifiedDate)
        include_line_items: Add IncludeLineItems=true for transactions with lines
    """
    attrs = {"requestID": request_id}
    if iterator_start:
        attrs["iterator"] = "Start"
    elif iterator_continue:
        attrs["iterator"] = "Continue"
        if iterator_id:
            attrs["iteratorID"] = iterator_id

    rq = Element(query_rq, **attrs)

    # MaxReturned
    max_el = SubElement(rq, "MaxReturned")
    max_el.text = str(max_returned)

    # Incremental filter — don't add on Continue (must match original request)
    if from_modified_date and not iterator_continue:
        if is_transaction:
            # Transaction queries use ModifiedDateRangeFilter wrapper
            date_filter = SubElement(rq, "ModifiedDateRangeFilter")
            SubElement(date_filter, "FromModifiedDate").text = from_modified_date
        else:
            # List queries use bare FromModifiedDate
            SubElement(rq, "FromModifiedDate").text = from_modified_date

    # Include line items for transactions that have them
    if include_line_items:
        SubElement(rq, "IncludeLineItems").text = "true"

    return _build_qbxml_envelope(rq)


def build_customer_query(
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 100,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
) -> str:
    """Build CustomerQueryRq with all useful fields."""
    attrs = {"requestID": request_id}
    if iterator_start:
        attrs["iterator"] = "Start"
    elif iterator_continue and iterator_id:
        attrs["iterator"] = "Continue"
        attrs["iteratorID"] = iterator_id

    rq = Element("CustomerQueryRq", **attrs)
    SubElement(rq, "MaxReturned").text = str(max_returned)

    if from_modified_date and not iterator_continue:
        SubElement(rq, "FromModifiedDate").text = from_modified_date

    # Include all fields
    for field in [
        "ListID", "TimeCreated", "TimeModified", "EditSequence",
        "Name", "FullName", "IsActive", "ClassRef",
        "ParentRef", "Sublevel", "CompanyName",
        "Salutation", "FirstName", "MiddleName", "LastName", "Suffix",
        "JobTitle", "BillAddress", "ShipAddress",
        "Phone", "AltPhone", "Fax", "Email", "Cc",
        "Contact", "AltContact",
        "CustomerTypeRef", "TermsRef", "SalesRepRef",
        "OpenBalance", "OpenBalanceDate", "TotalBalance",
        "SalesTaxCodeRef", "ItemSalesTaxRef", "SalesTaxCountry",
        "ResaleNumber", "AccountNumber",
        "CreditLimit", "PreferredPaymentMethodRef",
        "CreditCardInfo", "JobStatus", "JobStartDate",
        "JobProjectedEndDate", "JobEndDate", "JobDesc", "JobTypeRef",
        "Notes", "IsStatementWithParent", "PreferredDeliveryMethod",
        "PriceLevelRef", "ExternalGUID", "CurrencyRef",
    ]:
        SubElement(rq, "IncludeRetElement").text = field

    return _build_qbxml_envelope(rq)


def build_invoice_query(
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 50,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
) -> str:
    """Build InvoiceQueryRq — includes line items."""
    attrs = {"requestID": request_id}
    if iterator_start:
        attrs["iterator"] = "Start"
    elif iterator_continue and iterator_id:
        attrs["iterator"] = "Continue"
        attrs["iteratorID"] = iterator_id

    rq = Element("InvoiceQueryRq", **attrs)
    SubElement(rq, "MaxReturned").text = str(max_returned)

    if from_modified_date and not iterator_continue:
        df = SubElement(rq, "ModifiedDateRangeFilter")
        SubElement(df, "FromModifiedDate").text = from_modified_date

    # Include line items
    SubElement(rq, "IncludeLineItems").text = "true"
    SubElement(rq, "IncludeLinkedTxns").text = "true"

    return _build_qbxml_envelope(rq)


def build_item_query(
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 100,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
) -> str:
    """
    ItemQueryRq retrieves ALL item types in one query.
    Response contains mixed ItemServiceRet, ItemInventoryRet, etc.
    """
    attrs = {"requestID": request_id}
    if iterator_start:
        attrs["iterator"] = "Start"
    elif iterator_continue and iterator_id:
        attrs["iterator"] = "Continue"
        attrs["iteratorID"] = iterator_id

    rq = Element("ItemQueryRq", **attrs)
    SubElement(rq, "MaxReturned").text = str(max_returned)

    if from_modified_date and not iterator_continue:
        SubElement(rq, "FromModifiedDate").text = from_modified_date

    return _build_qbxml_envelope(rq)


def build_account_query(
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 200,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
) -> str:
    # AccountQueryRq does NOT support iterator in QB Desktop
    attrs = {"requestID": request_id}

    rq = Element("AccountQueryRq", **attrs)

    if from_modified_date:
        SubElement(rq, "FromModifiedDate").text = from_modified_date

    return _build_qbxml_envelope(rq)


def build_vendor_query(
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 100,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
) -> str:
    attrs = {"requestID": request_id}
    if iterator_start:
        attrs["iterator"] = "Start"
    elif iterator_continue and iterator_id:
        attrs["iterator"] = "Continue"
        attrs["iteratorID"] = iterator_id

    rq = Element("VendorQueryRq", **attrs)
    SubElement(rq, "MaxReturned").text = str(max_returned)

    if from_modified_date and not iterator_continue:
        SubElement(rq, "FromModifiedDate").text = from_modified_date

    for field in [
        "ListID", "TimeCreated", "TimeModified", "EditSequence",
        "Name", "IsActive", "ClassRef",
        "CompanyName", "Salutation", "FirstName", "MiddleName",
        "LastName", "JobTitle", "VendorAddress",
        "Phone", "AltPhone", "Fax", "Email", "Cc",
        "Contact", "AltContact",
        "NameOnCheck", "AccountNumber",
        "Notes", "VendorTypeRef", "TermsRef",
        "CreditLimit", "VendorTaxIdent",
        "IsVendorEligibleFor1099", "OpenBalance", "OpenBalanceDate",
        "BillingRateRef", "ExternalGUID", "CurrencyRef",
        "PrefillAccountRef",
    ]:
        SubElement(rq, "IncludeRetElement").text = field

    return _build_qbxml_envelope(rq)


def build_journal_entry_query(
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 50,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
) -> str:
    attrs = {"requestID": request_id}
    if iterator_start:
        attrs["iterator"] = "Start"
    elif iterator_continue and iterator_id:
        attrs["iterator"] = "Continue"
        attrs["iteratorID"] = iterator_id

    rq = Element("JournalEntryQueryRq", **attrs)
    SubElement(rq, "MaxReturned").text = str(max_returned)

    if from_modified_date and not iterator_continue:
        df = SubElement(rq, "ModifiedDateRangeFilter")
        SubElement(df, "FromModifiedDate").text = from_modified_date

    SubElement(rq, "IncludeLineItems").text = "true"

    return _build_qbxml_envelope(rq)


def build_assembly_bom_query(
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 100,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
) -> str:
    """Build ItemInventoryAssemblyQueryRq — returns assemblies with BOM line items.

    This is a list query, so it uses bare FromModifiedDate (not ModifiedDateRangeFilter).
    """
    attrs = {"requestID": request_id}
    if iterator_start:
        attrs["iterator"] = "Start"
    elif iterator_continue and iterator_id:
        attrs["iterator"] = "Continue"
        attrs["iteratorID"] = iterator_id

    rq = Element("ItemInventoryAssemblyQueryRq", **attrs)
    SubElement(rq, "MaxReturned").text = str(max_returned)

    if from_modified_date and not iterator_continue:
        SubElement(rq, "FromModifiedDate").text = from_modified_date

    return _build_qbxml_envelope(rq)


def build_item_receipt_query(
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 100,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
) -> str:
    """Build ItemReceiptQueryRq — includes line items for lot-level receiving data."""
    attrs = {"requestID": request_id}
    if iterator_start:
        attrs["iterator"] = "Start"
    elif iterator_continue and iterator_id:
        attrs["iterator"] = "Continue"
        attrs["iteratorID"] = iterator_id

    rq = Element("ItemReceiptQueryRq", **attrs)
    SubElement(rq, "MaxReturned").text = str(max_returned)

    if from_modified_date and not iterator_continue:
        df = SubElement(rq, "ModifiedDateRangeFilter")
        SubElement(df, "FromModifiedDate").text = from_modified_date

    # Include line items to get per-item receiving detail
    SubElement(rq, "IncludeLineItems").text = "true"

    return _build_qbxml_envelope(rq)


def build_build_assembly_add(
    assembly_list_id: str,
    quantity: float,
    txn_date: str | None = None,
    ref_number: str | None = None,
    memo: str | None = None,
    mark_pending_if_required: bool = False,
    inventory_site_name: str | None = None,
    request_id: str = "1",
) -> str:
    """
    Build a BuildAssemblyAddRq to record an assembly build in QuickBooks.

    Args:
        assembly_list_id: The ListID of the assembly item to build
        quantity: Number of assemblies to build (the yield)
        txn_date: Date of the build (YYYY-MM-DD). Defaults to today in QB.
        ref_number: Optional reference/batch number
        memo: Optional memo/note
        mark_pending_if_required: If True, emits <MarkPendingIfRequired>true</MarkPendingIfRequired>
            so QB records the build as pending when one or more components are short
            (instead of failing with error 3370). Response <IsPending> tells the caller
            whether QB ended up marking it pending.
        inventory_site_name: Optional inventory site (QB Enterprise only)
        request_id: Request ID for the qbXML envelope

    XML element ordering follows the qbXML 13.0 schema for BuildAssemblyAdd:
    ItemInventoryAssemblyRef, TxnDate, RefNumber, InventorySiteRef, Memo,
    QuantityToBuild, MarkPendingIfRequired. The previous (972dd18) ordering
    placed MarkPendingIfRequired before QuantityToBuild, which caused QB to
    reject the request at the COM/schema layer and the response was lost
    (no qbXML response was returned to the connector).
    """
    rq = Element("BuildAssemblyAddRq", requestID=request_id)
    add = SubElement(rq, "BuildAssemblyAdd")

    # Assembly item reference (required)
    item_ref = SubElement(add, "ItemInventoryAssemblyRef")
    SubElement(item_ref, "ListID").text = assembly_list_id

    if txn_date:
        SubElement(add, "TxnDate").text = txn_date

    if ref_number:
        SubElement(add, "RefNumber").text = ref_number

    if inventory_site_name:
        site_ref = SubElement(add, "InventorySiteRef")
        SubElement(site_ref, "FullName").text = inventory_site_name

    if memo:
        SubElement(add, "Memo").text = memo

    # QuantityToBuild is required
    SubElement(add, "QuantityToBuild").text = str(quantity)

    # MarkPendingIfRequired comes after QuantityToBuild per the qbXML 13.0 schema.
    if mark_pending_if_required:
        SubElement(add, "MarkPendingIfRequired").text = "true"

    return _build_qbxml_envelope(rq)


def build_txn_del(
    txn_del_type: str,
    txn_id: str,
    request_id: str = "1",
) -> str:
    """
    Build a generic TxnDelRq to delete a QuickBooks transaction by TxnID.

    qbXML uses one TxnDelRq for all transaction-type deletions; the
    TxnDelType element discriminates (BuildAssembly, Bill, Check, ...).
    Element ordering per qbXML 13.0 schema: TxnDelType, TxnID.

    Args:
        txn_del_type: One of the qbXML TxnDelType enums (e.g. "BuildAssembly").
        txn_id: The TxnID returned by the original Add response.
        request_id: Request ID for the qbXML envelope.
    """
    rq = Element("TxnDelRq", requestID=request_id)
    SubElement(rq, "TxnDelType").text = txn_del_type
    SubElement(rq, "TxnID").text = txn_id
    return _build_qbxml_envelope(rq)


def build_build_assembly_del(
    txn_id: str,
    request_id: str = "1",
) -> str:
    """
    Delete a previously-recorded BuildAssembly transaction in QuickBooks
    by its TxnID. Thin wrapper over build_txn_del with TxnDelType locked
    to "BuildAssembly" so callers can't pass the wrong type.

    QB will reverse the inventory effect of the build (raw materials
    returned to stock, assembly removed). The TxnID must reference an
    existing BuildAssembly that is not already linked to a downstream
    transaction (e.g. an invoice consuming the assembly).
    """
    return build_txn_del("BuildAssembly", txn_id, request_id=request_id)


def build_company_query(request_id: str = "1") -> str:
    """Retrieve company info (no filter needed)."""
    rq = Element("CompanyQueryRq", requestID=request_id)
    return _build_qbxml_envelope(rq)


def build_host_query(request_id: str = "1") -> str:
    """Retrieve QB host/version info."""
    rq = Element("HostQueryRq", requestID=request_id)
    return _build_qbxml_envelope(rq)


def build_preferences_query(request_id: str = "1") -> str:
    """Retrieve QB preferences."""
    rq = Element("PreferencesQueryRq", requestID=request_id)
    return _build_qbxml_envelope(rq)


# Dispatcher: map entity name -> build function
# For entities without specialized builders, fall back to generic
QUERY_BUILDERS = {
    "accounts": build_account_query,
    "customers": build_customer_query,
    "vendors": build_vendor_query,
    "items": build_item_query,
    "inventory_items": build_generic_query,
    "assembly_bom": build_assembly_bom_query,
    "invoices": build_invoice_query,
    "item_receipts": build_item_receipt_query,
    "journal_entries": build_journal_entry_query,
}


def build_query_for_entity(
    entity_name: str,
    query_rq: str,
    request_id: str = "1",
    from_modified_date: str | None = None,
    max_returned: int = 100,
    iterator_start: bool = False,
    iterator_continue: bool = False,
    iterator_id: str | None = None,
) -> str:
    """
    Dispatch to the appropriate builder for an entity.
    Falls back to generic builder if no specialized one exists.
    """
    builder = QUERY_BUILDERS.get(entity_name)
    if builder:
        if entity_name == "inventory_items":
            query_rq = "ItemInventoryQueryRq"
            return build_generic_query(
                query_rq=query_rq,
                request_id=request_id,
                from_modified_date=from_modified_date,
                max_returned=max_returned,
                iterator_start=iterator_start,
                iterator_continue=iterator_continue,
                iterator_id=iterator_id,
            )
        return builder(
            request_id=request_id,
            from_modified_date=from_modified_date,
            max_returned=max_returned,
            iterator_start=iterator_start,
            iterator_continue=iterator_continue,
            iterator_id=iterator_id,
        )
    else:
        # Look up entity definition to determine if it's a transaction with lines
        from src.qbxml.entities import ENTITY_BY_NAME

        edef = ENTITY_BY_NAME.get(entity_name)
        is_txn = edef.is_transaction if edef else False
        # Transaction queries with line items need IncludeLineItems=true
        has_lines = is_txn and entity_name not in (
            "bill_payments", "receive_payments", "transfers", "time_tracking",
        )

        return build_generic_query(
            query_rq=query_rq,
            request_id=request_id,
            from_modified_date=from_modified_date,
            max_returned=max_returned,
            iterator_start=iterator_start,
            iterator_continue=iterator_continue,
            iterator_id=iterator_id,
            is_transaction=is_txn,
            include_line_items=has_lines,
        )
