-- =============================================================================
-- Migration 011: <schema>.expenses_unified view
--
-- Purpose: provide ONE source of truth for OpEx analysis across all the QB
-- transaction types that can carry expense activity:
--   bills              (accrual A/P)
--   checks             (cash, direct expense entry)
--   credit_card_charges
--   vendor_credits     (refunds — negated)
--   journal_entries    (only the lines touching Expense / OtherExpense /
--                       CostOfGoodsSold accounts; debits positive, credits
--                       negative)
--
-- Why: ADKFF tapered off using the QB Bills workflow during 2024 and now
-- enters most expenses directly as Checks or Credit Card Charges. Joining
-- bill_lines alone misses those expenses entirely. This view lets analysts
-- compute true OpEx with a single query against expenses_unified, instead
-- of UNIONing four tables every time.
--
-- Stable column set (consumers can rely on these names):
--   source             text   — 'bill' | 'check' | 'credit_card_charge'
--                                 | 'vendor_credit' | 'journal_entry'
--   txn_id             text   — qb_txn_id of the parent transaction
--   line_seq_no        int    — line number within the transaction
--   txn_date           date   — transaction date in QB
--   vendor_or_entity   text   — vendor / payee / entity (NULL when blank)
--   account_name       text   — expense account this line is posted to
--   item_name          text   — item, when present (NULL for journal entries)
--   description        text   — line memo, falls back to the header memo
--   amount             numeric— positive = expense; vendor credits and
--                                 expense-account credit lines are negated
--   class_name         text   — class, when present
--   is_paid            bool   — bills only; NULL elsewhere
--   synced_at          timestamptz — when the parent header was last synced
--
-- The view is recreated (CREATE OR REPLACE VIEW) so reruns are idempotent.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Helper macro: this file is a SCRIPT — it spells out the view definition for
-- every QB-connected schema. Adding a 6th company means adding a 6th block.
-- -----------------------------------------------------------------------------

-- adk_fragrance ---------------------------------------------------------------
CREATE OR REPLACE VIEW adk_fragrance.expenses_unified AS
SELECT 'bill'::text AS source, b.qb_txn_id AS txn_id, bl.line_seq_no, b.txn_date,
       b.vendor_name AS vendor_or_entity, bl.account_name, bl.item_name,
       COALESCE(bl.description, b.memo) AS description,
       bl.amount, bl.class_name, b.is_paid, b.synced_at
FROM adk_fragrance.bills b
JOIN adk_fragrance.bill_lines bl ON bl.txn_id = b.qb_txn_id
WHERE bl.amount IS NOT NULL
UNION ALL
SELECT 'check', c.qb_txn_id, cl.line_seq_no, c.txn_date,
       c.entity_name, cl.account_name, cl.item_name,
       COALESCE(cl.description, c.memo), cl.amount,
       NULL::text, NULL::boolean, c.synced_at
FROM adk_fragrance.checks c
JOIN adk_fragrance.check_lines cl ON cl.txn_id = c.qb_txn_id
WHERE cl.amount IS NOT NULL
UNION ALL
SELECT 'credit_card_charge', cc.qb_txn_id, ccl.line_seq_no, cc.txn_date,
       cc.entity_name, ccl.account_name, ccl.item_name,
       COALESCE(ccl.description, cc.memo), ccl.amount,
       NULL, NULL, cc.synced_at
FROM adk_fragrance.credit_card_charges cc
JOIN adk_fragrance.credit_card_charge_lines ccl ON ccl.txn_id = cc.qb_txn_id
WHERE ccl.amount IS NOT NULL
UNION ALL
SELECT 'vendor_credit', vc.qb_txn_id, vcl.line_seq_no, vc.txn_date,
       vc.vendor_name, vcl.account_name, vcl.item_name,
       COALESCE(vcl.description, vc.memo), -vcl.amount,
       NULL, NULL, vc.synced_at
FROM adk_fragrance.vendor_credits vc
JOIN adk_fragrance.vendor_credit_lines vcl ON vcl.txn_id = vc.qb_txn_id
WHERE vcl.amount IS NOT NULL
UNION ALL
SELECT 'journal_entry', j.qb_txn_id, jl.line_seq_no, j.txn_date,
       jl.entity_name, jl.account_name, NULL::text,
       COALESCE(jl.memo, j.memo),
       CASE WHEN jl.line_type = 'Debit' THEN jl.amount ELSE -jl.amount END,
       jl.class_name, NULL, j.synced_at
FROM adk_fragrance.journal_entries j
JOIN adk_fragrance.journal_entry_lines jl ON jl.txn_id = j.qb_txn_id
JOIN adk_fragrance.accounts a ON a.full_name = jl.account_name
WHERE jl.amount IS NOT NULL
  AND a.account_type IN ('Expense', 'OtherExpense', 'CostOfGoodsSold');

COMMENT ON VIEW adk_fragrance.expenses_unified IS
    'Unified OpEx view across bills + checks + credit_card_charges + vendor_credits + journal_entries (expense-account lines only). Use this instead of bill_lines alone — bills have been a minor workflow at ADKFF since 2024.';

-- natures_storehouse ----------------------------------------------------------
CREATE OR REPLACE VIEW natures_storehouse.expenses_unified AS
SELECT 'bill'::text, b.qb_txn_id, bl.line_seq_no, b.txn_date,
       b.vendor_name, bl.account_name, bl.item_name,
       COALESCE(bl.description, b.memo), bl.amount, bl.class_name, b.is_paid, b.synced_at
FROM natures_storehouse.bills b
JOIN natures_storehouse.bill_lines bl ON bl.txn_id = b.qb_txn_id
WHERE bl.amount IS NOT NULL
UNION ALL
SELECT 'check', c.qb_txn_id, cl.line_seq_no, c.txn_date,
       c.entity_name, cl.account_name, cl.item_name,
       COALESCE(cl.description, c.memo), cl.amount, NULL::text, NULL::boolean, c.synced_at
FROM natures_storehouse.checks c
JOIN natures_storehouse.check_lines cl ON cl.txn_id = c.qb_txn_id
WHERE cl.amount IS NOT NULL
UNION ALL
SELECT 'credit_card_charge', cc.qb_txn_id, ccl.line_seq_no, cc.txn_date,
       cc.entity_name, ccl.account_name, ccl.item_name,
       COALESCE(ccl.description, cc.memo), ccl.amount, NULL, NULL, cc.synced_at
FROM natures_storehouse.credit_card_charges cc
JOIN natures_storehouse.credit_card_charge_lines ccl ON ccl.txn_id = cc.qb_txn_id
WHERE ccl.amount IS NOT NULL
UNION ALL
SELECT 'vendor_credit', vc.qb_txn_id, vcl.line_seq_no, vc.txn_date,
       vc.vendor_name, vcl.account_name, vcl.item_name,
       COALESCE(vcl.description, vc.memo), -vcl.amount, NULL, NULL, vc.synced_at
FROM natures_storehouse.vendor_credits vc
JOIN natures_storehouse.vendor_credit_lines vcl ON vcl.txn_id = vc.qb_txn_id
WHERE vcl.amount IS NOT NULL
UNION ALL
SELECT 'journal_entry', j.qb_txn_id, jl.line_seq_no, j.txn_date,
       jl.entity_name, jl.account_name, NULL::text,
       COALESCE(jl.memo, j.memo),
       CASE WHEN jl.line_type = 'Debit' THEN jl.amount ELSE -jl.amount END,
       jl.class_name, NULL, j.synced_at
FROM natures_storehouse.journal_entries j
JOIN natures_storehouse.journal_entry_lines jl ON jl.txn_id = j.qb_txn_id
JOIN natures_storehouse.accounts a ON a.full_name = jl.account_name
WHERE jl.amount IS NOT NULL
  AND a.account_type IN ('Expense', 'OtherExpense', 'CostOfGoodsSold');

COMMENT ON VIEW natures_storehouse.expenses_unified IS
    'Unified OpEx view across bills + checks + credit_card_charges + vendor_credits + journal_entries (expense-account lines only).';

-- yc_works --------------------------------------------------------------------
CREATE OR REPLACE VIEW yc_works.expenses_unified AS
SELECT 'bill'::text, b.qb_txn_id, bl.line_seq_no, b.txn_date,
       b.vendor_name, bl.account_name, bl.item_name,
       COALESCE(bl.description, b.memo), bl.amount, bl.class_name, b.is_paid, b.synced_at
FROM yc_works.bills b
JOIN yc_works.bill_lines bl ON bl.txn_id = b.qb_txn_id
WHERE bl.amount IS NOT NULL
UNION ALL
SELECT 'check', c.qb_txn_id, cl.line_seq_no, c.txn_date,
       c.entity_name, cl.account_name, cl.item_name,
       COALESCE(cl.description, c.memo), cl.amount, NULL::text, NULL::boolean, c.synced_at
FROM yc_works.checks c
JOIN yc_works.check_lines cl ON cl.txn_id = c.qb_txn_id
WHERE cl.amount IS NOT NULL
UNION ALL
SELECT 'credit_card_charge', cc.qb_txn_id, ccl.line_seq_no, cc.txn_date,
       cc.entity_name, ccl.account_name, ccl.item_name,
       COALESCE(ccl.description, cc.memo), ccl.amount, NULL, NULL, cc.synced_at
FROM yc_works.credit_card_charges cc
JOIN yc_works.credit_card_charge_lines ccl ON ccl.txn_id = cc.qb_txn_id
WHERE ccl.amount IS NOT NULL
UNION ALL
SELECT 'vendor_credit', vc.qb_txn_id, vcl.line_seq_no, vc.txn_date,
       vc.vendor_name, vcl.account_name, vcl.item_name,
       COALESCE(vcl.description, vc.memo), -vcl.amount, NULL, NULL, vc.synced_at
FROM yc_works.vendor_credits vc
JOIN yc_works.vendor_credit_lines vcl ON vcl.txn_id = vc.qb_txn_id
WHERE vcl.amount IS NOT NULL
UNION ALL
SELECT 'journal_entry', j.qb_txn_id, jl.line_seq_no, j.txn_date,
       jl.entity_name, jl.account_name, NULL::text,
       COALESCE(jl.memo, j.memo),
       CASE WHEN jl.line_type = 'Debit' THEN jl.amount ELSE -jl.amount END,
       jl.class_name, NULL, j.synced_at
FROM yc_works.journal_entries j
JOIN yc_works.journal_entry_lines jl ON jl.txn_id = j.qb_txn_id
JOIN yc_works.accounts a ON a.full_name = jl.account_name
WHERE jl.amount IS NOT NULL
  AND a.account_type IN ('Expense', 'OtherExpense', 'CostOfGoodsSold');

-- maine_and_maine -------------------------------------------------------------
CREATE OR REPLACE VIEW maine_and_maine.expenses_unified AS
SELECT 'bill'::text, b.qb_txn_id, bl.line_seq_no, b.txn_date,
       b.vendor_name, bl.account_name, bl.item_name,
       COALESCE(bl.description, b.memo), bl.amount, bl.class_name, b.is_paid, b.synced_at
FROM maine_and_maine.bills b
JOIN maine_and_maine.bill_lines bl ON bl.txn_id = b.qb_txn_id
WHERE bl.amount IS NOT NULL
UNION ALL
SELECT 'check', c.qb_txn_id, cl.line_seq_no, c.txn_date,
       c.entity_name, cl.account_name, cl.item_name,
       COALESCE(cl.description, c.memo), cl.amount, NULL::text, NULL::boolean, c.synced_at
FROM maine_and_maine.checks c
JOIN maine_and_maine.check_lines cl ON cl.txn_id = c.qb_txn_id
WHERE cl.amount IS NOT NULL
UNION ALL
SELECT 'credit_card_charge', cc.qb_txn_id, ccl.line_seq_no, cc.txn_date,
       cc.entity_name, ccl.account_name, ccl.item_name,
       COALESCE(ccl.description, cc.memo), ccl.amount, NULL, NULL, cc.synced_at
FROM maine_and_maine.credit_card_charges cc
JOIN maine_and_maine.credit_card_charge_lines ccl ON ccl.txn_id = cc.qb_txn_id
WHERE ccl.amount IS NOT NULL
UNION ALL
SELECT 'vendor_credit', vc.qb_txn_id, vcl.line_seq_no, vc.txn_date,
       vc.vendor_name, vcl.account_name, vcl.item_name,
       COALESCE(vcl.description, vc.memo), -vcl.amount, NULL, NULL, vc.synced_at
FROM maine_and_maine.vendor_credits vc
JOIN maine_and_maine.vendor_credit_lines vcl ON vcl.txn_id = vc.qb_txn_id
WHERE vcl.amount IS NOT NULL
UNION ALL
SELECT 'journal_entry', j.qb_txn_id, jl.line_seq_no, j.txn_date,
       jl.entity_name, jl.account_name, NULL::text,
       COALESCE(jl.memo, j.memo),
       CASE WHEN jl.line_type = 'Debit' THEN jl.amount ELSE -jl.amount END,
       jl.class_name, NULL, j.synced_at
FROM maine_and_maine.journal_entries j
JOIN maine_and_maine.journal_entry_lines jl ON jl.txn_id = j.qb_txn_id
JOIN maine_and_maine.accounts a ON a.full_name = jl.account_name
WHERE jl.amount IS NOT NULL
  AND a.account_type IN ('Expense', 'OtherExpense', 'CostOfGoodsSold');

-- yc_consulting ---------------------------------------------------------------
CREATE OR REPLACE VIEW yc_consulting.expenses_unified AS
SELECT 'bill'::text, b.qb_txn_id, bl.line_seq_no, b.txn_date,
       b.vendor_name, bl.account_name, bl.item_name,
       COALESCE(bl.description, b.memo), bl.amount, bl.class_name, b.is_paid, b.synced_at
FROM yc_consulting.bills b
JOIN yc_consulting.bill_lines bl ON bl.txn_id = b.qb_txn_id
WHERE bl.amount IS NOT NULL
UNION ALL
SELECT 'check', c.qb_txn_id, cl.line_seq_no, c.txn_date,
       c.entity_name, cl.account_name, cl.item_name,
       COALESCE(cl.description, c.memo), cl.amount, NULL::text, NULL::boolean, c.synced_at
FROM yc_consulting.checks c
JOIN yc_consulting.check_lines cl ON cl.txn_id = c.qb_txn_id
WHERE cl.amount IS NOT NULL
UNION ALL
SELECT 'credit_card_charge', cc.qb_txn_id, ccl.line_seq_no, cc.txn_date,
       cc.entity_name, ccl.account_name, ccl.item_name,
       COALESCE(ccl.description, cc.memo), ccl.amount, NULL, NULL, cc.synced_at
FROM yc_consulting.credit_card_charges cc
JOIN yc_consulting.credit_card_charge_lines ccl ON ccl.txn_id = cc.qb_txn_id
WHERE ccl.amount IS NOT NULL
UNION ALL
SELECT 'vendor_credit', vc.qb_txn_id, vcl.line_seq_no, vc.txn_date,
       vc.vendor_name, vcl.account_name, vcl.item_name,
       COALESCE(vcl.description, vc.memo), -vcl.amount, NULL, NULL, vc.synced_at
FROM yc_consulting.vendor_credits vc
JOIN yc_consulting.vendor_credit_lines vcl ON vcl.txn_id = vc.qb_txn_id
WHERE vcl.amount IS NOT NULL
UNION ALL
SELECT 'journal_entry', j.qb_txn_id, jl.line_seq_no, j.txn_date,
       jl.entity_name, jl.account_name, NULL::text,
       COALESCE(jl.memo, j.memo),
       CASE WHEN jl.line_type = 'Debit' THEN jl.amount ELSE -jl.amount END,
       jl.class_name, NULL, j.synced_at
FROM yc_consulting.journal_entries j
JOIN yc_consulting.journal_entry_lines jl ON jl.txn_id = j.qb_txn_id
JOIN yc_consulting.accounts a ON a.full_name = jl.account_name
WHERE jl.amount IS NOT NULL
  AND a.account_type IN ('Expense', 'OtherExpense', 'CostOfGoodsSold');
