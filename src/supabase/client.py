"""
Supabase client — uses service role key for server-side writes.
Per-company data lives in isolated Postgres schemas (natures_storehouse, adk_fragrance).
Shared metadata lives in qb_meta schema.
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from src.utils.config import get_settings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Schema names
META_SCHEMA = "qb_meta"       # sync_state, company_registry, etc.
# Per-company schemas defined in companies.yaml (pg_schema field)


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return cached Supabase client with service role key."""
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_key)
    logger.info("supabase_client_initialized", project_url=settings.supabase_url)
    return client
