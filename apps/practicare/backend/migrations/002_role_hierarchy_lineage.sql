-- PractiCare Stabilization: Role Hierarchy Lineage Columns
-- Non-destructive additive migration for PostgreSQL.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by_user_id VARCHAR(50);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by_role VARCHAR(50);

ALTER TABLE checklists ADD COLUMN IF NOT EXISTS created_by_user_id VARCHAR(50);
ALTER TABLE checklists ADD COLUMN IF NOT EXISTS created_by_role VARCHAR(50);

CREATE INDEX IF NOT EXISTS idx_tasks_creator ON tasks (tenant_id, created_by_role);
CREATE INDEX IF NOT EXISTS idx_checklists_creator ON checklists (tenant_id, created_by_role);

