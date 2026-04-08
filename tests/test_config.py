"""Tests for config loading."""
from __future__ import annotations

import pytest
from pathlib import Path

from src.utils.config import CompanyConfig, company_id_from_ticket_or_file


class TestCompanyConfig:
    @pytest.fixture
    def config(self):
        return CompanyConfig()

    def test_loads_both_companies(self, config):
        ids = config.all_company_ids()
        assert "natures_storehouse" in ids
        assert "adk_fragrance" in ids

    def test_pg_schemas(self, config):
        assert config.pg_schema("natures_storehouse") == "natures_storehouse"
        assert config.pg_schema("adk_fragrance") == "adk_fragrance"

    def test_all_pg_schemas(self, config):
        schemas = config.all_pg_schemas()
        assert "natures_storehouse" in schemas
        assert "adk_fragrance" in schemas

    def test_display_names(self, config):
        assert "Nature" in config.display_name("natures_storehouse")
        assert "Adirondack" in config.display_name("adk_fragrance")

    def test_enabled_entities(self, config):
        entities = config.enabled_entities("natures_storehouse")
        assert "customers" in entities
        assert "invoices" in entities
        assert "accounts" in entities

    def test_sync_order(self, config):
        """Accounts should be synced before invoices."""
        from src.qbxml.entities import get_entities_for_company
        enabled = config.enabled_entities("natures_storehouse")
        ordered = get_entities_for_company(enabled)
        names = [e.name for e in ordered]
        assert names.index("accounts") < names.index("customers")
        assert names.index("customers") < names.index("invoices")

    def test_unknown_company_raises(self, config):
        with pytest.raises(KeyError):
            config.get("nonexistent_company")

    def test_reverse_lookup(self, config):
        cid = config.company_id_for_schema("natures_storehouse")
        assert cid == "natures_storehouse"

        cid2 = config.company_id_for_schema("adk_fragrance")
        assert cid2 == "adk_fragrance"

        assert config.company_id_for_schema("does_not_exist") is None


class TestCompanyDetection:
    def test_detect_natures_from_path(self):
        config = CompanyConfig()
        cid = company_id_from_ticket_or_file(
            r"C:\Users\Public\Documents\Intuit\QuickBooks\Company Files\NaturesStorehouse.qbw",
            config,
        )
        assert cid == "natures_storehouse"

    def test_detect_adk_from_path(self):
        config = CompanyConfig()
        cid = company_id_from_ticket_or_file(
            r"C:\QB\ADK Fragrance Farm.qbw",
            config,
        )
        assert cid == "adk_fragrance"

    def test_unknown_path_returns_none(self):
        config = CompanyConfig()
        cid = company_id_from_ticket_or_file(r"C:\QB\SomeOtherCompany.qbw", config)
        assert cid is None
