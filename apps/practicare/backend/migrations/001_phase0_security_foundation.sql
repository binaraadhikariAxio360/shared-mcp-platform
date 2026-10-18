-- PractiCare Phase 0 security foundation.
-- Additive only. Review against a verified target before execution.

CREATE TABLE IF NOT EXISTS ai_pending_approvals (
    id VARCHAR(50) PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL REFERENCES practicare_users(id) ON DELETE CASCADE,
    user_role VARCHAR(50) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    arguments_json TEXT NOT NULL,
    arguments_hash VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    resolved_at TIMESTAMP WITHOUT TIME ZONE NULL,
    executed_at TIMESTAMP WITHOUT TIME ZONE NULL,
    error_detail TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_approval_principal
    ON ai_pending_approvals (tenant_id, user_id, status);
CREATE INDEX IF NOT EXISTS ix_ai_pending_approvals_tenant_id
    ON ai_pending_approvals (tenant_id);
CREATE INDEX IF NOT EXISTS ix_ai_pending_approvals_user_id
    ON ai_pending_approvals (user_id);
CREATE INDEX IF NOT EXISTS ix_ai_pending_approvals_status
    ON ai_pending_approvals (status);

CREATE TABLE IF NOT EXISTS ai_audit_events (
    id VARCHAR(50) PRIMARY KEY,
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tenant_id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    user_role VARCHAR(50) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    input_args_json TEXT NOT NULL DEFAULT '{}',
    status VARCHAR(30) NOT NULL,
    error_detail TEXT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ai_audit_tenant_time
    ON ai_audit_events (tenant_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_ai_audit_events_timestamp
    ON ai_audit_events (timestamp);
CREATE INDEX IF NOT EXISTS ix_ai_audit_events_tenant_id
    ON ai_audit_events (tenant_id);
CREATE INDEX IF NOT EXISTS ix_ai_audit_events_user_id
    ON ai_audit_events (user_id);
CREATE INDEX IF NOT EXISTS ix_ai_audit_events_tool_name
    ON ai_audit_events (tool_name);
CREATE INDEX IF NOT EXISTS ix_ai_audit_events_status
    ON ai_audit_events (status);
