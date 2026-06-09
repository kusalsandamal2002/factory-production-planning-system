-- ============================================================
-- Factory Oven Planner
-- Monthly Stock Count Module Schema
--
-- Purpose:
--   Monthly stock count Excel upload support.
--   Stores Material, FG, QC, Balance to PRD, Final Stock, Over PRD.
--
-- Business Logic:
--   Final Stock = FG + QC + Balance to PRD
--   Over PRD is manager editable from app.
--   Previous months can be viewed.
--
-- Important:
--   This script resets only the new monthly stock count module tables.
--   Do NOT run the app while applying this script.
-- ============================================================

BEGIN;

-- ============================================================
-- 1. Drop monthly stock count tables if already exist
-- ============================================================

DROP TABLE IF EXISTS monthly_stock_count_lines CASCADE;
DROP TABLE IF EXISTS monthly_stock_counts CASCADE;

-- ============================================================
-- 2. Monthly stock count upload header table
--    One record = one uploaded monthly stock Excel file
-- ============================================================

CREATE TABLE monthly_stock_counts (
    id BIGSERIAL PRIMARY KEY,

    stock_month_label VARCHAR(50) NOT NULL,
    month_key VARCHAR(7) NOT NULL,

    file_name VARCHAR(255) NOT NULL,
    sheet_name VARCHAR(150) DEFAULT 'Sheet1' NOT NULL,

    uploaded_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
    uploaded_by VARCHAR(150),

    total_rows INTEGER DEFAULT 0 NOT NULL,

    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    status VARCHAR(30) DEFAULT 'IMPORTED' NOT NULL,

    remarks TEXT,

    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,

    CONSTRAINT chk_monthly_stock_counts_month_key
        CHECK (month_key ~ '^[0-9]{4}-[0-9]{2}$'),

    CONSTRAINT chk_monthly_stock_counts_total_rows
        CHECK (total_rows >= 0),

    CONSTRAINT chk_monthly_stock_counts_status
        CHECK (status IN ('IMPORTED', 'ARCHIVED'))
);

CREATE INDEX idx_monthly_stock_counts_month_key
    ON monthly_stock_counts(month_key);

CREATE INDEX idx_monthly_stock_counts_uploaded_at
    ON monthly_stock_counts(uploaded_at);

CREATE INDEX idx_monthly_stock_counts_is_active
    ON monthly_stock_counts(is_active);

-- Only one active upload is allowed for one month.
-- If same month is uploaded again, old one should be archived by app/service.
CREATE UNIQUE INDEX uq_monthly_stock_counts_active_month
    ON monthly_stock_counts(month_key)
    WHERE is_active = TRUE;

-- ============================================================
-- 3. Monthly stock count line table
--    One record = one material row from uploaded Excel
-- ============================================================

CREATE TABLE monthly_stock_count_lines (
    id BIGSERIAL PRIMARY KEY,

    stock_count_id BIGINT NOT NULL
        REFERENCES monthly_stock_counts(id)
        ON DELETE CASCADE,

    material_code VARCHAR(100) NOT NULL,
    material_description TEXT,

    fg_qty NUMERIC(14, 3) DEFAULT 0 NOT NULL,
    qc_qty NUMERIC(14, 3) DEFAULT 0 NOT NULL,
    balance_to_prd_qty NUMERIC(14, 3) DEFAULT 0 NOT NULL,

    final_stock_qty NUMERIC(14, 3)
        GENERATED ALWAYS AS (
            fg_qty + qc_qty + balance_to_prd_qty
        ) STORED,

    over_prd_qty NUMERIC(14, 3) DEFAULT 0 NOT NULL,
    over_prd_updated_at TIMESTAMP WITHOUT TIME ZONE,

    source_row_number INTEGER,

    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,

    CONSTRAINT uq_monthly_stock_line_material
        UNIQUE (stock_count_id, material_code),

    CONSTRAINT chk_monthly_stock_line_fg_qty
        CHECK (fg_qty >= 0),

    CONSTRAINT chk_monthly_stock_line_qc_qty
        CHECK (qc_qty >= 0),

    CONSTRAINT chk_monthly_stock_line_balance_to_prd_qty
        CHECK (balance_to_prd_qty >= 0),

    CONSTRAINT chk_monthly_stock_line_over_prd_qty
        CHECK (over_prd_qty >= 0),

    CONSTRAINT chk_monthly_stock_line_source_row_number
        CHECK (source_row_number IS NULL OR source_row_number > 0)
);

CREATE INDEX idx_monthly_stock_count_lines_stock_count_id
    ON monthly_stock_count_lines(stock_count_id);

CREATE INDEX idx_monthly_stock_count_lines_material_code
    ON monthly_stock_count_lines(material_code);

CREATE INDEX idx_monthly_stock_count_lines_description
    ON monthly_stock_count_lines(material_description);

-- ============================================================
-- 4. Updated-at trigger function
-- ============================================================

CREATE OR REPLACE FUNCTION set_monthly_stock_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 5. Updated-at triggers
-- ============================================================

CREATE TRIGGER trg_monthly_stock_counts_updated_at
BEFORE UPDATE ON monthly_stock_counts
FOR EACH ROW
EXECUTE FUNCTION set_monthly_stock_updated_at();

CREATE TRIGGER trg_monthly_stock_count_lines_updated_at
BEFORE UPDATE ON monthly_stock_count_lines
FOR EACH ROW
EXECUTE FUNCTION set_monthly_stock_updated_at();

COMMIT;