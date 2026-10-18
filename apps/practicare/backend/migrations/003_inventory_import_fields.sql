-- PractiCare MOC: inventory import fields and idempotent import log
-- Additive and idempotent: existing inventory rows keep their values; new columns are NULL.
-- The backend applies the same statements on startup (database.init_db_and_seed); running this file
-- by hand first is safe and makes the startup statements no-ops.

BEGIN;

ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS supplier VARCHAR(150);
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS batch_number VARCHAR(80);
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS purchase_price NUMERIC(12, 2);

CREATE TABLE IF NOT EXISTS inventory_imports (
    id VARCHAR(50) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    import_token VARCHAR(64) NOT NULL UNIQUE,
    source_type VARCHAR(20) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    created_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITHOUT TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_inventory_imports_tenant_id ON inventory_imports (tenant_id);
CREATE INDEX IF NOT EXISTS idx_inventory_imports_source ON inventory_imports (tenant_id, source_hash);

COMMIT;

-- Rollback (only after the backend is reverted to a build without these fields):
-- BEGIN;
-- DROP TABLE IF EXISTS inventory_imports;
-- ALTER TABLE inventory_items DROP COLUMN IF EXISTS purchase_price;
-- ALTER TABLE inventory_items DROP COLUMN IF EXISTS batch_number;
-- ALTER TABLE inventory_items DROP COLUMN IF EXISTS supplier;
-- COMMIT;
