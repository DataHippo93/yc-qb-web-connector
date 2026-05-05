-- =============================================================================
-- Migration 013: Payroll extraction tables
-- Adds paychecks (header + lines), payroll_items_wage, payroll_items_non_wage,
-- and billing_rates to every company schema.
-- Applied to: adk_fragrance, natures_storehouse, maine_and_maine,
--             yc_consulting, yc_works
-- =============================================================================

DO $$
DECLARE
    s TEXT;
    company_schemas TEXT[] := ARRAY[
        'adk_fragrance',
        'maine_and_maine',
        'yc_consulting',
        'yc_works'
    ];
BEGIN
    FOREACH s IN ARRAY company_schemas LOOP

        -- ─────────────────────────────────────────────────────────────────────
        -- paychecks (header)
        -- One row per QB paycheck transaction. Pay-period dates come from
        -- PaycheckRet (qbXML 16+ exposes pay_period_start/end).
        -- ─────────────────────────────────────────────────────────────────────
        EXECUTE format($f$
            CREATE TABLE IF NOT EXISTS %I.paychecks (
                qb_txn_id            TEXT PRIMARY KEY,
                ref_number           TEXT,
                txn_number           INTEGER,
                txn_date             DATE,
                payroll_account_qb_list_id TEXT,
                payroll_account_name TEXT,
                employee_qb_list_id  TEXT,
                employee_full_name   TEXT,
                gross_pay            NUMERIC(15,2),
                net_pay              NUMERIC(15,2),
                total_taxes          NUMERIC(15,2),
                total_deductions     NUMERIC(15,2),
                total_company_contributions NUMERIC(15,2),
                pay_period_start     DATE,
                pay_period_end       DATE,
                is_to_be_printed     BOOLEAN,
                is_pending           BOOLEAN,
                is_void              BOOLEAN,
                memo                 TEXT,
                edit_sequence        TEXT,
                time_created         TIMESTAMPTZ,
                time_modified        TIMESTAMPTZ,
                synced_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $f$, s);

        EXECUTE format($f$
            CREATE INDEX IF NOT EXISTS idx_paychecks_employee
                ON %I.paychecks (employee_qb_list_id)
        $f$, s);
        EXECUTE format($f$
            CREATE INDEX IF NOT EXISTS idx_paychecks_txn_date
                ON %I.paychecks (txn_date)
        $f$, s);

        -- ─────────────────────────────────────────────────────────────────────
        -- paycheck_lines (per-item earnings, taxes, deductions, contributions)
        -- ─────────────────────────────────────────────────────────────────────
        EXECUTE format($f$
            CREATE TABLE IF NOT EXISTS %I.paycheck_lines (
                txn_id                  TEXT NOT NULL,
                line_seq_no             INTEGER NOT NULL,
                payroll_item_qb_list_id TEXT,
                payroll_item_name       TEXT,
                payroll_item_kind       TEXT,
                rate                    NUMERIC(15,4),
                hours                   NUMERIC(15,4),
                amount                  NUMERIC(15,2),
                ytd_amount              NUMERIC(15,2),
                class_qb_list_id        TEXT,
                class_name              TEXT,
                customer_qb_list_id     TEXT,
                customer_name           TEXT,
                synced_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (txn_id, line_seq_no)
            )
        $f$, s);

        EXECUTE format($f$
            CREATE INDEX IF NOT EXISTS idx_paycheck_lines_item
                ON %I.paycheck_lines (payroll_item_qb_list_id)
        $f$, s);
        EXECUTE format($f$
            CREATE INDEX IF NOT EXISTS idx_paycheck_lines_kind
                ON %I.paycheck_lines (payroll_item_kind)
        $f$, s);

        -- ─────────────────────────────────────────────────────────────────────
        -- payroll_items_wage (HourlyRegular, HourlyOvertime, Salary, Bonus, …)
        -- ─────────────────────────────────────────────────────────────────────
        EXECUTE format($f$
            CREATE TABLE IF NOT EXISTS %I.payroll_items_wage (
                qb_list_id             TEXT PRIMARY KEY,
                name                   TEXT NOT NULL,
                full_name              TEXT,
                is_active              BOOLEAN,
                wage_type              TEXT,
                expense_account_qb_list_id TEXT,
                expense_account_name   TEXT,
                edit_sequence          TEXT,
                time_created           TIMESTAMPTZ,
                time_modified          TIMESTAMPTZ,
                synced_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $f$, s);

        -- ─────────────────────────────────────────────────────────────────────
        -- payroll_items_non_wage (Addition, Deduction, CompanyContribution,
        -- FederalTax, StateTax, OtherTax, …)
        -- ─────────────────────────────────────────────────────────────────────
        EXECUTE format($f$
            CREATE TABLE IF NOT EXISTS %I.payroll_items_non_wage (
                qb_list_id             TEXT PRIMARY KEY,
                name                   TEXT NOT NULL,
                full_name              TEXT,
                is_active              BOOLEAN,
                item_kind              TEXT,
                liability_account_qb_list_id TEXT,
                liability_account_name TEXT,
                expense_account_qb_list_id TEXT,
                expense_account_name   TEXT,
                vendor_qb_list_id      TEXT,
                vendor_name            TEXT,
                edit_sequence          TEXT,
                time_created           TIMESTAMPTZ,
                time_modified          TIMESTAMPTZ,
                synced_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $f$, s);

        -- ─────────────────────────────────────────────────────────────────────
        -- billing_rates (rate cards used for time-tracking → invoicing)
        -- ─────────────────────────────────────────────────────────────────────
        EXECUTE format($f$
            CREATE TABLE IF NOT EXISTS %I.billing_rates (
                qb_list_id             TEXT PRIMARY KEY,
                name                   TEXT NOT NULL,
                is_active              BOOLEAN,
                billing_rate_type      TEXT,
                fixed_rate             NUMERIC(15,4),
                edit_sequence          TEXT,
                time_created           TIMESTAMPTZ,
                time_modified          TIMESTAMPTZ,
                synced_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        $f$, s);

        RAISE NOTICE 'Payroll tables created for schema: %', s;
    END LOOP;
END $$;
