"""Tests for BuildAssembly write-back: builder, parser, and write queue."""
from __future__ import annotations

import pytest
from lxml import etree

from src.qbxml.builders import build_build_assembly_add
from src.qbxml.parsers import parse_write_response, WriteResponse


def parse_xml(xml_string: str) -> etree._Element:
    """Parse XML, stripping the qbxml processing instruction."""
    lines = [l for l in xml_string.splitlines() if not l.startswith("<?")]
    return etree.fromstring("\n".join(lines).encode())


# ============================================================================
# Builder tests
# ============================================================================


class TestBuildAssemblyAddBuilder:
    def test_basic_build(self):
        xml = build_build_assembly_add(
            assembly_list_id="80000042-1234567890",
            quantity=10.0,
        )
        root = parse_xml(xml)
        rq = root.find(".//BuildAssemblyAddRq")
        assert rq is not None
        assert rq.get("requestID") == "1"

        add = rq.find("BuildAssemblyAdd")
        assert add is not None

        item_ref = add.find("ItemInventoryAssemblyRef/ListID")
        assert item_ref is not None
        assert item_ref.text == "80000042-1234567890"

        qty = add.find("QuantityToBuild")
        assert qty is not None
        assert qty.text == "10.0"

    def test_with_all_fields(self):
        xml = build_build_assembly_add(
            assembly_list_id="80000042-1234567890",
            quantity=5.5,
            txn_date="2026-04-14",
            ref_number="BATCH-001",
            memo="MakerHub batch #123",
            inventory_site_name="Main Warehouse",
            request_id="W42",
        )
        root = parse_xml(xml)
        rq = root.find(".//BuildAssemblyAddRq")
        assert rq.get("requestID") == "W42"

        add = rq.find("BuildAssemblyAdd")
        assert add.find("TxnDate").text == "2026-04-14"
        assert add.find("RefNumber").text == "BATCH-001"
        assert add.find("Memo").text == "MakerHub batch #123"
        assert add.find("QuantityToBuild").text == "5.5"
        assert add.find("InventorySiteRef/FullName").text == "Main Warehouse"

    def test_no_optional_fields(self):
        xml = build_build_assembly_add(
            assembly_list_id="80000042-1234567890",
            quantity=1,
        )
        root = parse_xml(xml)
        add = root.find(".//BuildAssemblyAdd")
        assert add.find("TxnDate") is None
        assert add.find("RefNumber") is None
        assert add.find("Memo") is None
        assert add.find("InventorySiteRef") is None

    def test_qbxml_envelope(self):
        xml = build_build_assembly_add(
            assembly_list_id="80000042-1234567890",
            quantity=1,
        )
        assert '<?xml version="1.0"' in xml
        assert '<?qbxml version="13.0"?>' in xml

    def test_element_order(self):
        """QB requires elements in a specific order per the SDK spec."""
        xml = build_build_assembly_add(
            assembly_list_id="80000042-1234567890",
            quantity=10,
            txn_date="2026-01-01",
            ref_number="REF-1",
            memo="test",
        )
        root = parse_xml(xml)
        add = root.find(".//BuildAssemblyAdd")
        tags = [child.tag for child in add]
        # ItemInventoryAssemblyRef must come first, QuantityToBuild after optional fields
        assert tags.index("ItemInventoryAssemblyRef") < tags.index("QuantityToBuild")
        assert tags.index("TxnDate") < tags.index("QuantityToBuild")
        assert tags.index("RefNumber") < tags.index("QuantityToBuild")
        assert tags.index("Memo") < tags.index("QuantityToBuild")


# ============================================================================
# Response parser tests
# ============================================================================

BUILD_ASSEMBLY_SUCCESS_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="13.0"?>
<QBXML>
  <QBXMLMsgsRs>
    <BuildAssemblyAddRs requestID="W42" statusCode="0" statusMessage="Status OK">
      <BuildAssemblyRet>
        <TxnID>TXN-BUILD-001</TxnID>
        <TimeCreated>2026-04-14T10:00:00</TimeCreated>
        <TimeModified>2026-04-14T10:00:00</TimeModified>
        <EditSequence>1234567890</EditSequence>
        <TxnDate>2026-04-14</TxnDate>
        <RefNumber>BATCH-001</RefNumber>
        <Memo>MakerHub batch #123</Memo>
        <ItemInventoryAssemblyRef>
          <ListID>80000042-1234567890</ListID>
          <FullName>Lavender Body Lotion 8oz</FullName>
        </ItemInventoryAssemblyRef>
        <QuantityToBuild>10</QuantityToBuild>
        <QuantityCanBuild>25</QuantityCanBuild>
        <QuantityOnHand>35</QuantityOnHand>
      </BuildAssemblyRet>
    </BuildAssemblyAddRs>
  </QBXMLMsgsRs>
</QBXML>'''

BUILD_ASSEMBLY_ERROR_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="13.0"?>
<QBXML>
  <QBXMLMsgsRs>
    <BuildAssemblyAddRs requestID="W42" statusCode="3180"
        statusMessage="There was an error when saving a BuildAssembly transaction.">
    </BuildAssemblyAddRs>
  </QBXMLMsgsRs>
</QBXML>'''

BUILD_ASSEMBLY_INSUFFICIENT_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<?qbxml version="13.0"?>
<QBXML>
  <QBXMLMsgsRs>
    <BuildAssemblyAddRs requestID="W42" statusCode="3180"
        statusMessage="You do not have sufficient quantities to build this assembly.">
    </BuildAssemblyAddRs>
  </QBXMLMsgsRs>
</QBXML>'''


class TestWriteResponseParser:
    def test_success_response(self):
        result = parse_write_response(BUILD_ASSEMBLY_SUCCESS_RESPONSE)
        assert result.success is True
        assert result.status_code == 0
        assert result.txn_id == "TXN-BUILD-001"
        assert result.txn_number == "BATCH-001"
        assert result.edit_sequence == "1234567890"
        assert result.request_id == "W42"

    def test_error_response(self):
        result = parse_write_response(BUILD_ASSEMBLY_ERROR_RESPONSE)
        assert result.success is False
        assert result.status_code == 3180
        assert "error" in result.status_message.lower()
        assert result.txn_id is None

    def test_insufficient_qty_response(self):
        result = parse_write_response(BUILD_ASSEMBLY_INSUFFICIENT_RESPONSE)
        assert result.success is False
        assert result.status_code == 3180
        assert "sufficient quantities" in result.status_message

    def test_empty_response(self):
        result = parse_write_response("")
        assert result.success is False
        assert result.status_code == -1

    def test_malformed_xml(self):
        result = parse_write_response("<broken>xml")
        assert result.success is False
        assert result.status_code == -1

    def test_no_msgs_rs(self):
        result = parse_write_response(
            '<?xml version="1.0"?><?qbxml version="13.0"?><QBXML></QBXML>'
        )
        assert result.success is False
        assert result.status_code == -1

    def test_no_add_rs_element(self):
        result = parse_write_response(
            '<?xml version="1.0"?><?qbxml version="13.0"?>'
            "<QBXML><QBXMLMsgsRs></QBXMLMsgsRs></QBXML>"
        )
        assert result.success is False


# ============================================================================
# WriteQueueManager tests (unit-level, no DB)
# ============================================================================

class TestWriteQueueBuildRequestXml:
    """Test build_request_xml without DB dependencies."""

    def test_build_assembly_xml(self):
        from src.sync.write_queue import WriteQueueManager

        # We can't instantiate with a real client, but we can test
        # the static method behavior by calling build_request_xml
        # with a mock queue item
        wq = WriteQueueManager.__new__(WriteQueueManager)

        item = {
            "id": 42,
            "operation": "build_assembly",
            "payload": {
                "assembly_list_id": "80000042-1234567890",
                "quantity": 10.0,
                "txn_date": "2026-04-14",
                "ref_number": "BATCH-001",
                "memo": "Test memo",
            },
        }

        xml = wq.build_request_xml(item, request_id="W42")
        assert xml is not None
        root = parse_xml(xml)
        rq = root.find(".//BuildAssemblyAddRq")
        assert rq is not None
        assert rq.get("requestID") == "W42"

        add = rq.find("BuildAssemblyAdd")
        assert add.find("ItemInventoryAssemblyRef/ListID").text == "80000042-1234567890"
        assert add.find("QuantityToBuild").text == "10.0"
        assert add.find("TxnDate").text == "2026-04-14"
        assert add.find("RefNumber").text == "BATCH-001"
        assert add.find("Memo").text == "Test memo"

    def test_unknown_operation(self):
        from src.sync.write_queue import WriteQueueManager

        wq = WriteQueueManager.__new__(WriteQueueManager)
        item = {"id": 1, "operation": "unknown_op", "payload": {}}
        xml = wq.build_request_xml(item)
        assert xml is None

    def test_minimal_payload(self):
        from src.sync.write_queue import WriteQueueManager

        wq = WriteQueueManager.__new__(WriteQueueManager)
        item = {
            "id": 1,
            "operation": "build_assembly",
            "payload": {
                "assembly_list_id": "LISTID-1",
                "quantity": 1,
            },
        }

        xml = wq.build_request_xml(item)
        assert xml is not None
        root = parse_xml(xml)
        add = root.find(".//BuildAssemblyAdd")
        assert add.find("TxnDate") is None
        assert add.find("RefNumber") is None
        assert add.find("Memo") is None


# ============================================================================
# Coordinator write integration tests (unit-level)
# ============================================================================

class TestCoordinatorWriteRouting:
    """Test that coordinator correctly routes write responses."""

    def test_handle_response_routes_to_write_handler(self):
        """When active_write_id is set, response should go to write handler."""
        from unittest.mock import MagicMock, patch
        from src.sync.coordinator import SyncCoordinator
        from src.soap.session import SyncSession

        coordinator = SyncCoordinator.__new__(SyncCoordinator)
        coordinator._write_queue = MagicMock()
        coordinator._state = MagicMock()
        coordinator._upserter = MagicMock()
        coordinator._settings = MagicMock()
        coordinator._company_cfg = MagicMock()

        session = SyncSession(
            ticket="test",
            company_id="natures_storehouse",
            company_file="",
            qbxml_version=(13, 0),
        )
        session.active_write_id = 42

        # Should call _handle_write_response, not the normal path
        with patch.object(coordinator, "_handle_write_response", return_value=50) as mock_write:
            result = coordinator.handle_response(session, BUILD_ASSEMBLY_SUCCESS_RESPONSE)
            mock_write.assert_called_once_with(session, BUILD_ASSEMBLY_SUCCESS_RESPONSE)
            assert result == 50

    def test_handle_write_response_success(self):
        """Successful write response marks queue item completed."""
        from unittest.mock import MagicMock
        from src.sync.coordinator import SyncCoordinator
        from src.soap.session import SyncSession

        coordinator = SyncCoordinator.__new__(SyncCoordinator)
        coordinator._write_queue = MagicMock()

        session = SyncSession(
            ticket="test",
            company_id="natures_storehouse",
            company_file="",
            qbxml_version=(13, 0),
        )
        session.active_write_id = 42

        coordinator._handle_write_response(session, BUILD_ASSEMBLY_SUCCESS_RESPONSE)

        coordinator._write_queue.mark_completed.assert_called_once_with(
            42, txn_id="TXN-BUILD-001"
        )
        assert session.active_write_id is None

    def test_handle_write_response_failure(self):
        """Failed write response marks queue item failed."""
        from unittest.mock import MagicMock
        from src.sync.coordinator import SyncCoordinator
        from src.soap.session import SyncSession

        coordinator = SyncCoordinator.__new__(SyncCoordinator)
        coordinator._write_queue = MagicMock()

        session = SyncSession(
            ticket="test",
            company_id="natures_storehouse",
            company_file="",
            qbxml_version=(13, 0),
        )
        session.active_write_id = 42

        coordinator._handle_write_response(session, BUILD_ASSEMBLY_ERROR_RESPONSE)

        coordinator._write_queue.mark_failed.assert_called_once()
        call_args = coordinator._write_queue.mark_failed.call_args
        assert call_args[0][0] == 42  # queue_id
        assert "3180" in call_args[0][1]  # error message contains status code
        assert session.active_write_id is None

    def test_no_write_during_iteration(self):
        """Write queue should NOT be checked while iterating through a read query."""
        from unittest.mock import MagicMock, patch
        from src.sync.coordinator import SyncCoordinator
        from src.soap.session import SyncSession, SyncTask

        coordinator = SyncCoordinator.__new__(SyncCoordinator)
        coordinator._write_queue = MagicMock()
        coordinator._state = MagicMock()
        coordinator._upserter = MagicMock()
        coordinator._settings = MagicMock()
        coordinator._company_cfg = MagicMock()
        coordinator._company_cfg.get.return_value = {"max_returned": 100}

        session = SyncSession(
            ticket="test",
            company_id="natures_storehouse",
            company_file="",
            qbxml_version=(13, 0),
        )
        # Simulate mid-iteration
        task = SyncTask(
            entity_type="invoices",
            query_name="InvoiceQueryRq",
            is_incremental=False,
            from_date=None,
            iterator_id="{ABC123}",  # Mid-iteration
            iterator_remaining=50,
        )
        session.task_queue = [task]
        session.current_task_index = 0

        with patch("src.sync.coordinator.get_entity") as mock_get_entity, \
             patch("src.sync.coordinator.build_query_for_entity", return_value="<xml>"):
            mock_get_entity.return_value = MagicMock(supports_iterator=True)
            coordinator.get_next_request(session)

        # claim_next should NOT have been called during iteration
        coordinator._write_queue.claim_next.assert_not_called()
