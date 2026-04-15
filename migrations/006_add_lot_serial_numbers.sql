-- =============================================================================
-- Migration 006: Add lot_number and serial_number columns to line tables
--
-- With lot/serial number tracking enabled in QB Desktop company preferences,
-- line items on purchase txns, sales txns, inventory adjustments, and transfers
-- can carry LotNumber and SerialNumber elements.
--
-- Run for each company schema.
-- =============================================================================

-- Invoice lines
ALTER TABLE natures_storehouse.invoice_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.invoice_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.invoice_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.invoice_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.invoice_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.invoice_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.invoice_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.invoice_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.invoice_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.invoice_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Sales receipt lines
ALTER TABLE natures_storehouse.sales_receipt_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.sales_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.sales_receipt_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.sales_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.sales_receipt_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.sales_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.sales_receipt_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.sales_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.sales_receipt_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.sales_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Credit memo lines
ALTER TABLE natures_storehouse.credit_memo_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.credit_memo_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.credit_memo_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.credit_memo_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.credit_memo_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.credit_memo_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.credit_memo_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.credit_memo_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.credit_memo_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.credit_memo_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Bill lines
ALTER TABLE natures_storehouse.bill_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.bill_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.bill_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.bill_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.bill_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.bill_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.bill_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.bill_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.bill_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.bill_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Purchase order lines
ALTER TABLE natures_storehouse.purchase_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.purchase_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.purchase_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.purchase_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.purchase_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.purchase_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.purchase_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.purchase_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.purchase_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.purchase_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Estimate lines
ALTER TABLE natures_storehouse.estimate_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.estimate_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.estimate_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.estimate_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.estimate_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.estimate_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.estimate_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.estimate_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.estimate_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.estimate_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Sales order lines
ALTER TABLE natures_storehouse.sales_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.sales_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.sales_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.sales_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.sales_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.sales_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.sales_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.sales_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.sales_order_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.sales_order_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Check lines
ALTER TABLE natures_storehouse.check_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.check_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.check_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.check_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.check_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.check_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.check_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.check_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.check_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.check_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Credit card charge lines
ALTER TABLE natures_storehouse.credit_card_charge_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.credit_card_charge_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.credit_card_charge_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.credit_card_charge_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.credit_card_charge_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.credit_card_charge_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.credit_card_charge_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.credit_card_charge_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.credit_card_charge_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.credit_card_charge_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Credit card credit lines
ALTER TABLE natures_storehouse.credit_card_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.credit_card_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.credit_card_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.credit_card_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.credit_card_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.credit_card_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.credit_card_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.credit_card_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.credit_card_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.credit_card_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Vendor credit lines
ALTER TABLE natures_storehouse.vendor_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.vendor_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.vendor_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.vendor_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.vendor_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.vendor_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.vendor_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.vendor_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.vendor_credit_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.vendor_credit_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Inventory adjustment lines
ALTER TABLE natures_storehouse.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE natures_storehouse.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE adk_fragrance.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_works.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE maine_and_maine.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS lot_number TEXT;
ALTER TABLE yc_consulting.inventory_adjustment_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;

-- Item receipt lines (already has lot_number, just add serial_number)
ALTER TABLE natures_storehouse.item_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE adk_fragrance.item_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_works.item_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE maine_and_maine.item_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
ALTER TABLE yc_consulting.item_receipt_lines ADD COLUMN IF NOT EXISTS serial_number TEXT;
