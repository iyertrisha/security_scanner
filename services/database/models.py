"""
SQLAlchemy ORM models for the NetGuard database.

Tables (v3 — multi-tenancy):
  - organizations: tenant root; holds the hashed scan API key
  - users:         per-org login accounts (email + password hash)
  - repositories: GitHub repos being analyzed (scoped to an org)
  - scans:        individual PR scan runs (org-scoped; iac snapshot for autofix)
  - graphs:       serialized graph snapshots (JSONB)
  - findings:     security findings with blast radius, compliance, overrides
  - overrides:    rule override audit trail
  - evaluations:  scan evaluation metrics
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Text,
    JSON,
    Boolean,
    Float,
)
from sqlalchemy.orm import relationship

from services.database.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Organization(Base):
    """A tenant org. Issued one API key (random raw value, bcrypt-hashed at rest)."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    api_key_prefix = Column(String(32), nullable=False, index=True)
    api_key_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Organization(id={self.id}, name='{self.name}')>"


class User(Base):
    """Login user; one-to-one with Organization for the demo (one user per org)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    organization = relationship("Organization", back_populates="users")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', org_id={self.org_id})>"


class Repository(Base):
    """A GitHub repository being monitored by NetGuard (per-org)."""
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(512), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    scans = relationship("Scan", back_populates="repository", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Repository(id={self.id}, name='{self.name}')>"


class Scan(Base):
    """A single PR scan run against a repository (per-org)."""
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    pr_number = Column(Integer, nullable=True)
    commit_sha = Column(String(40), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    resolution_summary = Column(JSON, nullable=True)  # Summary of resolutions/overrides in this scan
    iac_files_snapshot = Column(JSON, nullable=True)  # path->content for autofix
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    repository = relationship("Repository", back_populates="scans")
    graphs = relationship("Graph", back_populates="scan", cascade="all, delete-orphan")
    findings = relationship(
        "Finding",
        back_populates="scan",
        cascade="all, delete-orphan",
        foreign_keys="Finding.scan_id",
    )
    evaluations = relationship("Evaluation", back_populates="scan", cascade="all, delete-orphan")
    fix_proposals = relationship(
        "FindingFixProposal",
        back_populates="scan",
        cascade="all, delete-orphan",
        foreign_keys="FindingFixProposal.scan_id",
    )

    def __repr__(self):
        return f"<Scan(id={self.id}, pr={self.pr_number}, status='{self.status}')>"


class Graph(Base):
    """A serialized graph snapshot stored as JSONB."""
    __tablename__ = "graphs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    graph_type = Column(String(20), nullable=False)  # "base" or "head"
    graph_data = Column(JSON, nullable=False)  # Full D3-compatible JSON
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    scan = relationship("Scan", back_populates="graphs")

    def __repr__(self):
        return f"<Graph(id={self.id}, type='{self.graph_type}')>"


class Finding(Base):
    """A security finding produced by the risk scorer (per-org)."""
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    finding_type = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False)  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    details = Column(JSON, nullable=True)
    
    # v2.0 additions: blast radius and tracking
    blast_radius_count = Column(Integer, nullable=True)  # Number of reachable nodes
    blast_radius_resources = Column(JSON, nullable=True)  # List of reachable resource IDs
    compliance_tags = Column(JSON, nullable=True)  # e.g., ["CIS_AWS_1.1", "NIST_AC_3"]
    is_new = Column(Boolean, default=False)  # True if newly exposed in this PR
    
    # Resolution tracking
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_in_scan_id = Column(Integer, ForeignKey("scans.id"), nullable=True)
    
    # Override tracking
    overridden = Column(Boolean, default=False)  # True if override applied
    override_id = Column(Integer, ForeignKey("overrides.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    scan = relationship("Scan", back_populates="findings", foreign_keys=[scan_id])
    override = relationship("Override", back_populates="findings", foreign_keys=[override_id])
    fix_proposals = relationship(
        "FindingFixProposal",
        back_populates="finding",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Finding(id={self.id}, type='{self.finding_type}', severity='{self.severity}', overridden={self.overridden})>"


class FindingFixProposal(Base):
    """LLM-produced fix proposal artifacts for UI + optional GitHub comment."""

    __tablename__ = "finding_fix_proposals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    finding_id = Column(Integer, ForeignKey("findings.id"), nullable=False)

    status = Column(String(32), nullable=False, default="pending")  # pending|validated|failed
    llm_proposal = Column(JSON, nullable=True)
    validation_errors = Column(JSON, nullable=True)
    patched_files_preview = Column(JSON, nullable=True)  # minimal path->snippet for UI
    regression_ok = Column(Boolean, nullable=True)
    regression_detail = Column(Text, nullable=True)
    regression_findings_digest = Column(JSON, nullable=True)
    unified_diff_preview = Column(Text, nullable=True)
    github_comment_id = Column(String(40), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow)

    scan = relationship("Scan", foreign_keys=[scan_id], back_populates="fix_proposals")
    finding = relationship("Finding", back_populates="fix_proposals")


class Override(Base):
    """Override rules for specific resources and findings."""
    __tablename__ = "overrides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    finding_type = Column(String(100), nullable=False)  # e.g., "SSH_EXPOSED_TO_PUBLIC"
    resource_pattern = Column(String(255), nullable=False)  # regex/glob for resource_id matching
    severity_override = Column(String(20), nullable=True)  # "CRITICAL", "HIGH", "MEDIUM", "LOW", or None to disable
    justification = Column(Text, nullable=True)  # Why this override was applied
    created_by = Column(String(255), nullable=True)  # User who created override
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    active = Column(Boolean, default=True)  # Whether override is currently active
    deactivated_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    findings = relationship("Finding", back_populates="override", foreign_keys="Finding.override_id")

    def __repr__(self):
        return f"<Override(id={self.id}, type='{self.finding_type}', pattern='{self.resource_pattern}', active={self.active})>"


class Evaluation(Base):
    """Evaluation metrics for a scan (TP/FP/FN, precision, recall)."""
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    
    # Legacy aggregate scoring
    truepositive_count = Column(Integer, nullable=True)  # Findings that are genuinely vulnerabilities
    falsepositive_count = Column(Integer, nullable=True)  # Findings that are not actual vulnerabilities
    falsenegative_count = Column(Integer, nullable=True)  # Actual vulnerabilities not detected
    precision = Column(Float, nullable=True)  # TP / (TP + FP)
    recall = Column(Float, nullable=True)  # TP / (TP + FN)

    # v2.0 evaluation rubric (1-5 sliders)
    accuracy = Column(Float, nullable=True)
    specificity = Column(Float, nullable=True)
    blast_radius_correctness = Column(Float, nullable=True)
    actionability = Column(Float, nullable=True)
    calibration = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    scan = relationship("Scan", back_populates="evaluations", foreign_keys=[scan_id])

    def __repr__(self):
        return f"<Evaluation(id={self.id}, scan_id={self.scan_id}, precision={self.precision}, recall={self.recall})>"
