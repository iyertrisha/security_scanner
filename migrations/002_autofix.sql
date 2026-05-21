-- Autofix / IaC snapshot (Postgres). Run manually if not using SQLAlchemy auto-create on empty DB.

ALTER TABLE scans ADD COLUMN IF NOT EXISTS iac_files_snapshot JSONB;

CREATE TABLE IF NOT EXISTS finding_fix_proposals (
  id SERIAL PRIMARY KEY,
  scan_id INTEGER NOT NULL REFERENCES scans(id),
  finding_id INTEGER NOT NULL REFERENCES findings(id),
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  llm_proposal JSONB,
  validation_errors JSONB,
  patched_files_preview JSONB,
  regression_ok BOOLEAN,
  regression_detail TEXT,
  regression_findings_digest JSONB,
  unified_diff_preview TEXT,
  github_comment_id VARCHAR(40),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
