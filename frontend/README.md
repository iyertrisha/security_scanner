# NetGuard frontend (React + Vite)

## Local development

```bash
cp .env.example .env
npm install
npm run dev
```

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | API base URL. Use `http://localhost:8000` when running the backend locally (default in `.env.example`). |
| `VITE_GITHUB_WORKFLOW_URL` | Optional link to `netguard.yml` on the Scans page. |
| `VITE_CI_REPO_LABEL` | Optional repo label in the PR scan guide. |

With `npm run dev`, Vite sets `import.meta.env.DEV` to `true`, so the app calls `http://localhost:8000` (from your `.env` or the built-in fallback). **`vercel.json` rewrites are not used locally.**

Start the API stack from the monorepo root (`docker compose up` or uvicorn on port 8000) before using signup, dashboard, or scans.

## Vercel + EC2 (production demo)

The UI is deployed at **https://net-guard-steel.vercel.app**. API traffic uses **same-origin** paths (`/api/*`) proxied to EC2 via [`vercel.json`](vercel.json):

- Browser → `https://net-guard-steel.vercel.app/api/...`
- Vercel edge → `http://13.234.87.247:8000/api/...`

**Vercel dashboard:** leave `VITE_API_BASE_URL` **unset** (or set to `https://net-guard-steel.vercel.app`). Do **not** set the raw EC2 IP or ngrok URL in Vercel env vars.

**GitHub Actions** (IaC repos) should use **direct EC2** for `NETGUARD_API_URL` (`http://13.234.87.247:8000`), not the Vercel URL, because scans can run longer than Vercel proxy timeouts.

**EC2 operator** (edit `~/mini-project/.env` manually on the server — see root `.env.example`):

- `NETGUARD_CORS_ORIGINS=https://net-guard-steel.vercel.app` (optional with same-origin proxy)
- `NETGUARD_API_URL=http://13.234.87.247:8000` (for Settings UI and CI secrets display)

PR-driven scans are posted by GitHub Actions, not the UI. The dashboard reads `GET /api/scans` and `GET /api/repos`.

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Local dev server (port 5173) |
| `npm run build` | Production build for Vercel |
| `npm run lint` | ESLint |
