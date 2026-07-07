# NetGuard — IaC Security Analyzer

**Team 18 · MSRIT · CSP67 Mini Project**

NetGuard is a pull-request security platform for **Terraform** and **Kubernetes**. It parses infrastructure-as-code, builds a live network topology graph, scores findings with deterministic rules and optional LLM enrichment, and can propose autofixes back to GitHub PRs.

**Live demo:** [https://net-guard-msrit.vercel.app/](https://net-guard-msrit.vercel.app/)

**Sample IaC repo:** [demo-guard](https://github.com/iyertrisha/demo-guard)

---

## What NetGuard does

Modern cloud breaches often start with small IaC misconfigurations: SSH open to the internet, public S3 buckets, internet-facing EC2 instances with admin IAM roles, privileged Kubernetes pods, and more. NetGuard catches these **before merge** and gives engineers a clear path to fix them.

**Core capabilities:**

- **PR-driven scanning** — GitHub Actions collects all `.tf` / `.yaml` / `.yml` files in a branch, signs the payload with HMAC, and POSTs to the NetGuard API.
- **Topology graph** — VPCs, subnets, security groups, EC2, RDS, S3, and K8s workloads are linked as nodes and edges for blast-radius analysis.
- **Deterministic risk rules** — 11+ rules plus cross-resource chains (e.g. internet-facing EC2 + admin IAM → CRITICAL).
- **LLM enrichment** — Optional Gemini/Groq/OpenAI explanations and **Suggest fix** autofix proposals with diff preview.
- **Merge gate** — CI fails if non-overridden HIGH or CRITICAL findings remain.
- **Dashboard** — Sign up, view scan history, explore the D3 graph, run autofix, and post comments to GitHub PRs.

---

## Architecture

```
GitHub PR (demo-guard)
       │
       ▼  HMAC-signed POST /api/scan
┌──────────────────────────────────────────────────┐
│  EC2 — Docker Compose                            │
│  ┌─────┐  ┌────────┐  ┌─────────────┐  ┌──────┐ │
│  │ API │→ │ Parser │→ │Graph Engine │→ │Risk  │ │
│  │8000 │  │ 8001   │  │    8002     │  │Scorer│ │
│  └─────┘  └────────┘  └─────────────┘  │ 8003 │ │
│       │                                 └──────┘ │
│       └──────────────► PostgreSQL (5432)         │
└──────────────────────────────────────────────────┘
       ▲
       │  /api/* proxied via vercel.json
┌──────┴───────┐
│ Vercel (UI)  │  React + Vite dashboard
└──────────────┘
```

| Service | Port | Role |
|---------|------|------|
| API | 8000 | Auth, scans, autofix, GitHub comment posting |
| Parser | 8001 | IaC parsing (Terraform + Kubernetes) |
| Graph engine | 8002 | Topology graph + PR diff |
| Risk scorer | 8003 | Rules + LLM enrichment |
| PostgreSQL | 5432 | Scans, findings, fix proposals |
| Frontend (dev) | 5173 | Local Vite dev server |

---

## Prerequisites

- **Docker** and **Docker Compose** (v2)
- **Node.js 20+** and **npm** (for local frontend dev)
- **Python 3.12+** (optional, for running tests outside Docker)
- **Git** and **Git LFS** (for demo video files)

---

## Run locally

### 1. Clone and configure

```bash
git clone https://github.com/iyertrisha/security_scanner.git
cd security_scanner
git lfs pull

cp .env.example .env
```

Edit `.env` with at least:

```env
NETGUARD_API_URL=http://localhost:8000
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_from_aistudio.google.com
GEMINI_MODEL=gemini-2.5-flash
GITHUB_TOKEN=github_pat_...          # optional — Post to GitHub PR
NETGUARD_SECRET=$(openssl rand -hex 32)
```

Generate HMAC secret:

```bash
openssl rand -hex 32
```

### 2. Start the backend

```bash
docker compose up -d --build db parser graph_engine risk_scorer api
```

Wait ~1–2 minutes, then verify:

```bash
curl http://localhost:8000/health   # {"status":"ok","service":"api"}
curl http://localhost:8001/health   # parser
curl http://localhost:8002/health   # graph engine
curl http://localhost:8003/health   # risk scorer
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

### 4. Create an account

1. Go to **http://localhost:5173/signup** (not `/login` first — signup stores your API key in the browser).
2. Create an org and **copy the API key** shown once.
3. Use the dashboard: Scan History, topology graph, Suggest fix.

### 5. Run tests

```bash
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest
```

### Useful commands

```bash
# View API logs
docker compose logs -f api

# Restart after .env changes
docker compose up -d --force-recreate api risk_scorer

# Stop everything
docker compose down
```

---

## Production deployment

The live UI runs on [Vercel](https://net-guard-msrit.vercel.app/). The backend runs on **AWS EC2** via Docker Compose. Use [demo-guard](https://github.com/iyertrisha/demo-guard) as the sample IaC repo for PR scan demos.

### EC2 backend

1. Launch Ubuntu EC2 (t3.small+), open ports **22** and **8000**.
2. Install Docker, clone this repo, create `.env`:

```env
NETGUARD_API_URL=http://YOUR_EC2_PUBLIC_IP:8000
GEMINI_API_KEY=...
GITHUB_TOKEN=...
NETGUARD_SECRET=...
NETGUARD_CORS_ORIGINS=https://net-guard-msrit.vercel.app
```

3. Start backend only (no frontend container on EC2):

```bash
docker compose up -d --build db parser graph_engine risk_scorer api
curl http://localhost:8000/health
```

### Vercel frontend

Update `frontend/vercel.json` to proxy `/api/*` to your EC2 IP, then redeploy on Vercel.

```json
"destination": "http://YOUR_EC2_PUBLIC_IP:8000/api/:path*"
```

Leave `VITE_API_BASE_URL` **unset** on Vercel so the browser uses same-origin `/api/*`.

---

## Connect a GitHub IaC repo (CI pipeline)

1. **Sign up** at the [live app](https://net-guard-msrit.vercel.app/signup) or locally.
2. In **Settings**, note your **API key** and **HMAC secret** (`NETGUARD_SECRET` from server `.env`).
3. In your IaC repo (e.g. demo-guard), add GitHub Actions secrets:

| Secret | Value |
|--------|-------|
| `NETGUARD_API_URL` | `http://YOUR_EC2_IP:8000` (direct EC2, not Vercel URL) |
| `NETGUARD_SECRET` | Same as server `.env` |
| `NETGUARD_API_KEY` | From signup |
| `NETGUARD_UI_URL` | `https://net-guard-msrit.vercel.app` (optional) |

4. Copy `.github/workflows/netguard.yml` and `scripts/post_pr_findings.py` from this repo into your IaC repo.
5. Open a PR — NetGuard scans, comments on the PR, and blocks merge on HIGH/CRITICAL findings.

---

## Demo videos

Recordings are in **Git LFS** under `docs/demos/`.

| Demo | Link |
|------|------|
| Dashboard, login, and scan overview | [01-netguard-dashboard-and-scan.mov](docs/demos/01-netguard-dashboard-and-scan.mov) |
| PR scan results and findings | [02-pr-scan-and-findings.mov](docs/demos/02-pr-scan-and-findings.mov) |
| LLM autofix and post comment to GitHub PR | [03-autofix-and-github-pr-comment.mov](docs/demos/03-autofix-and-github-pr-comment.mov) |

After clone: `git lfs pull`

---

## Project layout

```
security_scanner/
├── .github/workflows/netguard.yml   # CI workflow template
├── services/                        # api, parser, graph_engine, risk_scorer, autofix, database
├── parser-service/                  # Standalone parser + benchmarks
├── frontend/                        # React UI
├── docker/                          # Dockerfiles
├── docker-compose.yml
├── migrations/
├── scripts/post_pr_findings.py      # CI scan helper
├── docs/demos/                      # Screen recordings (Git LFS)
└── tests/
```

---

## Environment variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Where | Purpose |
|----------|-------|---------|
| `GEMINI_API_KEY` | Server `.env` | LLM enrichment + autofix |
| `LLM_PROVIDER` | Server `.env` | `gemini`, `groq`, or `openai` |
| `GITHUB_TOKEN` | Server `.env` | Post autofix comments to GitHub PRs |
| `NETGUARD_SECRET` | Server `.env` + GitHub secrets | HMAC signing for CI scans |
| `NETGUARD_API_URL` | Server `.env` | Public API URL shown in Settings |
| `NETGUARD_API_KEY` | GitHub secrets only | Org API key from signup |

---

## Security note

Do not commit real API keys. Use `.env` locally and GitHub/Vercel secrets in production. The [demo-guard](https://github.com/iyertrisha/demo-guard) IaC is **intentionally vulnerable** — never apply it to a real AWS account.
