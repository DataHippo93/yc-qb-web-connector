-- =============================================================================
-- Migration 001: qb_meta schema
-- Shared metadata: company registry, sync state, sync log.
-- Run once against the Supabase project.
-- =============================================================================

-- Create the metadata schema
CREATE SCHEMA IF NOT EXISTS qb_meta;

-- ============================================================================
-- Company registry
-- ============================================================================
CREATE TABLE IF NOT EXISTS qb_meta.companies (
    company_id      TEXT PRIMARY KEY,
    pg_schema       TEXT NOT NULL UNIQUE,     -- e.g. natures_storehouse
    display_name    TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE qb_meta.companies IS
    'Registry of QuickBooks companies. Each company has an isolated Postgres schema.';

-- Seed known companies
INSERT INTO qb_meta.companies (company_id, pg_schema, display_name)
VALUES
    ('natures_storehouse', 'natures_storehouse', 'Nature''s Storehouse'),
    ('adk_fragrance',      'adk_fragrance',      'Adirondack Fragrance Farm'),
    ('yc_works',           'yc_works',           'YC Works LLC')
ON CONFLICT (company_id) DO UPDATE
    SET pg_schema    = EXCLUDED.pg_schema,
        display_name = EXCLUDED.display_name,
        updated_at   = NOW();

-- ============================================================================
-- Sync state
-- ============================================================================
CREATE TABLE IF NOT EXISTS qb_meta.sync_state (
    company_id          TEXT NOT NULL REFERENCES qb_meta.companies(company_id),
    entity_type         TEXT NOT NULL,            -- e.g. customers, invoices
    status              TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|error
    last_synced_at      TIMESTAMPTZ,              -- end of last successful sync
    last_full_sync_at   TIMESTAMPTZ,              -- end of last full (non-incremental) sync
    records_synced      INTEGER DEFAULT 0,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_sync_state PRIMARY KEY (company_id, entity_type),
    CONSTRAINT chk_status CHECK (status IN ('pending','running','done','error'))
);

CREATE INDEX IF NOT EXISTS idx_sync_state_company
    ON qb_meta.sync_state (company_id);

CREATE INDEX IF NOT EXISTS idx_sync_state_status
    ON qb_meta.sync_state (status)
    WHERE status IN ('running', 'error');

COMMENT ON TABLE qb_meta.sync_state IS
    'Tracks last successful sync per company+entity. Drives incremental vs full sync decision.';

-- ============================================================================
-- Sync log (history of every sync run)
-- ============================================================================
CREATE TABLE IF NOT EXISTS qb_meta.sync_log (
    id              BIGSERIAL PRIMARY KEY,
    company_id      TEXT NOT NULL,
    entity_type     TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    records_synced  INTEGER DEFAULT 0,
    is_full_sync    BOOLEAN DEFAULT false,
    status          TEXT NOT NULL DEFAULT 'running',  -- running|done|error
    error_message   TEXT,
    ticket          TEXT                             -- QBWC session ticket
);

CREATE INDEX IF NOT EXISTS idx_sync_log_company_time
    ON qb_meta.sync_log (company_id, started_at DESC);

COMMENT ON TABLE qb_meta.sync_log IS
    'Append-only history of every sync run. Useful for auditing and troubleshooting.';

-- ============================================================================
-- Row-level security (service role bypasses RLS)
-- ============================================================================
ALTER TABLE qb_meta.companies   ENABLE ROW LEVEL SECURITY;
ALTER TABLE qb_meta.sync_state  ENABLE ROW LEVEL SECURITY;
ALTER TABLE qb_meta.sync_log    ENABLE ROW LEVEL SECURITY;

-- Service role policy (full access for the connector)
CREATE POLICY "service_role_all" ON qb_meta.companies
    USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON qb_meta.sync_state
    USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON qb_meta.sync_log
    USING (true) WITH CHECK (true);
