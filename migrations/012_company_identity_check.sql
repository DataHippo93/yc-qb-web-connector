-- =============================================================================
-- Migration 012: Company-identity verification fields
--
-- Why: QBWC's username-based routing (e.g. `YCConnector_ADK` -> adk_fragrance)
-- does NOT verify which QB Desktop company file is actually open at the time
-- the .qwc app fires. If the wrong file is open, QB returns that file's data
-- and the connector silently writes it into the wrong Supabase schema.
--
-- This migration adds two facets per company:
--   observed_*  — what we last saw QB report on session start (ground truth
--                 from CompanyQueryRq), written every time a session starts.
--   expected_*  — what we EXPECT to see (configured in companies.yaml as
--                 `qb_company_name`). When set and the observed value
--                 doesn't match, the session is aborted before any data
--                 syncs. When NULL, observation-only mode (logs the
--                 mismatch but does not fail-close).
-- =============================================================================

ALTER TABLE qb_meta.companies
    ADD COLUMN IF NOT EXISTS observed_company_name TEXT,
    ADD COLUMN IF NOT EXISTS observed_company_file TEXT,
    ADD COLUMN IF NOT EXISTS observed_at           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS expected_company_name TEXT,
    ADD COLUMN IF NOT EXISTS expected_company_file TEXT;

COMMENT ON COLUMN qb_meta.companies.observed_company_name IS
    'Most recent <CompanyName> returned by QB CompanyQueryRq for this company_id.';
COMMENT ON COLUMN qb_meta.companies.observed_company_file IS
    'Most recent strCompanyFileName QBWC supplied at sendRequestXML time.';
COMMENT ON COLUMN qb_meta.companies.expected_company_name IS
    'When non-NULL, sessions for this company_id MUST report this CompanyName from QB or be aborted. Mirror of qb_company_name in companies.yaml — populated automatically when the YAML config is observed-and-matched.';
COMMENT ON COLUMN qb_meta.companies.expected_company_file IS
    'When non-NULL, the QB file path QBWC sends must contain this substring (case-insensitive).';

-- ----------------------------------------------------------------------------
-- Audit log of every identity check (lets you see *every* mismatch attempt,
-- not just the latest one)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS qb_meta.company_identity_log (
    id              BIGSERIAL PRIMARY KEY,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    company_id      TEXT NOT NULL,            -- the company_id from QBWC username
    ticket          TEXT,                     -- session ticket (FK-ish)
    expected_name   TEXT,                     -- expected_company_name at check time
    observed_name   TEXT,                     -- what QB CompanyQueryRq returned
    observed_file   TEXT,                     -- strCompanyFileName from QBWC
    matched         BOOLEAN NOT NULL,
    action_taken    TEXT NOT NULL             -- 'allow' | 'observe_only' | 'abort'
);

CREATE INDEX IF NOT EXISTS idx_company_identity_log_company
    ON qb_meta.company_identity_log (company_id, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_company_identity_log_mismatches
    ON qb_meta.company_identity_log (checked_at DESC)
    WHERE matched = false;

COMMENT ON TABLE qb_meta.company_identity_log IS
    'Append-only history of every CompanyQueryRq verification. Mismatch rows are the smoking gun for cross-schema contamination attempts.';

ALTER TABLE qb_meta.company_identity_log ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'qb_meta' AND tablename = 'company_identity_log' AND policyname = 'service_role_all'
  ) THEN
    EXECUTE 'CREATE POLICY "service_role_all" ON qb_meta.company_identity_log USING (true) WITH CHECK (true)';
  END IF;
END$$;
