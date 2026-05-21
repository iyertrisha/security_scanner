# NetGuard — Graph Engine & Database Module

> **Status:** Core graph logic fully implemented and tested (89 tests passing).  
> **Last updated:** March 2026

---

## Table of Contents

1. [Overview](#overview)  
2. [Architecture](#architecture)  
3. [What Works (Fully Implemented)](#what-works-fully-implemented)  
4. [What Doesn't Work Yet](#what-doesnt-work-yet)  
5. [API Endpoints](#api-endpoints)  
6. [Data Models](#data-models)  
7. [Edge Rules & How the Graph Is Built](#edge-rules--how-the-graph-is-built)  
8. [Diff Logic](#diff-logic)  
9. [Database Layer](#database-layer)  
10. [Tests](#tests)  
11. [Running Locally](#running-locally)  
12. [What Needs to Change for Real Data](#what-needs-to-change-for-real-data)  
13. [File Map](#file-map)

---

## Overview

The **Graph Engine** is the core analysis service of NetGuard. It takes a list of normalized infrastructure resources (VPCs, subnets, security groups, EC2 instances, etc.) and builds a **directed network topology graph** using NetworkX. It can also **diff two graphs** (base vs head) to detect what changed in a pull request — added/removed nodes, added/removed edges, exposure changes, and attack surface delta.

The **Database Module** is a shared SQLAlchemy layer that stores graphs, scan metadata, and security findings in PostgreSQL.

---

## Architecture

```
Parser Service          Graph Engine Service          Risk Scorer
(Terraform/K8s →        (Resources → Graph →          (Graph → Findings)
 normalized JSON)        D3 JSON / Diff / Store)

         ↓                       ↓                        ↓
         └───────────── PostgreSQL (shared DB) ───────────┘
```

The graph engine is a **standalone FastAPI microservice** (port 8002) that:
- Receives normalized resources as JSON
- Builds a NetworkX DiGraph
- Serializes it to D3-compatible JSON (for the frontend)
- Can diff two graphs and report security-relevant changes
- Can persist graphs to PostgreSQL via the shared DB module

---

## What Works (Fully Implemented)

| Feature | Status | Details |
|---|---|---|
| **Pydantic request/response models** | ✅ Working | `Resource`, `Rule`, `GraphBuildRequest`, `GraphBuildResponse`, `GraphDiffRequest`, `GraphDiffResponse`, `NodeResponse`, `EdgeResponse` |
| **Graph builder** | ✅ Working | Converts resources → NetworkX DiGraph with typed nodes and edges |
| **Edge inference from type pairs** | ✅ Working | `vpc→subnet`, `subnet→ec2_instance`, `security_group→ec2_instance` |
| **Internet exposure detection** | ✅ Working | If a security group has `cidr: 0.0.0.0/0`, an `internet` node + edge is created |
| **Enriched edge attributes** | ✅ Working | Every edge has `direction`, `exposure_type`. Internet edges also have `port`, `protocol` |
| **D3 serialization** | ✅ Working | Converts NetworkX graph to `{nodes, edges, metadata}` dict |
| **Graph diffing** | ✅ Working | Set-math diff: added/removed nodes, added/removed edges |
| **Modified node detection** | ✅ Working | Detects nodes with same ID but changed attributes |
| **Exposure tracking** | ✅ Working | `newly_exposed`, `no_longer_exposed`, `exposure_delta` |
| **POST /graph/build** | ✅ Working | Accepts resources, returns D3 JSON |
| **POST /graph/diff** | ✅ Working | Accepts base + head resources, returns full diff |
| **GET /health** | ✅ Working | Returns `{"status": "ok"}` |
| **Database ORM models** | ✅ Working | 4 tables: `repositories`, `scans`, `graphs`, `findings` |
| **Database tests (SQLite)** | ✅ Working | CRUD, cascade delete, relationship navigation — all tested with in-memory SQLite |
| **Demo script** | ✅ Working | `demo.py` — builds graphs from fixtures, runs diff, prints everything |
| **89 unit tests** | ✅ All passing | Models, builder, serializer, API, differ, edge cases, database |

---

## What Doesn't Work Yet

| Feature | Status | Why |
|---|---|---|
| **POST /graph/store** | ⚠️ Needs PostgreSQL | Builds and persists a graph to DB. Works in code, but requires a running PostgreSQL instance. Will fail at runtime without it. |
| **GET /graph/{graph_id}** | ⚠️ Needs PostgreSQL | Retrieves a stored graph by ID. Same requirement. |
| **Parser → Graph Engine pipeline** | ❌ Not connected | The parser service is still a placeholder. No real Terraform/K8s files are being parsed into the `Resource` format yet. |
| **Risk Scorer consumption** | ❌ Not connected | The risk scorer doesn't read from the graph engine yet. |
| **Frontend visualization** | ❌ Not connected | The frontend exists but doesn't call the graph engine API yet. |
| **API gateway routing** | ❌ Not connected | The main API service doesn't proxy to the graph engine yet. |
| **Docker deployment** | ⚠️ Not tested end-to-end | `docker-compose.yml` is configured but the full stack hasn't been tested together. |
| **Alembic migrations** | ❌ Not set up | Tables are created via `Base.metadata.create_all()`. No migration history or schema versioning. |

---

## API Endpoints

### `GET /health`
Returns service status.

**Response:**
```json
{"status": "ok", "service": "graph_engine"}
```

### `POST /graph/build`
Build a graph from a list of resources.

**Request body:**
```json
{
  "resources": [
    {"resource_id": "vpc-1", "type": "vpc", "provider": "aws"},
    {"resource_id": "sg-1", "type": "security_group", "provider": "aws",
     "rules": [{"port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"}]},
    {"resource_id": "ec2-1", "type": "ec2_instance", "provider": "aws"}
  ]
}
```

**Response:**
```json
{
  "nodes": [
    {"id": "vpc-1", "type": "vpc", "provider": "aws"},
    {"id": "internet", "type": "internet", "provider": "global"}
  ],
  "edges": [
    {"source": "internet", "target": "sg-1", "relationship": "exposes",
     "port": 22, "protocol": "tcp", "direction": "inbound", "exposure_type": "public"},
    {"source": "sg-1", "target": "ec2-1", "relationship": "protects",
     "direction": "inbound", "exposure_type": "private"}
  ],
  "metadata": {"node_count": 4, "edge_count": 3}
}
```

### `POST /graph/diff`
Compare two resource sets and return what changed.

**Request body:**
```json
{
  "base": [ ... resources ... ],
  "head": [ ... resources ... ]
}
```

**Response:**
```json
{
  "added_nodes": ["ec2-2"],
  "removed_nodes": ["internet"],
  "added_edges": [{"source": "sg-1", "target": "ec2-2", "relationship": "protects", ...}],
  "removed_edges": [{"source": "internet", "target": "sg-1", "relationship": "exposes", ...}],
  "modified_nodes": [],
  "newly_exposed": [],
  "no_longer_exposed": ["sg-1"],
  "exposure_delta": -1
}
```

### `POST /graph/store` ⚠️ Requires PostgreSQL
Build a graph and persist it to the database.

**Query params:** `scan_id` (int, default 1), `graph_type` (str, default "base")

### `GET /graph/{graph_id}` ⚠️ Requires PostgreSQL
Retrieve a previously stored graph by ID.

---

## Data Models

### Pydantic (Request/Response)

| Model | Purpose |
|---|---|
| `Rule` | A firewall rule: `port`, `protocol`, `cidr` |
| `Resource` | A normalized infra resource: `resource_id`, `type`, `provider`, `rules[]` |
| `GraphBuildRequest` | Wraps a list of `Resource` objects |
| `GraphDiffRequest` | Wraps `base` and `head` resource lists |
| `NodeResponse` | A graph node: `id`, `type`, `provider` |
| `EdgeResponse` | A graph edge: `source`, `target`, `relationship`, `port?`, `protocol?`, `direction`, `exposure_type` |
| `GraphBuildResponse` | Full graph: `nodes[]`, `edges[]`, `metadata` |
| `GraphDiffResponse` | Diff result: added/removed nodes/edges + exposure fields |

### SQLAlchemy ORM (Database)

| Table | Columns | Notes |
|---|---|---|
| `repositories` | `id`, `name`, `url`, `created_at` | GitHub repos being monitored |
| `scans` | `id`, `repository_id` (FK), `pr_number`, `commit_sha`, `status`, `created_at` | One scan per PR |
| `graphs` | `id`, `scan_id` (FK), `graph_type`, `graph_data` (JSON), `created_at` | Stores serialized D3 graph |
| `findings` | `id`, `scan_id` (FK), `finding_type`, `severity`, `details` (JSON), `created_at` | Risk scorer output |

Cascade deletes: deleting a repository cascades to its scans → graphs + findings.

---

## Edge Rules & How the Graph Is Built

The builder (`builder.py`) creates edges based on **resource type pairs**:

| Source Type | Target Type | Relationship | Exposure |
|---|---|---|---|
| `vpc` | `subnet` | `contains` | private |
| `subnet` | `ec2_instance` | `places` | private |
| `security_group` | `ec2_instance` | `protects` | private |
| `internet` | `security_group` | `exposes` | **public** |

The `internet → security_group` edge is only created when a security group has a rule with `cidr: 0.0.0.0/0`. It carries `port`, `protocol`, `direction="inbound"`, `exposure_type="public"`.

**Current limitation:** Edge rules are hard-coded in a `EDGE_RULES` dict. They only cover AWS resource types (`vpc`, `subnet`, `ec2_instance`, `security_group`). See the "What Needs to Change" section below.

---

## Diff Logic

The differ (`differ.py`) compares two NetworkX graphs using set math:

| Field | How It's Computed |
|---|---|
| `added_nodes` | Node IDs in head but not in base |
| `removed_nodes` | Node IDs in base but not in head |
| `added_edges` | Edges (src, tgt) in head but not in base |
| `removed_edges` | Edges (src, tgt) in base but not in head |
| `modified_nodes` | Same node ID in both, but attributes differ |
| `newly_exposed` | Resources that gained an `internet → X` edge |
| `no_longer_exposed` | Resources that lost an `internet → X` edge |
| `exposure_delta` | `count(public edges in head) - count(public edges in base)` |

A **negative** `exposure_delta` means the PR reduced the attack surface. A **positive** one means it increased.

---

## Database Layer

- **Engine:** SQLAlchemy 2.0+ with `create_engine()`
- **Production DB:** PostgreSQL 14 (via Docker or external)
- **Test DB:** In-memory SQLite (automatic fallback when psycopg2 is unavailable)
- **Table creation:** `Base.metadata.create_all()` — no Alembic migrations yet
- **Connection string:** Reads `DATABASE_URL` from environment, defaults to `postgresql://netguard:netguard@localhost:5432/netguard`
- **JSON columns:** Use SQLAlchemy's generic `JSON` type (works on both PostgreSQL and SQLite)

---

## Tests

**89 tests total**, all passing.

| Test File | Count | What It Covers |
|---|---|---|
| `test_models.py` | 7 | Pydantic model parsing, validation, fixtures |
| `test_builder.py` | 14 | Node/edge creation, internet exposure, enriched edge attributes |
| `test_api.py` | 27 | All endpoints via TestClient, serializer, enriched fields, diff via API |
| `test_differ.py` | 19 | Added/removed nodes/edges, modified nodes, exposure tracking, delta |
| `test_edge_cases.py` | 12 | Unknown types, duplicates, single resources, multiple SGs, validation errors |
| `test_database.py` | 10 | Table creation, CRUD, cascade delete, relationship navigation |

Run all tests:
```powershell
py -3.13 -m pytest tests/test_graph_engine/ -v
```

---

## Running Locally

### Prerequisites
- Python 3.13+ (or 3.12+ should work)
- Required packages: `pip install fastapi uvicorn networkx pydantic sqlalchemy python-dotenv httpx pytest`

### Run the demo (no database needed)
```powershell
py -3.13 demo.py
```
This builds graphs from hardcoded fixtures, runs a diff, and prints all results including a security summary.

### Run the API server (no database needed for /build and /diff)
```powershell
py -3.13 -m uvicorn services.graph_engine.main:app --host 0.0.0.0 --port 8002 --reload
```
Then visit: http://localhost:8002/docs (Swagger UI)

### Run with PostgreSQL (for /store and /graph/{id})
```powershell
# Start PostgreSQL via Docker
docker run -d --name netguard-db -e POSTGRES_USER=netguard -e POSTGRES_PASSWORD=netguard -e POSTGRES_DB=netguard -p 5432:5432 postgres:14

# Install the PostgreSQL driver
pip install psycopg2-binary

# Set the DATABASE_URL (or create a .env file)
$env:DATABASE_URL = "postgresql://netguard:netguard@localhost:5432/netguard"

# Start the server
py -3.13 -m uvicorn services.graph_engine.main:app --host 0.0.0.0 --port 8002 --reload
```

### Run via Docker Compose (full stack)
```powershell
docker-compose up --build
```

---

## What Needs to Change for Real Data

### 1. Parser Output → Graph Engine Input

Currently the graph engine uses **hardcoded fixtures** (`fixtures.py`). In production, the **parser service** will send real resources.

**What the parser needs to produce:**

Every resource must match this schema:
```json
{
  "resource_id": "unique-id",
  "type": "vpc | subnet | ec2_instance | security_group | ...",
  "provider": "aws | gcp | azure | kubernetes",
  "rules": [
    {"port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"}
  ]
}
```

- `resource_id` — must be unique across the entire resource list
- `type` — must match a known type in `EDGE_RULES` for edges to be created
- `rules` — only relevant for `security_group` type resources; other types can omit it
- `provider` — stored as metadata on the node; not used for edge logic currently

### 2. Add More Resource Types to EDGE_RULES

The current `EDGE_RULES` dict in `builder.py` only covers 4 AWS types:

```python
EDGE_RULES = {
    ("vpc", "subnet"): "contains",
    ("subnet", "ec2_instance"): "places",
    ("security_group", "ec2_instance"): "protects",
}
```

**To support real infrastructure, add rules for:**
- `rds_instance` — e.g., `("subnet", "rds_instance"): "places"`, `("security_group", "rds_instance"): "protects"`
- `lambda_function` — e.g., `("vpc", "lambda_function"): "contains"`
- `s3_bucket` — may not have network edges, but could have policy-based edges
- `iam_role` — `("iam_role", "ec2_instance"): "assumes"`
- `load_balancer` — `("internet", "load_balancer"): "exposes"`, `("load_balancer", "ec2_instance"): "routes"`
- Kubernetes: `("namespace", "pod"): "contains"`, `("service", "pod"): "routes"`, `("ingress", "service"): "exposes"`

### 3. Internet Exposure Logic

Currently, only security groups with `cidr: 0.0.0.0/0` trigger an internet edge.

**For real data, also consider:**
- IPv6 exposure: `::/0`
- Load balancers with public IPs
- Kubernetes Ingress resources with external IPs
- S3 buckets with public ACLs
- Other cloud-specific public exposure patterns

### 4. Edge Relationship Inference

Currently edges are inferred purely from type pairs (all VPCs connect to all subnets, etc.). This works for small demos but **creates false edges in real infrastructure**.

**For real data, the parser should pass explicit relationships**, for example:
```json
{
  "resource_id": "subnet-1",
  "type": "subnet",
  "provider": "aws",
  "parent_id": "vpc-1"
}
```

Then the builder should use `parent_id` / `attached_to` / `references` fields instead of brute-force type-pair matching.

### 5. Database: Switch to Alembic Migrations

Currently tables are created via `Base.metadata.create_all()`. This is fine for dev but:
- Doesn't track schema changes
- Can't roll back
- Will silently ignore new columns on existing tables

**Action:** Set up Alembic and generate an initial migration from the existing models.

### 6. Database: JSON → JSONB for PostgreSQL

The ORM models use SQLAlchemy's generic `JSON` type for cross-database compatibility. In production on PostgreSQL, switch to `JSONB` for:
- Indexable JSON queries
- Better performance on large graph payloads
- GIN indexing for finding specific nodes/edges in stored graphs

### 7. Create a `.env` File

The database module reads `DATABASE_URL` from the environment. Create a `.env` file in the project root:
```
DATABASE_URL=postgresql://netguard:netguard@localhost:5432/netguard
```

### 8. Wire the Parser → Graph Engine → Risk Scorer Pipeline

The current flow is entirely manual (call endpoints directly). The full pipeline should be:
1. **Parser** receives Terraform/K8s files → produces normalized `Resource[]`
2. **Graph Engine** receives resources → builds graph, stores it, runs diff
3. **Risk Scorer** receives diff → produces findings
4. **API Gateway** orchestrates the above and returns results to the frontend

---

## File Map

```
services/
  graph_engine/
    models.py          ← Pydantic request/response contracts
    builder.py         ← NetworkX graph construction + edge rules
    serializer.py      ← Graph → D3 JSON conversion
    differ.py          ← Graph diffing with exposure tracking
    fixtures.py        ← Hardcoded sample data (replace with real parser output)
    main.py            ← FastAPI app with all endpoints
  database/
    database.py        ← Engine, session factory, Base class
    models.py          ← ORM models (repositories, scans, graphs, findings)

tests/
  test_graph_engine/
    test_models.py     ← Pydantic model tests
    test_builder.py    ← Graph construction tests
    test_api.py        ← Endpoint + serializer tests
    test_differ.py     ← Diff logic tests
    test_edge_cases.py ← Edge case + validation tests
    test_database.py   ← ORM + CRUD tests (SQLite in-memory)

demo.py                ← Runnable demo — build, diff, print results
docker-compose.yml     ← Full stack definition (DB, all services, frontend)
requirements.txt       ← Python dependencies
```
