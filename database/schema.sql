-- B2B AI Support & Workflow Automation System
-- Database Schema: Tickets & Execution Audit Logs with Idempotency Support

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Clean existing tables if resetting schema
DROP TABLE IF EXISTS execution_logs CASCADE;
DROP TABLE IF EXISTS tickets CASCADE;

-- =============================================================================
-- 1. TICKETS TABLE
-- Stores ticket metadata, resolution state, and LLM output guarantees.
-- Enforces idempotency via UNIQUE constraint on idempotency_key.
-- =============================================================================
CREATE TABLE tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key VARCHAR(128) UNIQUE NOT NULL,
    ticket_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    customer_email VARCHAR(255),
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    category VARCHAR(64) DEFAULT 'GENERAL',
    priority VARCHAR(32) DEFAULT 'MEDIUM' CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'RESOLVED', 'ESCALATED', 'FAILED')),
    confidence_score NUMERIC(4, 3),
    resolution_summary TEXT,
    customer_reply TEXT,
    actions_taken JSONB DEFAULT '[]'::jsonb,
    execution_time_ms INTEGER DEFAULT 0,
    cost_estimate_usd NUMERIC(6, 4) DEFAULT 0.0300,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 2. EXECUTION_LOGS TABLE (Audit Tracking)
-- Immutable audit ledger capturing every execution step, tool call, latency,
-- and confidence score for compliance, observability, and rollback tracking.
-- =============================================================================
CREATE TABLE execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID REFERENCES tickets(id) ON DELETE SET NULL,
    idempotency_key VARCHAR(128),
    step_name VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('SUCCESS', 'WARNING', 'ERROR', 'SKIPPED')),
    confidence_score NUMERIC(4, 3),
    latency_ms INTEGER DEFAULT 0,
    input_payload JSONB,
    output_payload JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 3. INDEXES FOR HIGH-THROUGHPUT LOOKUPS & AUDIT QUERIES
-- =============================================================================
CREATE INDEX idx_tickets_idempotency_key ON tickets(idempotency_key);
CREATE INDEX idx_tickets_ticket_id ON tickets(ticket_id);
CREATE INDEX idx_tickets_customer_id ON tickets(customer_id);
CREATE INDEX idx_tickets_status ON tickets(status);
CREATE INDEX idx_tickets_category ON tickets(category);
CREATE INDEX idx_tickets_created_at ON tickets(created_at DESC);

CREATE INDEX idx_execution_logs_ticket_id ON execution_logs(ticket_id);
CREATE INDEX idx_execution_logs_idempotency_key ON execution_logs(idempotency_key);
CREATE INDEX idx_execution_logs_step_name ON execution_logs(step_name);
CREATE INDEX idx_execution_logs_status ON execution_logs(status);
CREATE INDEX idx_execution_logs_created_at ON execution_logs(created_at DESC);

-- =============================================================================
-- 4. AUTO-UPDATE TRIGGER FOR TICKETS.UPDATED_AT
-- =============================================================================
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_tickets_timestamp
BEFORE UPDATE ON tickets
FOR EACH ROW
EXECUTE FUNCTION update_modified_column();

-- =============================================================================
-- 5. HISTORICAL SEED DATA FOR EXECUTIVE DASHBOARD VISUALIZATION
-- Pre-populates realistic enterprise production scenarios (Resolved, Escalated)
-- =============================================================================
INSERT INTO tickets (
    idempotency_key, ticket_id, customer_id, customer_email, subject, body,
    category, priority, status, confidence_score, resolution_summary, customer_reply,
    actions_taken, execution_time_ms, cost_estimate_usd, created_at
) VALUES
(
    'SEED-IDEMP-001', 'TCK-9001', 'ACME-CORP-01', 'billing@acme.com',
    'Upgrade Subscription to Enterprise Tier',
    'Please upgrade our current team subscription to the Enterprise tier with annual billing.',
    'SUBSCRIPTION', 'HIGH', 'RESOLVED', 0.950,
    'Successfully invoked update_subscription_tier for ACME-CORP-01 to Enterprise tier.',
    'Hello Acme Team, Your account has been upgraded to the Enterprise tier effective immediately. A confirmation invoice has been sent to your billing contact.',
    '[{"tool": "update_subscription_tier", "status": "SUCCESS", "details": {"old_tier": "Pro", "new_tier": "Enterprise", "effective_date": "2026-10-05"}}]',
    420, 0.0280, NOW() - INTERVAL '4 hours'
),
(
    'SEED-IDEMP-002', 'TCK-9002', 'NEXUS-TECH-04', 'ops@nexustech.io',
    'Current Account Balance and Invoice Inquiry',
    'Can you tell us our current credit balance and if we have any pending unpaid invoices?',
    'BILLING', 'MEDIUM', 'RESOLVED', 0.920,
    'Retrieved account ledger data via check_account_balance for NEXUS-TECH-04.',
    'Hello Nexus Tech Team, Your current balance is $4,250.00 USD with zero overdue invoices. Your next scheduled billing cycle is on the 1st of next month.',
    '[{"tool": "check_account_balance", "status": "SUCCESS", "details": {"balance": 4250.00, "currency": "USD", "overdue_invoices": 0}}]',
    380, 0.0240, NOW() - INTERVAL '3 hours'
),
(
    'SEED-IDEMP-003', 'TCK-9003', 'GLOBAL-LOGISTICS-09', 'dev@globallogistics.com',
    'Unclear Custom Integration Bug',
    'We are seeing intermittent 502 Bad Gateway when sending payloads from our custom ERP webhook.',
    'TECHNICAL', 'URGENT', 'ESCALATED', 0.610,
    'Confidence score 0.61 is below 0.80 threshold. Escalated to Tier-2 Engineering with diagnostics.',
    'Thank you for reporting this issue. Due to the technical nature of custom ERP webhook integrations, I have escalated this ticket directly to our Senior Integration Engineers (Ticket #TCK-9003). A specialist will follow up within 2 business hours.',
    '[]',
    310, 0.0190, NOW() - INTERVAL '2 hours'
),
(
    'SEED-IDEMP-004', 'TCK-9004', 'FINTECH-SOLUTIONS-12', 'cfo@fintechsol.com',
    'Dispute regarding prorated charge on invoice #9812',
    'We were charged $350 for additional seats that we believe were deactivated last week. Need an immediate refund.',
    'BILLING', 'HIGH', 'ESCALATED', 0.720,
    'Refund dispute requires human authorization. Escalated to Billing Department Lead.',
    'Hello, I have initiated an escalation to our Senior Billing Operations team to review invoice #9812 and the seat deactivation history. Our team will review the audit logs and respond promptly.',
    '[]',
    340, 0.0220, NOW() - INTERVAL '1 hour'
),
(
    'SEED-IDEMP-005', 'TCK-9005', 'CLOUD-DATA-07', 'admin@clouddata.io',
    'Upgrade seat limit for Starter tier',
    'We need to switch from Starter to Professional tier for 50 users.',
    'SUBSCRIPTION', 'HIGH', 'RESOLVED', 0.940,
    'Updated subscription tier to Professional tier successfully.',
    'Hello Cloud Data Team, Your subscription has been updated to the Professional tier. 50 user seats are now active.',
    '[{"tool": "update_subscription_tier", "status": "SUCCESS", "details": {"old_tier": "Starter", "new_tier": "Professional", "seats": 50}}]',
    450, 0.0270, NOW() - INTERVAL '30 minutes'
);

-- Seed execution logs for audit trail tracking
INSERT INTO execution_logs (
    ticket_id, idempotency_key, step_name, status, confidence_score, latency_ms,
    input_payload, output_payload, created_at
)
SELECT 
    id, idempotency_key, 'IDEMPOTENCY_VERIFICATION', 'SUCCESS', 1.000, 15,
    jsonb_build_object('idempotency_key', idempotency_key),
    jsonb_build_object('is_duplicate', false),
    created_at - INTERVAL '300 milliseconds'
FROM tickets;

INSERT INTO execution_logs (
    ticket_id, idempotency_key, step_name, status, confidence_score, latency_ms,
    input_payload, output_payload, created_at
)
SELECT 
    id, idempotency_key, 'LLM_INTENT_AND_TOOL_CALLING', 
    CASE WHEN status = 'RESOLVED' THEN 'SUCCESS' ELSE 'WARNING' END,
    confidence_score, execution_time_ms,
    jsonb_build_object('subject', subject, 'body', body),
    jsonb_build_object('status', status, 'confidence_score', confidence_score, 'actions', actions_taken),
    created_at
FROM tickets;
