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

    # Incremental filter
    if from_modified_date and not iterator_continue:
        # Don't add filter on Continue — must match original request
        if iterator_start:
            # Iterator-capable queries use ModifiedDateRangeFilter wrapper
            date_filter = SubElement(rq, "ModifiedDateRangeFilter")
            SubElement(date_filter, "FromModifiedDate").text = from_modified_date
        else:
            # Simple list queries use direct FromModifiedDate element
            SubElement(rq, "FromModifiedDate").text = from_modified_date

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
        df = SubElement(rq, "ModifiedDateRangeFilter")
        SubElement(df, "FromModifiedDate").text = from_modified_date

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
        df = SubElement(rq, "ModifiedDateRangeFilter")
        SubElement(df, "FromModifiedDate").text = from_modified_date

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
        df = SubElement(rq, "ModifiedDateRangeFilter")
        SubElement(df, "FromModifiedDate").text = from_modified_date

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
    """Build ItemInventoryAssemblyQueryRq — returns assemblies with BOM line items."""
    attrs = {"requestID": request_id}
    if iterator_start:
        attrs["iterator"] = "Start"
    elif iterator_continue and iterator_id:
        attrs["iterator"] = "Continue"
        attrs["iteratorID"] = iterator_id

    rq = Element("ItemInventoryAssemblyQueryRq", **attrs)
    SubElement(rq, "MaxReturned").text = str(max_returned)

    if from_modified_date and not iterator_continue:
        df = SubElement(rq, "ModifiedDateRangeFilter")
        SubElement(df, "FromModifiedDate").text = from_modified_date

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
        return builder(
            request_id=request_id,
            from_modified_date=from_modified_date,
            max_returned=max_returned,
            iterator_start=iterator_start,
            iterator_continue=iterator_continue,
            iterator_id=iterator_id,
        )
    else:
        return build_generic_query(
            query_rq=query_rq,
            request_id=request_id,
            from_modified_date=from_modified_date,
            max_returned=max_returned,
            iterator_start=iterator_start,
            iterator_continue=iterator_continue,
            iterator_id=iterator_id,
        )
