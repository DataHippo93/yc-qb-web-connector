-- =============================================================================
-- Migration 002: Per-company schema template
--
-- Run this TWICE, substituting the schema name each time:
--   \set schema natures_storehouse
--   \i migrations/002_company_schema_template.sql
--
--   \set schema adk_fragrance
--   \i migrations/002_company_schema_template.sql
--
-- Or use the bootstrap script:
--   python scripts/bootstrap_schemas.py
--
-- All tables follow the same structure in every company schema.
-- No company_id column — isolation is provided by the schema itself.
-- =============================================================================

-- This file uses :schema as a substitution variable.
-- When running via psql: \set schema natures_storehouse
-- When running via bootstrap script, the script does the substitution.

-- ============================================================================
-- Reference / List objects
-- ============================================================================

CREATE TABLE IF NOT EXISTS :schema.accounts (
    qb_list_id              TEXT PRIMARY KEY,
    name                    TEXT,
    full_name               TEXT,
    is_active               BOOLEAN,
    parent_list_id          TEXT,
    sublevel                TEXT,
    account_type            TEXT,
    special_account_type    TEXT,
    account_number          TEXT,
    bank_number             TEXT,
    description             TEXT,
    balance                 NUMERIC(15,2),
    total_balance           NUMERIC(15,2),
    cash_flow_classification TEXT,
    time_created            TIMESTAMPTZ,
    time_modified           TIMESTAMPTZ,
    edit_sequence           TEXT,
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_accounts_full_name ON :schema.accounts (full_name);
CREATE INDEX IF NOT EXISTS idx_accounts_type ON :schema.accounts (account_type);

CREATE TABLE IF NOT EXISTS :schema.classes (
    qb_list_id      TEXT PRIMARY KEY,
    name            TEXT,
    full_name       TEXT,
    is_active       BOOLEAN,
    parent_list_id  TEXT,
    sublevel        TEXT,
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.sales_tax_codes (
    qb_list_id      TEXT PRIMARY KEY,
    name            TEXT,
    is_active       BOOLEAN,
    is_taxable      BOOLEAN,
    description     TEXT,
    item_purchase_tax_ref TEXT,
    item_sales_tax_ref    TEXT,
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.payment_methods (
    qb_list_id          TEXT PRIMARY KEY,
    name                TEXT,
    is_active           BOOLEAN,
    payment_method_type TEXT,
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.ship_methods (
    qb_list_id    TEXT PRIMARY KEY,
    name          TEXT,
    is_active     BOOLEAN,
    time_created  TIMESTAMPTZ,
    time_modified TIMESTAMPTZ,
    edit_sequence TEXT,
    synced_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.terms (
    qb_list_id          TEXT PRIMARY KEY,
    name                TEXT,
    is_active           BOOLEAN,
    is_standard_terms   BOOLEAN,
    std_due_days        INTEGER,
    std_discount_days   INTEGER,
    discount_pct        NUMERIC(6,3),
    day_of_month_due    INTEGER,
    due_next_month_days INTEGER,
    discount_day_of_month INTEGER,
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Customers
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.customers (
    qb_list_id              TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    full_name               TEXT,
    is_active               BOOLEAN,
    parent_list_id          TEXT,
    sublevel                INTEGER,
    company_name            TEXT,
    salutation              TEXT,
    first_name              TEXT,
    middle_name             TEXT,
    last_name               TEXT,
    suffix                  TEXT,
    job_title               TEXT,
    bill_address            JSONB,
    ship_address            JSONB,
    phone                   TEXT,
    alt_phone               TEXT,
    fax                     TEXT,
    email                   TEXT,
    cc                      TEXT,
    contact                 TEXT,
    alt_contact             TEXT,
    customer_type           TEXT,
    terms                   TEXT,
    sales_rep               TEXT,
    open_balance            NUMERIC(15,2),
    total_balance           NUMERIC(15,2),
    sales_tax_code          TEXT,
    item_sales_tax          TEXT,
    resale_number           TEXT,
    account_number          TEXT,
    credit_limit            NUMERIC(15,2),
    preferred_payment_method TEXT,
    job_status              TEXT,
    job_start_date          DATE,
    job_projected_end_date  DATE,
    job_end_date            DATE,
    job_desc                TEXT,
    job_type                TEXT,
    notes                   TEXT,
    is_statement_with_parent BOOLEAN,
    preferred_delivery_method TEXT,
    price_level             TEXT,
    external_guid           TEXT,
    time_created            TIMESTAMPTZ,
    time_modified           TIMESTAMPTZ,
    edit_sequence           TEXT,
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_customers_name     ON :schema.customers (name);
CREATE INDEX IF NOT EXISTS idx_customers_email    ON :schema.customers (email);
CREATE INDEX IF NOT EXISTS idx_customers_modified ON :schema.customers (time_modified DESC);

-- ============================================================================
-- Vendors
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.vendors (
    qb_list_id              TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    is_active               BOOLEAN,
    company_name            TEXT,
    salutation              TEXT,
    first_name              TEXT,
    middle_name             TEXT,
    last_name               TEXT,
    job_title               TEXT,
    vendor_address          JSONB,
    phone                   TEXT,
    alt_phone               TEXT,
    fax                     TEXT,
    email                   TEXT,
    contact                 TEXT,
    alt_contact             TEXT,
    name_on_check           TEXT,
    account_number          TEXT,
    notes                   TEXT,
    vendor_type             TEXT,
    terms                   TEXT,
    credit_limit            NUMERIC(15,2),
    vendor_tax_ident        TEXT,
    is_vendor_eligible_for_1099 BOOLEAN,
    open_balance            NUMERIC(15,2),
    external_guid           TEXT,
    time_created            TIMESTAMPTZ,
    time_modified           TIMESTAMPTZ,
    edit_sequence           TEXT,
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vendors_name     ON :schema.vendors (name);
CREATE INDEX IF NOT EXISTS idx_vendors_modified ON :schema.vendors (time_modified DESC);

-- ============================================================================
-- Employees
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.employees (
    qb_list_id      TEXT PRIMARY KEY,
    name            TEXT,
    is_active       BOOLEAN,
    salutation      TEXT,
    first_name      TEXT,
    middle_name     TEXT,
    last_name       TEXT,
    suffix          TEXT,
    job_title       TEXT,
    address         JSONB,
    phone           TEXT,
    mobile          TEXT,
    email           TEXT,
    employee_type   TEXT,
    gender          TEXT,
    hired_date      DATE,
    released_date   DATE,
    external_guid   TEXT,
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Items
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.items (
    qb_list_id              TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    full_name               TEXT,
    item_type               TEXT NOT NULL,   -- Service|Inventory|NonInventory|etc.
    is_active               BOOLEAN,
    parent_list_id          TEXT,
    sublevel                INTEGER,
    manufacturer_part_number TEXT,
    unit_of_measure_set     TEXT,
    sales_desc              TEXT,
    sales_price             NUMERIC(15,4),
    income_account          TEXT,
    purchase_desc           TEXT,
    purchase_cost           NUMERIC(15,4),
    cogs_account            TEXT,
    asset_account           TEXT,
    preferred_vendor        TEXT,
    sales_tax_code          TEXT,
    quantity_on_hand        NUMERIC(15,4),
    avg_cost                NUMERIC(15,4),
    quantity_on_order       NUMERIC(15,4),
    quantity_on_sales_order NUMERIC(15,4),
    reorder_point           NUMERIC(15,4),
    external_guid           TEXT,
    time_created            TIMESTAMPTZ,
    time_modified           TIMESTAMPTZ,
    edit_sequence           TEXT,
    synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_items_name      ON :schema.items (name);
CREATE INDEX IF NOT EXISTS idx_items_type      ON :schema.items (item_type);
CREATE INDEX IF NOT EXISTS idx_items_modified  ON :schema.items (time_modified DESC);

-- Assembly Bill of Materials
CREATE TABLE IF NOT EXISTS :schema.assembly_bom_lines (
    assembly_list_id    TEXT NOT NULL REFERENCES :schema.items(qb_list_id) ON DELETE CASCADE,
    line_seq_no         INTEGER NOT NULL,
    item_list_id        TEXT,
    item_name           TEXT,
    quantity            NUMERIC(15,4),
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (assembly_list_id, line_seq_no)
);
CREATE INDEX IF NOT EXISTS idx_bom_assembly ON :schema.assembly_bom_lines (assembly_list_id);
CREATE INDEX IF NOT EXISTS idx_bom_item     ON :schema.assembly_bom_lines (item_list_id);

-- ============================================================================
-- Invoices + line items
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.invoices (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    customer_list_id    TEXT REFERENCES :schema.customers(qb_list_id) ON DELETE SET NULL,
    customer_name       TEXT,
    class_name          TEXT,
    ar_account          TEXT,
    template_name       TEXT,
    bill_address        JSONB,
    ship_address        JSONB,
    is_pending          BOOLEAN,
    is_finance_charge   BOOLEAN,
    po_number           TEXT,
    terms               TEXT,
    due_date            DATE,
    sales_rep           TEXT,
    ship_date           DATE,
    ship_method         TEXT,
    subtotal            NUMERIC(15,2),
    item_sales_tax      TEXT,
    sales_tax_percentage NUMERIC(6,3),
    sales_tax_total     NUMERIC(15,2),
    applied_amount      NUMERIC(15,2),
    balance_remaining   NUMERIC(15,2),
    memo                TEXT,
    is_paid             BOOLEAN,
    external_guid       TEXT,
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_invoices_customer  ON :schema.invoices (customer_list_id);
CREATE INDEX IF NOT EXISTS idx_invoices_date      ON :schema.invoices (txn_date DESC);
CREATE INDEX IF NOT EXISTS idx_invoices_modified  ON :schema.invoices (time_modified DESC);
CREATE INDEX IF NOT EXISTS idx_invoices_unpaid     ON :schema.invoices (is_paid) WHERE is_paid = false;

CREATE TABLE IF NOT EXISTS :schema.invoice_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.invoices(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    line_type       TEXT,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    sales_tax_code  TEXT,
    class_name      TEXT,
    account_name    TEXT,
    memo            TEXT,
    service_date    DATE,
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);
CREATE INDEX IF NOT EXISTS idx_invoice_lines_txn ON :schema.invoice_lines (txn_id);

-- ============================================================================
-- Sales Receipts
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.sales_receipts (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    customer_list_id    TEXT,
    customer_name       TEXT,
    class_name          TEXT,
    ar_account          TEXT,
    payment_method      TEXT,
    memo                TEXT,
    check_number        TEXT,
    bill_address        JSONB,
    ship_address        JSONB,
    subtotal            NUMERIC(15,2),
    sales_tax_total     NUMERIC(15,2),
    total_amount        NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sales_receipts_date     ON :schema.sales_receipts (txn_date DESC);
CREATE INDEX IF NOT EXISTS idx_sales_receipts_customer ON :schema.sales_receipts (customer_list_id);

CREATE TABLE IF NOT EXISTS :schema.sales_receipt_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.sales_receipts(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    line_type       TEXT,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    sales_tax_code  TEXT,
    class_name      TEXT,
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Credit Memos
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.credit_memos (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    customer_list_id    TEXT,
    customer_name       TEXT,
    class_name          TEXT,
    ar_account          TEXT,
    memo                TEXT,
    subtotal            NUMERIC(15,2),
    sales_tax_total     NUMERIC(15,2),
    total_credit_remaining NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.credit_memo_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.credit_memos(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Bills + lines
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.bills (
    qb_txn_id       TEXT PRIMARY KEY,
    txn_number      TEXT,
    txn_date        DATE,
    vendor_list_id  TEXT REFERENCES :schema.vendors(qb_list_id) ON DELETE SET NULL,
    vendor_name     TEXT,
    ap_account      TEXT,
    due_date        DATE,
    amount_due      NUMERIC(15,2),
    memo            TEXT,
    is_paid         BOOLEAN,
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bills_vendor   ON :schema.bills (vendor_list_id);
CREATE INDEX IF NOT EXISTS idx_bills_date     ON :schema.bills (txn_date DESC);
CREATE INDEX IF NOT EXISTS idx_bills_unpaid   ON :schema.bills (is_paid) WHERE is_paid = false;

CREATE TABLE IF NOT EXISTS :schema.bill_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.bills(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    line_type       TEXT,
    item_name       TEXT,
    item_list_id    TEXT,
    account_name    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    class_name      TEXT,
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Bill Payments
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.bill_payments (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    vendor_list_id      TEXT,
    vendor_name         TEXT,
    payment_method_type TEXT,
    bank_account        TEXT,
    ap_account          TEXT,
    amount              NUMERIC(15,2),
    memo                TEXT,
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Vendor Credits
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.vendor_credits (
    qb_txn_id       TEXT PRIMARY KEY,
    txn_number      TEXT,
    txn_date        DATE,
    vendor_list_id  TEXT,
    vendor_name     TEXT,
    ap_account      TEXT,
    amount          NUMERIC(15,2),
    memo            TEXT,
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.vendor_credit_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.vendor_credits(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    account_name    TEXT,
    item_name       TEXT,
    description     TEXT,
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Purchase Orders
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.purchase_orders (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    vendor_list_id      TEXT,
    vendor_name         TEXT,
    class_name          TEXT,
    ship_address        JSONB,
    terms               TEXT,
    due_date            DATE,
    expected_date       DATE,
    ship_method         TEXT,
    is_manually_closed  BOOLEAN,
    is_fully_received   BOOLEAN,
    memo                TEXT,
    subtotal            NUMERIC(15,2),
    total_amount        NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.purchase_order_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.purchase_orders(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    class_name      TEXT,
    is_manually_closed BOOLEAN,
    qty_received_on_items NUMERIC(15,4),
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Estimates
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.estimates (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    customer_list_id    TEXT,
    customer_name       TEXT,
    class_name          TEXT,
    is_active           BOOLEAN,
    estimate_state      TEXT,
    expiration_date     DATE,
    memo                TEXT,
    subtotal            NUMERIC(15,2),
    sales_tax_total     NUMERIC(15,2),
    total_amount        NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.estimate_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.estimates(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Sales Orders
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.sales_orders (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    customer_list_id    TEXT,
    customer_name       TEXT,
    class_name          TEXT,
    is_manually_closed  BOOLEAN,
    is_fully_invoiced   BOOLEAN,
    memo                TEXT,
    subtotal            NUMERIC(15,2),
    total_amount        NUMERIC(15,2),
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.sales_order_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.sales_orders(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    description     TEXT,
    quantity        NUMERIC(15,4),
    unit_price      NUMERIC(15,4),
    amount          NUMERIC(15,2),
    qty_invoiced    NUMERIC(15,4),
    is_manually_closed BOOLEAN,
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Receive Payments
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.receive_payments (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    customer_list_id    TEXT,
    customer_name       TEXT,
    ar_account          TEXT,
    total_amount        NUMERIC(15,2),
    payment_method      TEXT,
    memo                TEXT,
    deposit_to_account  TEXT,
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Deposits
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.deposits (
    qb_txn_id       TEXT PRIMARY KEY,
    txn_date        DATE,
    deposit_to_account TEXT,
    memo            TEXT,
    total_amount    NUMERIC(15,2),
    cash_back_account TEXT,
    cash_back_memo  TEXT,
    cash_back_amount NUMERIC(15,2),
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.deposit_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.deposits(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    entity_name     TEXT,
    account_name    TEXT,
    memo            TEXT,
    amount          NUMERIC(15,2),
    payment_method  TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Checks
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.checks (
    qb_txn_id       TEXT PRIMARY KEY,
    txn_number      TEXT,
    txn_date        DATE,
    bank_account    TEXT,
    entity_name     TEXT,
    is_to_be_printed BOOLEAN,
    memo            TEXT,
    amount          NUMERIC(15,2),
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.check_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.checks(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    account_name    TEXT,
    item_name       TEXT,
    description     TEXT,
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Credit Card Charges
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.credit_card_charges (
    qb_txn_id       TEXT PRIMARY KEY,
    txn_number      TEXT,
    txn_date        DATE,
    credit_card_account TEXT,
    entity_name     TEXT,
    memo            TEXT,
    amount          NUMERIC(15,2),
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.credit_card_charge_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.credit_card_charges(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    account_name    TEXT,
    item_name       TEXT,
    description     TEXT,
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Credit Card Credits
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.credit_card_credits (
    qb_txn_id       TEXT PRIMARY KEY,
    txn_number      TEXT,
    txn_date        DATE,
    credit_card_account TEXT,
    entity_name     TEXT,
    memo            TEXT,
    amount          NUMERIC(15,2),
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.credit_card_credit_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.credit_card_credits(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    account_name    TEXT,
    item_name       TEXT,
    description     TEXT,
    amount          NUMERIC(15,2),
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Journal Entries
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.journal_entries (
    qb_txn_id       TEXT PRIMARY KEY,
    txn_number      TEXT,
    txn_date        DATE,
    is_adjustment   BOOLEAN,
    memo            TEXT,
    time_created    TIMESTAMPTZ,
    time_modified   TIMESTAMPTZ,
    edit_sequence   TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_je_date ON :schema.journal_entries (txn_date DESC);

CREATE TABLE IF NOT EXISTS :schema.journal_entry_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.journal_entries(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    line_type       TEXT,       -- Debit or Credit
    account_name    TEXT,
    amount          NUMERIC(15,2),
    memo            TEXT,
    entity_name     TEXT,
    class_name      TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Transfers
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.transfers (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_date            DATE,
    from_account        TEXT,
    from_amount         NUMERIC(15,2),
    to_account          TEXT,
    to_amount           NUMERIC(15,2),
    memo                TEXT,
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Inventory Adjustments
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.inventory_adjustments (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_number          TEXT,
    txn_date            DATE,
    account_name        TEXT,
    class_name          TEXT,
    memo                TEXT,
    customer_name       TEXT,
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS :schema.inventory_adjustment_lines (
    id              BIGSERIAL PRIMARY KEY,
    txn_id          TEXT NOT NULL REFERENCES :schema.inventory_adjustments(qb_txn_id) ON DELETE CASCADE,
    line_seq_no     INTEGER NOT NULL,
    item_name       TEXT,
    item_list_id    TEXT,
    qty_diff        NUMERIC(15,4),
    value_diff      NUMERIC(15,2),
    new_quantity    NUMERIC(15,4),
    new_value       NUMERIC(15,2),
    lot_number      TEXT,
    serial_number   TEXT,
    UNIQUE (txn_id, line_seq_no)
);

-- ============================================================================
-- Time Tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS :schema.time_tracking (
    qb_txn_id           TEXT PRIMARY KEY,
    txn_date            DATE,
    entity_name         TEXT,
    customer_name       TEXT,
    item_service_name   TEXT,
    class_name          TEXT,
    duration_hours      NUMERIC(6,2),
    notes               TEXT,
    is_billable         TEXT,    -- Billable|NotBillable|HasBeenBilled
    billing_status      TEXT,
    time_created        TIMESTAMPTZ,
    time_modified       TIMESTAMPTZ,
    edit_sequence       TEXT,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_time_tracking_date     ON :schema.time_tracking (txn_date DESC);
CREATE INDEX IF NOT EXISTS idx_time_tracking_customer ON :schema.time_tracking (customer_name);

-- ============================================================================
-- Row-Level Security
-- Enable RLS on all tables; service role bypasses, anon key blocked by default.
-- ============================================================================
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT tablename FROM pg_tables WHERE schemaname = :'schema'
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', :'schema', t);
        -- Service role policy (drop + create to avoid "already exists" error)
        BEGIN
            EXECUTE format(
                'CREATE POLICY "service_role_all" ON %I.%I USING (true) WITH CHECK (true)',
                :'schema', t
            );
        EXCEPTION WHEN duplicate_object THEN
            NULL; -- policy already exists, skip
        END;
    END LOOP;
END $$;
