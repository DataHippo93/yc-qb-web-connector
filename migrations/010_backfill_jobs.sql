-- =============================================================================
-- Migration 010: Backfill jobs queue
--
-- Purpose: allow operators to request a re-sync of one entity for a SPECIFIC
-- date window (e.g., re-pull invoices modified between 2024-01-01 and
-- 2024-04-30) without resetting the whole entity to a full re-sync.
--
-- Used by:
--   POST /backfill/{company}/{entity}  body: { from_date, to_date, filter_type }
--
-- Lifecycle: pending -> claimed -> running -> done | error
--
-- The coordinator inserts a backfill task at the FRONT of the per-session
-- task queue when it sees pending backfill jobs for the company. The
-- backfill task uses ModifiedDateRangeFilter (or TxnDateRangeFilter) with
-- BOTH FromDate and ToDate set, instead of just the bare FromModifiedDate
-- the regular incremental sync uses.
-- =============================================================================

CREATE TABLE IF NOT EXISTS qb_meta.backfill_jobs (
    id              BIGSERIAL PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES qb_meta.companies(company_id),
    entity_type     TEXT NOT NULL,            -- e.g. invoices, bills
    -- Window: pull records whose <filter_field> falls in [from_date, to_date)
    from_date       TIMESTAMPTZ NOT NULL,
    to_date         TIMESTAMPTZ NOT NULL,
    -- 'modified' = filter on TimeModified (uses ModifiedDateRangeFilter)
    -- 'txn'      = filter on TxnDate      (uses TxnDateRangeFilter)
    filter_type     TEXT NOT NULL DEFAULT 'modified',
    -- Lifecycle
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|claimed|running|done|error
    requested_by    TEXT,                              -- caller / operator note
    reason          TEXT,                              -- why this backfill was requested
    -- Execution metadata
    claimed_at      TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    records_synced  INTEGER DEFAULT 0,
    error_message   TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_backfill_status     CHECK (status IN ('pending','claimed','running','done','error')),
    CONSTRAINT chk_backfill_filter     CHECK (filter_type IN ('modified','txn')),
    CONSTRAINT chk_backfill_window     CHECK (to_date > from_date)
);

CREATE INDEX IF NOT EXISTS idx_backfill_jobs_pending
    ON qb_meta.backfill_jobs (company_id, status, created_at)
    WHERE status IN ('pending', 'claimed');

CREATE INDEX IF NOT EXISTS idx_backfill_jobs_entity
    ON qb_meta.backfill_jobs (company_id, entity_type, status);

COMMENT ON TABLE qb_meta.backfill_jobs IS
    'On-demand date-windowed re-sync queue. Each row asks the connector to '
    're-pull one entity for a specific window on the next QBWC cycle. Useful '
    'for repairing data gaps without forcing a full all-time re-sync.';

ALTER TABLE qb_meta.backfill_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON qb_meta.backfill_jobs
    USING (true) WITH CHECK (true);
