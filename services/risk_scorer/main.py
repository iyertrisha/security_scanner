import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from .schemas import ScoreRequest, ScoreResponse, Severity
from .rules.rules import run_all_rules
from .rules.cross_resource_rules import run_cross_resource_rules_bulk
from .llm.client import enrich_finding
from services.database.database import SessionLocal
from services.database.models import Override

load_dotenv()

_LLM_POOL = ThreadPoolExecutor(max_workers=8)

app = FastAPI(
    title="NetGuard Risk Scorer Service",
    description="Scores security findings using rule-based checks augmented by AI explanations",
    version="0.1.0",
)

COMPLIANCE_TAG_MAP = {
    "SSH_EXPOSED_TO_PUBLIC": ["CIS_AWS", "NIST_AC", "SOC2_CC", "PCI_DSS"],
    "RDP_EXPOSED_TO_PUBLIC": ["CIS_AWS", "NIST_AC", "SOC2_CC", "PCI_DSS"],
    "PUBLIC_DB_PORT_EXPOSED": ["CIS_AWS", "NIST_SC", "PCI_DSS"],
    "PUBLIC_S3_BUCKET": ["CIS_AWS", "NIST_SC", "SOC2_CC"],
    "ALL_PORTS_OPEN": ["CIS_AWS", "NIST_AC"],
    "HTTP_WITHOUT_HTTPS": ["CIS_AWS", "NIST_SC", "PCI_DSS"],
    "PERMISSIVE_IAM_POLICY": ["CIS_AWS", "NIST_AC", "SOC2_CC"],
    "MISSING_NETWORK_POLICY": ["CIS_KUBERNETES", "NIST_SC"],
    "PRIVILEGED_CONTAINER": ["CIS_KUBERNETES", "NIST_AC"],
    "UNAUTHENTICATED_SERVICE": ["CIS_KUBERNETES", "SOC2_CC"],
    "UNENCRYPTED_STORAGE": ["CIS_AWS", "NIST_SC", "PCI_DSS"],
    "MISSING_TAGS": ["SOC2_CC"],
    "INTERNET_EXPOSED_ADMIN_EC2": ["NIST_AC", "NIST_SC", "SOC2_CC", "PCI_DSS"],
    "PRIVILEGED_EC2_TO_SENSITIVE_DB": ["NIST_AC", "NIST_SC", "PCI_DSS"],
    "PUBLIC_CHAIN_TO_DATABASE": ["NIST_SC", "PCI_DSS"],
    "OVERPERMISSIVE_SG_CHAIN": ["CIS_AWS", "NIST_AC"],
    "CROSS_AZ_REPLICATION_EXPOSURE": ["CIS_AWS", "NIST_SC"],
    "LATERAL_MOVEMENT_VIA_SG": ["NIST_AC", "SOC2_CC"],
    "MUTABLE_DOCKER_IMAGE": ["NIST_SA", "NIST_SR"],
    "MISSING_DEPENDENCY_LOCK": ["NIST_SA", "NIST_SR"],
    "STALE_DEPENDENCY_LOCK": ["NIST_SA", "NIST_SR"],
}


def _apply_override(finding, resource_id: str):
    db = SessionLocal()
    try:
        override = None
        try:
            override = (
                db.query(Override)
                .filter(
                    Override.active.is_(True),
                    Override.finding_type == finding.finding_type,
                )
                .order_by(Override.created_at.desc())
                .first()
            )
        except Exception:
            return finding
        if not override:
            return finding

        pattern = override.resource_pattern or ""
        if pattern not in ("", "*") and pattern not in resource_id:
            return finding

        finding.overridden = True
        finding.override_justification = override.justification
        if override.severity_override:
            finding.severity = Severity(override.severity_override)
        return finding
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "risk_scorer"}


@app.post("/score", response_model=ScoreResponse)
async def score_resources(request: ScoreRequest):
    """
    Main endpoint — receives a list of resources (from the parser)
    and an optional graph context (from the graph engine).
    Returns all security findings with severity + AI explanations.
    
    Runs three layers:
    1. Phase 1: 11 single-resource deterministic rules
    2. Phase 3: 5 cross-resource rules (uses graph context)
    3. Phase 3: 2 supply-chain rules

    LLM enrichment is parallelized to keep total latency under ngrok/CI timeouts.
    """
    if not request.resources:
        raise HTTPException(status_code=400, detail="No resources provided.")

    resource_by_id = {resource.resource_id: resource for resource in request.resources}
    loop = asyncio.get_event_loop()

    # Phase 1+2: collect all per-resource findings (deterministic, fast).
    pending_enrichments: list[tuple] = []
    for resource in request.resources:
        findings = run_all_rules(
            resource,
            request.graph_context,
            request.resources,
            include_cross_resource=False,
        )
        for finding in findings:
            pending_enrichments.append((finding, resource))

    # Phase 3: cross-resource findings.
    cross_findings = run_cross_resource_rules_bulk(request.resources, request.graph_context)
    for finding in cross_findings:
        owner = resource_by_id.get(finding.resource_id)
        if owner is None and request.resources:
            owner = request.resources[0]
        if owner is None:
            continue
        pending_enrichments.append((finding, owner))

    # LLM enrichment in parallel via thread pool (Gemini SDK is sync).
    async def _enrich(finding, resource):
        enriched = await loop.run_in_executor(
            _LLM_POOL,
            enrich_finding, finding, resource, request.graph_context,
        )
        enriched.compliance_tags = COMPLIANCE_TAG_MAP.get(enriched.finding_type, [])
        enriched = _apply_override(enriched, resource.resource_id)
        return enriched

    all_findings = await asyncio.gather(
        *[_enrich(f, r) for f, r in pending_enrichments]
    )

    return ScoreResponse(
        findings=list(all_findings),
        total=len(all_findings),
        critical_count=sum(1 for f in all_findings if f.severity == Severity.CRITICAL),
        high_count=sum(1 for f in all_findings if f.severity == Severity.HIGH),
        medium_count=sum(1 for f in all_findings if f.severity == Severity.MEDIUM),
        low_count=sum(1 for f in all_findings if f.severity == Severity.LOW),
    )