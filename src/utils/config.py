"""
Settings and company configuration.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ============================================================================
# Application Settings (from .env / environment variables)
# ============================================================================

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Supabase
    qb_supabase_url: str = ""
    qb_supabase_anon_key: str = ""
    qb_supabase_service_key: str = ""
    qb_supabase_db_pass: str = ""

    # QBWC auth — must match .qwc file
    qbwc_username: str = "YCConnector"
    qbwc_password: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    # Sync behavior
    sync_lookback_minutes: int = 5
    qbxml_max_returned: int = 100
    sync_interval_minutes: int = 60

    # MakerHub completion webhook (optional). When both are set, the
    # write_queue manager fires a fire-and-forget POST to MAKERHUB_CALLBACK_URL
    # whenever a build_assembly queue row reaches a terminal status, so
    # MakerHub can update its mirror without waiting for the pg_cron poll.
    # Auth: Authorization: Bearer <MAKERHUB_CALLBACK_SECRET>.
    makerhub_callback_url: str = ""
    makerhub_callback_secret: str = ""

    @field_validator("qb_supabase_url", mode="before")
    @classmethod
    def must_have_supabase_url(cls, v: str) -> str:
        if not v:
            raise ValueError("QB_SUPABASE_URL is required")
        return v

    @property
    def supabase_url(self) -> str:
        return self.qb_supabase_url

    @property
    def supabase_service_key(self) -> str:
        return self.qb_supabase_service_key

    @property
    def supabase_anon_key(self) -> str:
        return self.qb_supabase_anon_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# ============================================================================
# Company Configuration (from config/companies.yaml)
# ============================================================================

class CompanyConfig:
    """
    Wraps companies.yaml.
    Each company has an isolated Postgres schema (pg_schema).
    """

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is None:
            # Resolve relative to project root
            root = Path(__file__).parent.parent.parent
            config_path = root / "config" / "companies.yaml"
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        self._companies: dict[str, dict] = raw.get("companies", {})

    def get(self, company_id: str) -> dict[str, Any]:
        """Get full config dict for a company. Raises KeyError if not found."""
        if company_id not in self._companies:
            raise KeyError(f"Unknown company_id: {company_id!r}. "
                           f"Known: {list(self._companies.keys())}")
        return self._companies[company_id]

    def pg_schema(self, company_id: str) -> str:
        """Return the Postgres schema name for this company."""
        return self.get(company_id)["pg_schema"]

    def enabled_entities(self, company_id: str) -> list[str]:
        """Return ordered list of entity names enabled for this company."""
        return self.get(company_id).get("enabled_entities", [])

    def display_name(self, company_id: str) -> str:
        return self.get(company_id).get("display_name", company_id)

    def expected_company_name(self, company_id: str) -> str | None:
        """Expected QB <CompanyName> for this company_id (set in companies.yaml as
        qb_company_name). When configured, the runtime identity check ABORTS any
        session that observes a different name; when None, observation-only mode."""
        v = self.get(company_id).get("qb_company_name")
        if isinstance(v, str) and v.strip():
            return v.strip()
        return None

    def expected_company_file(self, company_id: str) -> str | None:
        """Expected substring (case-insensitive) of the QB file path QBWC reports.
        Set in companies.yaml as qb_company_file."""
        v = self.get(company_id).get("qb_company_file")
        if isinstance(v, str) and v.strip():
            return v.strip()
        return None

    def all_company_ids(self) -> list[str]:
        return list(self._companies.keys())

    def all_pg_schemas(self) -> list[str]:
        return [c["pg_schema"] for c in self._companies.values()]

    def company_id_for_schema(self, pg_schema: str) -> str | None:
        """Reverse lookup: pg_schema -> company_id."""
        for cid, cfg in self._companies.items():
            if cfg.get("pg_schema") == pg_schema:
                return cid
        return None


@lru_cache(maxsize=1)
def get_company_config() -> CompanyConfig:
    return CompanyConfig()


def company_id_from_ticket_or_file(
    qb_file_path: str, company_config: CompanyConfig | None = None
) -> str | None:
    """
    Attempt to identify company from QB file path.
    QB Enterprise typically puts company files in a known location.
    Falls back to None if ambiguous — caller should use QBWC username/app context.
    """
    if company_config is None:
        company_config = get_company_config()

    lower_path = qb_file_path.lower()

    # Simple heuristic: match display name fragments in path
    mappings = {
        "natures": "natures_storehouse",
        "nature": "natures_storehouse",
        "nss": "natures_storehouse",
        "adk": "adk_fragrance",
        "adirondack": "adk_fragrance",
        "fragrance": "adk_fragrance",
    }
    for fragment, company_id in mappings.items():
        if fragment in lower_path:
            return company_id

    return None
