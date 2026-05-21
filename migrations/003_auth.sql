-- Multi-tenant auth (Postgres). Run manually if not relying on SQLAlchemy create_all.

CREATE TABLE IF NOT EXISTS organizations (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  api_key_prefix VARCHAR(32) NOT NULL,
  api_key_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_organizations_api_key_prefix ON organizations (api_key_prefix);

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);

ALTER TABLE repositories ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id);
ALTER TABLE scans        ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id);
ALTER TABLE findings     ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id);

CREATE INDEX IF NOT EXISTS ix_repositories_org_id ON repositories (org_id);
CREATE INDEX IF NOT EXISTS ix_scans_org_id        ON scans (org_id);
CREATE INDEX IF NOT EXISTS ix_findings_org_id     ON findings (org_id);
