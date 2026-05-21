from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ── What we receive FROM the parser (Vinay's schema) ──────────────────────────

class Rule(BaseModel):
    port: Any          # string from Vinay ("22"), we normalise to int internally
    protocol: str
    cidr: str


class Resource(BaseModel):
    resource_id: str
    resource_type: str
    provider: str
    properties: Dict = {}
    inbound_rules: List[Rule] = []
    outbound_rules: List[Rule] = []
    tags: Dict = {}
    source_file: Optional[str] = None
    source_line: Optional[int] = None


# ── What we receive FROM the graph engine (Vineet's schema) ───────────────────

class GraphContext(BaseModel):
    nodes: List[Dict] = []
    edges: List[Dict] = []
    newly_exposed: List[str] = []
    exposure_delta: int = 0


# ── The request body for POST /score ──────────────────────────────────────────

class ScoreRequest(BaseModel):
    resources: List[Resource]
    graph_context: Optional[GraphContext] = None


# ── A single finding your service produces ────────────────────────────────────

class Finding(BaseModel):
    resource_id: str
    resource_type: str
    finding_type: str
    severity: Severity
    explanation: str
    remediation: str
    confidence_score: float = 1.0
    is_new: bool = False
    compliance_tags: List[str] = []
    overridden: bool = False
    override_justification: Optional[str] = None
    source_file: Optional[str] = None
    source_line: Optional[int] = None


def finding_location_kwargs(resource: Resource) -> dict[str, Any]:
    """Attach parser source location from resource to a Finding constructor."""
    return {"source_file": resource.source_file, "source_line": resource.source_line}


# ── The response body for POST /score ─────────────────────────────────────────

class ScoreResponse(BaseModel):
    findings: List[Finding]
    total: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int