-- =============================================================================
-- Migration 009: Auto-cascading build assembly support
--
-- Adds the cascade dispatch primitive on qb_meta.write_queue so MakerHub's
-- planner can chain build operations (intermediate Y must complete before
-- final X enters the dispatcher's pending queue). Self-orchestrating: a
-- trigger flips child rows from cascade_waiting → pending the moment their
-- parent reaches status='completed', no cron job required.
--
-- All three changes are idempotent and additive — existing single-build
-- flows (status in {pending, claimed, sent, completed, failed}) are
-- unaffected.
-- =============================================================================

-- 1. New column: dependency edge between write_queue rows.
ALTER TABLE qb_meta.write_queue
    ADD COLUMN IF NOT EXISTS depends_on_write_id BIGINT
        REFERENCES qb_meta.write_queue(id);

CREATE INDEX IF NOT EXISTS idx_write_queue_depends_on
    ON qb_meta.write_queue(depends_on_write_id)
    WHERE depends_on_write_id IS NOT NULL;

COMMENT ON COLUMN qb_meta.write_queue.depends_on_write_id IS
    'When set, this row participates in a cascade and depends on the '
    'referenced row''s completion. The dispatcher must NOT claim this row '
    'until the depended-upon row has completed_at IS NOT NULL. Self-managed '
    'via the release_cascade_dependents trigger below; no application-side '
    'logic needed beyond filtering status=pending in claim_next().';

-- 2. Allow the new 'cascade_waiting' status value. Cascade children sit at
-- this status until their parent completes; the dispatcher's claim_next()
-- already filters status='pending', so cascade_waiting rows are naturally
-- skipped without any application-side change.
ALTER TABLE qb_meta.write_queue
    DROP CONSTRAINT IF EXISTS chk_write_status;

ALTER TABLE qb_meta.write_queue
    ADD CONSTRAINT chk_write_status CHECK (
        status IN ('pending', 'claimed', 'sent', 'completed', 'failed', 'cascade_waiting')
    );

-- 3. Trigger: when a row reaches status='completed', release any cascade
-- children whose depends_on_write_id points at it. Flipping their status
-- from 'cascade_waiting' to 'pending' makes them eligible for the
-- dispatcher's next claim_next() call. Resetting attempts=0 means a
-- cascade child gets the full retry budget the dispatcher would normally
-- allow a fresh row.
CREATE OR REPLACE FUNCTION qb_meta.release_cascade_dependents()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'completed' AND (OLD.status IS DISTINCT FROM 'completed') THEN
        UPDATE qb_meta.write_queue
           SET status = 'pending',
               attempts = 0
         WHERE depends_on_write_id = NEW.id
           AND status = 'cascade_waiting';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS write_queue_release_dependents ON qb_meta.write_queue;
CREATE TRIGGER write_queue_release_dependents
AFTER UPDATE OF status ON qb_meta.write_queue
FOR EACH ROW
EXECUTE FUNCTION qb_meta.release_cascade_dependents();

COMMENT ON FUNCTION qb_meta.release_cascade_dependents() IS
    'Auto-cascading build assembly support: when a parent write_queue row '
    'reaches status=completed, flip any cascade_waiting children to pending '
    'so the dispatcher can claim them on the next QBWC poll. Added with '
    'migration 009.';
