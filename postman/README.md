# NetGuard Postman collection

## Contents

- `NetGuard.postman_collection.json` — One happy-path request per FastAPI endpoint across API / Parser / Graph Engine / Risk Scorer services (defaults assume localhost ports from the README).
- `NetGuard.postman_environment.json` — URLs for local development.

## Import into Postman

1. Open Postman → **Import** → drag both JSON files (or pick **Upload Files**).
2. Select environment **NetGuard Local** (upper-right environment picker).

Ensure services are running, for example:

```bash
uvicorn services.api.main:app --port 8000 --reload
# Parser microservice (port 8001) lives under parser-service
uvicorn parser-service.app.main:app --port 8001 --reload
uvicorn services.graph_engine.main:app --port 8002 --reload
uvicorn services.risk_scorer.main:app --port 8003 --reload
```

Or use Docker Compose when wired for those ports.

## Order-sensitive flows

1. Run **API → POST api/scan** first — its test script sets `scanId` on success so **GET api/scans/{scanId}** hits the same scan.
2. Run **Graph engine → POST graph/store** before **GET graph/{graphId}** — the store response updates `graphId`.
3. Run **API → POST api/overrides** before **DELETE api/overrides/{overrideId}** — creation stores `overrideId`.

## Newman (CLI)

Install [Newman](https://learning.postman.com/docs/running-collections/using-newman-cli/command-line-integration-with-newman-cli/) (`npm install -g newman`), then:

```bash
cd mini-project
newman run postman/NetGuard.postman_collection.json \
  -e postman/NetGuard.postman_environment.json \
  --delay-request 200
```

Expect failures if PostgreSQL-backed endpoints (`POST graph/store`, full **`POST api/scan`**) are used without the corresponding databases/services configured.
