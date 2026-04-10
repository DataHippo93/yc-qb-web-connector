-- =============================================================================
-- Migration 005: Add item_receipts tables to company schemas
-- Captures inventory receiving transactions from QB Desktop
-- =============================================================================

-- natures_storehouse
CREATE TABLE IF NOT EXISTS natures_storehouse.item_receipts (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    vendor_list_id      TEXT,
    vendor_name         TEXT,
    ap_account          TEXT,
    ref_number          TEXT,
    memo                TEXT,
    total_amount        NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS natures_storehouse.item_receipt_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES natures_storehouse.item_receipts(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    expiration_date DATE,
    class_name      TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- adk_fragrance
CREATE TABLE IF NOT EXISTS adk_fragrance.item_receipts (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    vendor_list_id      TEXT,
    vendor_name         TEXT,
    ap_account          TEXT,
    ref_number          TEXT,
    memo                TEXT,
    total_amount        NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS adk_fragrance.item_receipt_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES adk_fragrance.item_receipts(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    expiration_date DATE,
    class_name      TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- yc_works
CREATE TABLE IF NOT EXISTS yc_works.item_receipts (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    vendor_list_id      TEXT,
    vendor_name         TEXT,
    ap_account          TEXT,
    ref_number          TEXT,
    memo                TEXT,
    total_amount        NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS yc_works.item_receipt_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES yc_works.item_receipts(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    expiration_date DATE,
    class_name      TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- maine_and_maine
CREATE TABLE IF NOT EXISTS maine_and_maine.item_receipts (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    vendor_list_id      TEXT,
    vendor_name         TEXT,
    ap_account          TEXT,
    ref_number          TEXT,
    memo                TEXT,
    total_amount        NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS maine_and_maine.item_receipt_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES maine_and_maine.item_receipts(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    expiration_date DATE,
    class_name      TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- yc_consulting
CREATE TABLE IF NOT EXISTS yc_consulting.item_receipts (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    vendor_list_id      TEXT,
    vendor_name         TEXT,
    ap_account          TEXT,
    ref_number          TEXT,
    memo                TEXT,
    total_amount        NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS yc_consulting.item_receipt_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES yc_consulting.item_receipts(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    expiration_date DATE,
    class_name      TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- Also add to the template for future company schemas
-- (This comment documents that 002_company_schema_template.sql should be updated
-- to include item_receipts + item_receipt_lines for any new companies)
