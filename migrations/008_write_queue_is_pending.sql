-- =============================================================================
-- Migration 008: Track pending-build outcome on qb_meta.write_queue
--
-- When a BuildAssemblyAdd request is sent with <MarkPendingIfRequired>true</..>,
-- QB records the build as pending (no stock is deducted) if one or more
-- components are short. The response carries an <IsPending>true</IsPending>
-- element so the caller (e.g. MakerHub) can surface this to the operator
-- and prompt them to finalize the build later, once inventory is restocked.
--
-- This migration adds a boolean column to persist that outcome alongside
-- qb_txn_id. NULL = unknown/not applicable (non-build-assembly ops or rows
-- written before this column existed).
-- =============================================================================

ALTER TABLE qb_meta.write_queue
    ADD COLUMN IF NOT EXISTS is_pending BOOLEAN;

COMMENT ON COLUMN qb_meta.write_queue.is_pending IS
    'For BuildAssembly ops: QB-reported <IsPending> flag. True = build was '
    'recorded as pending because components were short (MarkPendingIfRequired '
    'path). NULL = not applicable or not yet recorded.';
