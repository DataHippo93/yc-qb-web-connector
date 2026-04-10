-- =============================================================================
-- Migration 004: Add assembly_bom_lines table to existing company schemas
-- Captures Bill of Materials for inventory assembly items
-- =============================================================================

-- natures_storehouse
CREATE TABLE IF NOT EXISTS natures_storehouse.assembly_bom_lines (
    assembly_list_id    TEXT NOT NULL REFERENCES natures_storehouse.items(qb_list_id) ON DELETE CASCADE,
    line_seq_no         INTEGER NOT NULL,
    item_list_id        TEXT,
    item_name           TEXT,
    quantity            NUMERIC(15,4),
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (assembly_list_id, line_seq_no)
);
CREATE INDEX IF NOT EXISTS idx_bom_assembly ON natures_storehouse.assembly_bom_lines (assembly_list_id);
CREATE INDEX IF NOT EXISTS idx_bom_item     ON natures_storehouse.assembly_bom_lines (item_list_id);

-- adk_fragrance
CREATE TABLE IF NOT EXISTS adk_fragrance.assembly_bom_lines (
    assembly_list_id    TEXT NOT NULL REFERENCES adk_fragrance.items(qb_list_id) ON DELETE CASCADE,
    line_seq_no         INTEGER NOT NULL,
    item_list_id        TEXT,
    item_name           TEXT,
    quantity            NUMERIC(15,4),
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (assembly_list_id, line_seq_no)
);
CREATE INDEX IF NOT EXISTS idx_bom_assembly ON adk_fragrance.assembly_bom_lines (assembly_list_id);
CREATE INDEX IF NOT EXISTS idx_bom_item     ON adk_fragrance.assembly_bom_lines (item_list_id);
