# NetGuard — System context diagram (Level 0)

This is a **system context** view: NetGuard is shown as one logical system with **external actors** and **external software** it depends on. For internal microservices (API, parser, graph engine, risk scorer, database, frontend), see [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Context diagram (Mermaid)

```mermaid
%%{init: {'theme': 'default'}}%%
flowchart TB
  %% External actors
  DEV(("Developer"))
  ANALYST(("Security analyst /<br/>reviewer"))

  %% External systems
  GH["GitHub<br/>Git repos & pull requests"]
  GHA["GitHub Actions<br/>CI workflow"]

  LLM["LLM API<br/>Gemini / Groq / OpenAI<br/>(enrichment & autofix)"]

  %% System under study
  subgraph NG["NetGuard platform"]
    direction TB
    NGLABEL["FastAPI microservices · PostgreSQL ·<br/>React/Vite dashboard · IaC snapshot store"]
  end

  %% Relationships
  DEV -->|"git push, open/update PR"| GH
  GH -->|"PR event"| GHA

  GHA -->|"Collect tracked .tf / .yaml / .yml;<br/>POST /api/scan with HMAC-signed body<br/>+ org API key in payload"| NG
  NG -->|"JSON: findings, severities,<br/>blocking flag, comment markdown"| GHA
  GHA -->|"Post PR comment;<br/>fail job if HIGH/CRITICAL<br/>(non-overridden)"| GH

  ANALYST -->|"HTTPS browser · UI + REST<br/>X-API-Key (local session)"| NG
  DEV -.->|"optional: signup/login,<br/>view scans in UI"| NG

  NG <-->|"LLM calls (severity ±1,<br/>explanations, fix JSON)"| LLM

  NG -.->|"optional: PAT on API host<br/>autofix diff as PR thread comment"| GH

  %% Light-mode palette (pale fills, dark text)
  style NG fill:#dbeafe,color:#0f172a,stroke:#2563eb
  style NGLABEL fill:#eff6ff,color:#0f172a,stroke:#93c5fd
  style LLM fill:#fef3c7,color:#0f172a,stroke:#d97706
  style GH fill:#f8fafc,color:#0f172a,stroke:#64748b
  style GHA fill:#e0f2fe,color:#0f172a,stroke:#0284c7
  style DEV fill:#f3e8ff,color:#0f172a,stroke:#7c3aed
  style ANALYST fill:#f3e8ff,color:#0f172a,stroke:#7c3aed
```

## Legend (narrative)

| Flow | Meaning |
|------|---------|
| **Developer → GitHub** | Changes land as commits; PRs trigger review and CI. |
| **GitHub Actions → NetGuard** | Workflow `netguard.yml` runs `scripts/post_pr_findings.py`, which calls the hosted **Backend API** over HTTPS with **HMAC** (`NETGUARD_SECRET`) and embeds the org **`api_key`** so scans are tenant-scoped without a browser session. |
| **NetGuard → GitHub Actions** | API returns structured results; the job posts a summary comment and may **exit non-zero** to block merge when policy requires it. |
| **Analyst / developer → NetGuard** | **Frontend** (e.g. port 5173) talks to the **Backend API** (e.g. port 8000) with **`X-API-Key`** after signup/login. |
| **NetGuard ↔ LLM** | **Risk scorer** enriches deterministic findings; **autofix** may request structured fix proposals. Without keys, rules still run (degraded mode). |
| **NetGuard ⇢ GitHub (dashed)** | Optional **`GITHUB_TOKEN`** on the API server: post validated autofix diffs to the PR (separate from Actions’ token used for the scan summary comment). |

## See also

- High-level component architecture: [`ARCHITECTURE.md`](./ARCHITECTURE.md) — *System Architecture* and *Deployment Architecture* sections.
- Report-oriented summary: [`MINI_PROJECT_REPORT_CONTEXT.md`](./MINI_PROJECT_REPORT_CONTEXT.md).
