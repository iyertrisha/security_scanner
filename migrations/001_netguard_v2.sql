CREATE TABLE IF NOT EXISTS repositories (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  url VARCHAR(512) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scans (
  id SERIAL PRIMARY KEY,
  repository_id INTEGER NOT NULL REFERENCES repositories(id),
  pr_number INTEGER,
  commit_sha VARCHAR(40),
  status VARCHAR(50) NOT NULL DEFAULT 'pending',
  resolution_summary JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS graphs (
  id SERIAL PRIMARY KEY,
  scan_id INTEGER NOT NULL REFERENCES scans(id),
  graph_type VARCHAR(20) NOT NULL,
  graph_data JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS overrides (
  id SERIAL PRIMARY KEY,
  finding_type VARCHAR(100) NOT NULL,
  resource_pattern VARCHAR(255) NOT NULL,
  severity_override VARCHAR(20),
  justification TEXT,
  created_by VARCHAR(255),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  active BOOLEAN DEFAULT TRUE,
  deactivated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS findings (
  id SERIAL PRIMARY KEY,
  scan_id INTEGER NOT NULL REFERENCES scans(id),
  finding_type VARCHAR(100) NOT NULL,
  severity VARCHAR(20) NOT NULL,
  details JSONB,
  blast_radius_count INTEGER,
  blast_radius_resources JSONB,
  compliance_tags JSONB,
  is_new BOOLEAN DEFAULT FALSE,
  resolved_at TIMESTAMPTZ,
  resolved_in_scan_id INTEGER REFERENCES scans(id),
  overridden BOOLEAN DEFAULT FALSE,
  override_id INTEGER REFERENCES overrides(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evaluations (
  id SERIAL PRIMARY KEY,
  scan_id INTEGER NOT NULL REFERENCES scans(id),
  truepositive_count INTEGER,
  falsepositive_count INTEGER,
  falsenegative_count INTEGER,
  precision FLOAT,
  recall FLOAT,
  accuracy FLOAT,
  specificity FLOAT,
  blast_radius_correctness FLOAT,
  actionability FLOAT,
  calibration FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
