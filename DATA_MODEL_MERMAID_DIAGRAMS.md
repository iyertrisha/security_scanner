# Data model & design diagrams (Mermaid)

ER diagram, ORM **class diagram**, and extra **flowcharts** for reports and `ARCHITECTURE.md`. Sources: `services/database/models.py`, `migrations/003_auth.sql`.

---

## 1. Entity–relationship diagram (database)

Reflects **organizations** / **users** (multi-tenant), **org_id** on `repositories`, `scans`, and `findings`. `graph_type` values used in code include `head`, `diff`, and `resources` (not only `base`/`head`).

```mermaid
%%{init: {'theme': 'default'}}%%
erDiagram
    ORGANIZATION ||--o{ USER : has
    ORGANIZATION ||--o{ REPOSITORY : owns
    ORGANIZATION ||--o{ SCAN : scopes
    ORGANIZATION ||--o{ FINDING : scopes

    REPOSITORY ||--o{ SCAN : has
    SCAN ||--o{ GRAPH : contains
    SCAN ||--o{ FINDING : produces
    SCAN ||--o{ EVALUATION : evaluated_by
    SCAN ||--o{ FINDING_FIX_PROPOSAL : generates
    FINDING ||--o{ FINDING_FIX_PROPOSAL : has
    FINDING }o--o| OVERRIDE : matched_override
    FINDING }o--o| SCAN : resolved_in_scan

    ORGANIZATION {
        int id PK
        string name
        string api_key_prefix
        string api_key_hash
        timestamptz created_at
    }

    USER {
        int id PK
        string email UK
        string password_hash
        int org_id FK
        timestamptz created_at
    }

    REPOSITORY {
        int id PK
        string name
        string url
        int org_id FK
        timestamptz created_at
    }

    SCAN {
        int id PK
        int repository_id FK
        int org_id FK
        int pr_number
        string commit_sha
        string status
        json resolution_summary
        json iac_files_snapshot
        timestamptz created_at
    }

    GRAPH {
        int id PK
        int scan_id FK
        string graph_type
        json graph_data
        timestamptz created_at
    }

    FINDING {
        int id PK
        int scan_id FK
        int org_id FK
        string finding_type
        string severity
        json details
        int blast_radius_count
        json blast_radius_resources
        json compliance_tags
        boolean is_new
        timestamptz resolved_at
        int resolved_in_scan_id FK
        boolean overridden
        int override_id FK
        timestamptz created_at
    }

    FINDING_FIX_PROPOSAL {
        int id PK
        int scan_id FK
        int finding_id FK
        string status
        json llm_proposal
        json validation_errors
        json patched_files_preview
        boolean regression_ok
        text regression_detail
        json regression_findings_digest
        text unified_diff_preview
        string github_comment_id
        timestamptz created_at
    }

    OVERRIDE {
        int id PK
        string finding_type
        string resource_pattern
        string severity_override
        text justification
        string created_by
        boolean active
        timestamptz created_at
        timestamptz deactivated_at
    }

    EVALUATION {
        int id PK
        int scan_id FK
        int truepositive_count
        int falsepositive_count
        int falsenegative_count
        float precision
        float recall
        float accuracy
        float specificity
        float blast_radius_correctness
        float actionability
        float calibration
        timestamptz created_at
    }
```

**Fig. D.1: ER diagram (NetGuard persistence layer)**

---

## 2. Class diagram (SQLAlchemy ORM)

Maps the same schema as **Python domain classes** in `services/database/models.py`. Suitable for object-oriented design sections.

```mermaid
%%{init: {'theme': 'default'}}%%
classDiagram
    direction TB

    class Organization {
        +int id
        +string name
        +string api_key_prefix
        +string api_key_hash
        +datetime created_at
    }

    class User {
        +int id
        +string email
        +string password_hash
        +int org_id
        +datetime created_at
    }

    class Repository {
        +int id
        +string name
        +string url
        +int org_id
        +datetime created_at
    }

    class Scan {
        +int id
        +int repository_id
        +int org_id
        +int pr_number
        +string commit_sha
        +string status
        +JSON resolution_summary
        +JSON iac_files_snapshot
        +datetime created_at
    }

    class Graph {
        +int id
        +int scan_id
        +string graph_type
        +JSON graph_data
        +datetime created_at
    }

    class Finding {
        +int id
        +int scan_id
        +int org_id
        +string finding_type
        +string severity
        +JSON details
        +int blast_radius_count
        +JSON blast_radius_resources
        +JSON compliance_tags
        +bool is_new
        +datetime resolved_at
        +int resolved_in_scan_id
        +bool overridden
        +int override_id
        +datetime created_at
    }

    class FindingFixProposal {
        +int id
        +int scan_id
        +int finding_id
        +string status
        +JSON llm_proposal
        +JSON validation_errors
        +JSON patched_files_preview
        +bool regression_ok
        +string regression_detail
        +JSON regression_findings_digest
        +string unified_diff_preview
        +string github_comment_id
        +datetime created_at
    }

    class Override {
        +int id
        +string finding_type
        +string resource_pattern
        +string severity_override
        +string justification
        +string created_by
        +bool active
        +datetime created_at
        +datetime deactivated_at
    }

    class Evaluation {
        +int id
        +int scan_id
        +int truepositive_count
        +int falsepositive_count
        +int falsenegative_count
        +float precision
        +float recall
        +float accuracy
        +float specificity
        +float blast_radius_correctness
        +float actionability
        +float calibration
        +datetime created_at
    }

    Organization "1" *-- "0..*" User : users

    Repository ..> Organization : org_id FK
    Scan ..> Organization : org_id FK
    Finding ..> Organization : org_id FK

    Repository "1" --> "0..*" Scan : scans
    Scan "1" --> "0..*" Graph : graphs
    Scan "1" --> "0..*" Finding : findings
    Scan "1" --> "0..*" Evaluation : evaluations
    Scan "1" --> "0..*" FindingFixProposal : fix_proposals

    Finding "1" --> "0..*" FindingFixProposal : fix_proposals
    Finding "0..*" --> "0..1" Override : override

    Finding ..> Scan : resolved_in_scan_id FK
```

**Fig. D.2: Class diagram (SQLAlchemy models)**

---

## 3. Flowchart — Multi-service scan orchestration (logical)

High-level view of **which service** owns each stage (complements the API-internal flowchart in [`LOW_LEVEL_DESIGN_DIAGRAMS.md`](./LOW_LEVEL_DESIGN_DIAGRAMS.md)).

```mermaid
%%{init: {'theme': 'default'}}%%
flowchart LR
    subgraph Client
        A[GitHub Actions / UI]
    end

    subgraph API["Backend API :8000"]
        O[Orchestrate + persist + authz]
    end

    subgraph Workers
        P[Parser :8001]
        G[Graph engine :8002]
        R[Risk scorer :8003]
    end

    subgraph Data
        DB[(PostgreSQL)]
    end

    subgraph External
        L[LLM API]
    end

    A -->|HTTP| O
    O -->|parse files| P
    O -->|build / diff| G
    O -->|score + optional enrich| R
    R -.->|optional| L
    O --> DB
```

**Fig. D.3: Multi-service scan orchestration flowchart**

---

## 4. Flowchart — Finding lifecycle (persisted row)

From scorer output through override matching to resolution on a later scan.

```mermaid
%%{init: {'theme': 'default'}}%%
flowchart TD
    START([Risk scorer emits finding]) --> API[API persists Finding row]
    API --> OVR{Matches active Override?}
    OVR -->|Yes| ADJ[Set overridden, severity_override]
    OVR -->|No| KEEP[Severity from scorer]
    ADJ --> STORE[Store blast_radius, compliance_tags, is_new]
    KEEP --> STORE
    STORE --> OPEN[Finding open on scan]
    OPEN --> LATER[Later scan: same PR / repo]
    LATER --> GONE{Same key absent + resource in scope?}
    GONE -->|Yes| RES[Set resolved_at, resolved_in_scan_id]
    GONE -->|No| OPEN
    RES --> END([Closed / resolved])
```

**Fig. D.4: Finding lifecycle flowchart**

---

## See also

- [**LOW_LEVEL_DESIGN_DIAGRAMS.md**](./LOW_LEVEL_DESIGN_DIAGRAMS.md) — §6.4 sequence diagrams, use cases, API scan flowchart.
- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — narrative + older ER snippet (without org/user).
- [**SYSTEM_ARCHITECTURE_CONTEXT.md**](./SYSTEM_ARCHITECTURE_CONTEXT.md) — Level-0 context diagram.
