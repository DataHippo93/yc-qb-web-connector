-- =============================================================================
-- Migration 007: Write queue for outbound QB operations
--
-- Stores pending write operations (BuildAssemblyAdd, etc.) that get sent
-- to QuickBooks during the next QBWC sync cycle via sendRequestXML.
-- =============================================================================

CREATE TABLE IF NOT EXISTS qb_meta.write_queue (
    id              BIGSERIAL PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES qb_meta.companies(company_id),
    operation       TEXT NOT NULL,          -- e.g. 'build_assembly'
    payload         JSONB NOT NULL,         -- operation-specific data
    status          TEXT NOT NULL DEFAULT 'pending',
    -- Lifecycle timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at      TIMESTAMPTZ,           -- when picked up by a QBWC session
    completed_at    TIMESTAMPTZ,
    -- Result tracking
    qb_txn_id       TEXT,                  -- TxnID returned by QB on success
    qb_request_id   TEXT,                  -- request ID used in the qbXML
    error_message   TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    -- Caller reference (e.g. MakerHub batch ID)
    external_id     TEXT,
    external_source TEXT,                  -- e.g. 'makerhub'

    CONSTRAINT chk_write_status CHECK (
        status IN ('pending', 'claimed', 'sent', 'completed', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_write_queue_pending
    ON qb_meta.write_queue (company_id, status)
    WHERE status IN ('pending', 'claimed', 'sent');

CREATE INDEX IF NOT EXISTS idx_write_queue_external
    ON qb_meta.write_queue (external_source, external_id)
    WHERE external_id IS NOT NULL;

COMMENT ON TABLE qb_meta.write_queue IS
    'Outbound write queue — pending Add/Mod operations sent to QB via QBWC.';

-- RLS
ALTER TABLE qb_meta.write_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON qb_meta.write_queue
    USING (true) WITH CHECK (true);

-- Add active_write_id column to sessions table for write-back tracking
ALTER TABLE qb_meta.sessions ADD COLUMN IF NOT EXISTS active_write_id BIGINT;
