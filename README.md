# NetGuard IaC Analyzer

**Team 18** — Automated Network Security Analysis and Risk Scoring for Infrastructure-as-Code Pipelines

NetGuard scans Terraform and Kubernetes configurations during pull requests, builds network topology graphs, performs PR-level graph diffing, and scores security risk using AI. Critical findings hard-block PRs from merging.

---

## Architecture

| Service | Port | Description |
|---|---|---|
| Backend API | 8000 | Orchestrates all services, persists data, serves the frontend |
| Parser Service | 8001 | Parses `.tf` and `.yaml` IaC files into normalized resources |
| Graph Engine Service | 8002 | Builds topology graphs and performs PR-level graph diffing |
| Risk Scorer Service | 8003 | Rule-based + AI scoring of security findings |
| Frontend | 5173 | React + Vite dashboard with D3.js graph visualization |
| PostgreSQL | 5432 | Persistent storage for scans, graphs, and findings |

---

## Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- Docker Desktop

---

## Local Development Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd mini-project
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env with your values (LLM_PROVIDER supports gemini, groq, or openai)
```

### 3. Python virtual environment

```bash
python3.12 -m venv venv
source venv/bin/activate       # macOS / Linux
# venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 4. Run a service locally

```bash
# From the project root, with venv activated:
uvicorn services.api.main:app --port 8000 --reload
uvicorn services.parser.main:app --port 8001 --reload
uvicorn services.graph_engine.main:app --port 8002 --reload
uvicorn services.risk_scorer.main:app --port 8003 --reload
```

Verify any service is running:
```bash
curl http://localhost:8000/health
# {"status":"ok","service":"api"}
```

**Important:** each backend process must use the port in the table above (`graph_engine` → **8002**, `risk_scorer` → **8003**). Matching `.env` URLs (`PARSER_SERVICE_URL`, `GRAPH_ENGINE_SERVICE_URL`, `RISK_SCORER_SERVICE_URL`) to the wrong process causes bogus autofix regression (parse/score failures or stale rules).

**Autofix:** after changing Python code for parser/validators/risk scorer, restart those services and trigger a **new POST /api/scan** (or rely on CI) so snapshots and downstream behavior match the upgraded stack. Chained “Suggest fix” merges prior **validated** proposals—stale DB rows from older code can skew results until you rescan.

### 5. Run the frontend

```bash
cd frontend
npm run dev
# Open http://localhost:5173
```

---

## Auth (multi-tenant demo)

NetGuard now has a self-serve signup/login that issues per-organization API keys.
Every `/api/*` request must carry an `X-API-Key` header (the frontend stores it in
`localStorage` and attaches it automatically). Public routes:

- `POST /api/auth/signup` — `{ name, email, password }` → returns `{ org_id, org_name, api_key }` **once**. Save this key.
- `POST /api/auth/login` — `{ email, password }` → verifies password, returns `api_key: null`. Your key from signup remains valid.
- `POST /api/auth/regenerate-key` — requires auth; issues a new key and invalidates the old one.
- `GET /api/me` — auth required; returns `{ org_id, org_name, user_email }`.
- `GET /health` — public, no auth.

**Key management:**
- API keys are **bcrypt-hashed** at rest and cannot be retrieved after signup.
- **Signup** returns the key **once** — you must save it immediately.
- **Login** verifies your password but does **not** return the key (bcrypt is one-way).
- If you lose your key, use `POST /api/auth/regenerate-key` to get a fresh one (invalidates the old key).
- All scan / repo / finding queries are filtered by `org_id`, so logging in
  as a different org cannot see another org's data.

**For CI/server deployments:**
- Create a dedicated "CI org" via signup.
- Save that org's API key in your `.env` as `NETGUARD_API_KEY`.
- This key remains valid until you regenerate it — it does NOT rotate on login.

### CI auth bypass for `/api/scan`

GitHub Actions does not have a UI session, so `/api/scan` accepts an HMAC-signed
request *instead of* `X-API-Key`. Steps:

1. Sign up your service org via `/api/auth/signup`, then log in to obtain a fresh API key.
2. Save that API key as the GitHub repo secret `NETGUARD_API_KEY` (alongside
   `NETGUARD_API_URL` and `NETGUARD_SECRET`).
3. The workflow's `scripts/post_pr_findings.py` embeds the key inside the signed body so
   the API can resolve which org the scan belongs to. The signature still uses
   `NETGUARD_SECRET` over the body bytes; the API verifies it before reading any field.

---

## Automatic PR Scanning

NetGuard scans **automatically** — there is no manual file upload. When you open or update a PR the workflow:

1. Checks out the PR head branch.
2. Collects **all** `.tf`, `.yaml`, and `.yml` files tracked in the branch (not just changed files) to give the scorer full infrastructure topology context.
3. Signs the payload with `NETGUARD_SECRET` and posts to `POST /api/scan`.
4. Posts a summary comment on the PR with finding counts, severities, and links.
5. **Blocks the merge** if any non-overridden HIGH or CRITICAL finding is present.

### Hosted app quick setup (customer actions only)

If you are using a hosted NetGuard deployment, customers only configure GitHub secrets.
Customers should **not** be asked to provide LLM provider keys, database credentials, or
internal service URLs.

#### Required GitHub repository secrets (customer-managed)

Add these under **Settings → Secrets and variables → Actions** in your GitHub repo:

| Secret | Required | Description |
|--------|----------|-------------|
| `NETGUARD_API_URL` | Yes | Public base URL of the running NetGuard API. No trailing `/api`. Example: `https://abcd-1.ngrok-free.app` (ngrok to port 8000). |
| `NETGUARD_SECRET` | Yes | HMAC secret for payload signing. Must be byte-for-byte identical to `NETGUARD_SECRET` in your API server `.env`. Generate: `openssl rand -hex 32`. |
| `NETGUARD_API_KEY` | Yes | Your org's NetGuard API key, provided by your NetGuard operator/admin (or obtained via `POST /api/auth/login` if you self-host). Embedded in the signed body so the API knows which org the scan belongs to. |
| `NETGUARD_UI_URL` | No | Public URL of the NetGuard frontend. Used for "View findings" links in PR comments. Defaults to `NETGUARD_API_URL` with `:8000` → `:5173`. |

#### Customer checklist

1. Receive `NETGUARD_API_URL`, `NETGUARD_SECRET`, and `NETGUARD_API_KEY` from your NetGuard operator/admin.
2. Add the three secrets in your GitHub repository.
3. Add `.github/workflows/netguard.yml` to your IaC repo.
4. Open/update a PR and review the NetGuard comment.

### Operator-only server configuration (not customer-managed)

These go in `.env` (or exported environment) on the machine/container running the Python services.
These values are managed by the NetGuard operator — **not by customer repo owners**:

| Variable | Required | Description |
|----------|----------|-------------|
| `NETGUARD_SECRET` | Yes | Same value as the GitHub secret above. Must match exactly. |
| `DATABASE_URL` | Yes | PostgreSQL connection string. Example: `postgresql://netguard:netguard@localhost:5432/netguard`. |
| `GEMINI_API_KEY` | No | Google AI Studio key for LLM enrichment (severity refinement, explanations, autofix). Without it, deterministic rules still run. |
| `LLM_PROVIDER` | No | `gemini` (default), `groq`, or `openai`. |
| `GROQ_API_KEY` | No | Needed only when `LLM_PROVIDER=groq`. |
| `OPENAI_API_KEY` | No | Needed only when `LLM_PROVIDER=openai`. |
| `GITHUB_TOKEN` | No | GitHub PAT with `repo` scope. Used by the API server to post autofix diff comments on PRs. Different from the Actions `github.token` used for scan summary comments. |
| `PARSER_SERVICE_URL` | No | Default: `http://localhost:8001`. |
| `GRAPH_ENGINE_SERVICE_URL` | No | Default: `http://localhost:8002`. |
| `RISK_SCORER_SERVICE_URL` | No | Default: `http://localhost:8003`. |

---

## Docker Compose (Full Stack)

```bash
# Copy and fill in your .env
cp .env.example .env

# Build and start all 6 containers
docker-compose up --build

# Stop everything
docker-compose down
```

Services will be available at the same ports listed in the Architecture table above.

---

## Running Tests

```bash
source venv/bin/activate
pytest
```

---

## Project Structure

```
mini-project/
├── .github/workflows/netguard.yml   # GitHub Action — triggers on PR
├── services/
│   ├── api/                         # Backend API (FastAPI, port 8000)
│   ├── parser/                      # Parser Service (FastAPI, port 8001)
│   ├── graph_engine/                # Graph Engine Service (FastAPI, port 8002)
│   └── risk_scorer/                 # Risk Scorer Service (FastAPI, port 8003)
├── frontend/                        # React + Vite + D3.js (port 5173)
├── docker/                          # Dockerfiles for each service
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

## Implementation Phases

| Phase | Description | Status |
|---|---|---|
| 0 | Project structure, venv, Docker skeleton | Done |
| 1 | AWS + Kubernetes parsers, graph construction | Pending |
| 2 | Risk scoring engine + AI integration | Pending |
| 3 | Backend API orchestration + PostgreSQL | Pending |
| 4 | Frontend dashboard | Pending |
| 5 | GitHub Action CI gate | Pending |
| 6 | Benchmarking and demo polish | Pending |

---

## Mini project report (Claude / LLM)

For the **CSP67 formal report**, the repo includes a single context pack with full architecture, stack, CI, data model, scoring rules, autofix, auth, algorithms, and discrepancies to watch for:

- **[MINI_PROJECT_REPORT_CONTEXT.md](./MINI_PROJECT_REPORT_CONTEXT.md)**
- **[LOW_LEVEL_DESIGN_DIAGRAMS.md](./LOW_LEVEL_DESIGN_DIAGRAMS.md)** — Mermaid for §6.4: scan sequence, autofix sequence, use cases, API scan flowchart
- **[DATA_MODEL_MERMAID_DIAGRAMS.md](./DATA_MODEL_MERMAID_DIAGRAMS.md)** — ER diagram, SQLAlchemy class diagram, extra flowcharts

**How to use it:** Open that file, copy its entire contents into Claude (or your preferred assistant), then copy and paste the **“Master prompt for Claude”** section at the **bottom** of the same file so the model generates the complete report following your department’s TOC (Abstract, SRS, Design, Implementation, Testing, Results, Conclusion, References).
