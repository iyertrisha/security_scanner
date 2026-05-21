# NetGuard frontend (React + Vite)

## Environment variables

Copy `.env.example` to `.env` and adjust:

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE_URL` | Base URL of the NetGuard API (default `http://localhost:8000`). |
| `VITE_GITHUB_WORKFLOW_URL` | Optional. If set, the **Scans** page shows a link to your `netguard.yml` on GitHub (e.g. `https://github.com/org/repo/blob/main/.github/workflows/netguard.yml`). |
| `VITE_CI_REPO_LABEL` | Optional display label for the repo/workflow hint (e.g. `org/repo`). Defaults to a placeholder when unset. |

PR-driven scans do not use the UI to upload files; GitHub Actions POSTs to the API. The UI lists scans from `GET /api/scans` and repositories from `GET /api/repos`.

---

## React + Vite (template)

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
