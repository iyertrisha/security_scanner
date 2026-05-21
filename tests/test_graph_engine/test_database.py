"""
Tests for database module: ORM models and table creation.

Uses SQLite in-memory database to avoid needing PostgreSQL for tests.
Note: JSONB columns fall back to JSON in SQLite.
"""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from services.database.database import Base
from services.database.models import Repository, Scan, Graph, Finding, Override, Evaluation


def _get_test_session():
    """Create an in-memory SQLite engine/session for testing."""
    engine = create_engine("sqlite:///:memory:")
    # SQLite doesn't support JSONB, so we need to handle that
    # SQLAlchemy will fall back gracefully
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session(), engine


# --- Table creation tests ---

def test_all_six_tables_created():
    """create_all() should produce all v2.0 tables."""
    _, engine = _get_test_session()
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "repositories" in tables
    assert "scans" in tables
    assert "graphs" in tables
    assert "findings" in tables
    assert "overrides" in tables
    assert "evaluations" in tables


def test_repositories_columns():
    """repositories table should have id, name, url, created_at."""
    _, engine = _get_test_session()
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("repositories")}
    assert {"id", "name", "url", "created_at"}.issubset(columns)


def test_scans_columns():
    """scans table should have id, repository_id, pr_number, commit_sha, status, created_at."""
    _, engine = _get_test_session()
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("scans")}
    assert {
        "id",
        "repository_id",
        "pr_number",
        "commit_sha",
        "status",
        "resolution_summary",
        "created_at",
    }.issubset(columns)


def test_graphs_columns():
    """graphs table should have id, scan_id, graph_type, graph_data, created_at."""
    _, engine = _get_test_session()
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("graphs")}
    assert {"id", "scan_id", "graph_type", "graph_data", "created_at"}.issubset(columns)


def test_findings_columns():
    """findings table should have id, scan_id, finding_type, severity, details, created_at."""
    _, engine = _get_test_session()
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("findings")}
    assert {
        "id",
        "scan_id",
        "finding_type",
        "severity",
        "details",
        "blast_radius_count",
        "blast_radius_resources",
        "compliance_tags",
        "is_new",
        "resolved_at",
        "resolved_in_scan_id",
        "overridden",
        "override_id",
        "created_at",
    }.issubset(columns)


def test_overrides_columns():
    _, engine = _get_test_session()
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("overrides")}
    assert {
        "id",
        "finding_type",
        "resource_pattern",
        "severity_override",
        "justification",
        "created_by",
        "active",
        "deactivated_at",
        "created_at",
    }.issubset(columns)


def test_evaluations_columns():
    _, engine = _get_test_session()
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("evaluations")}
    assert {
        "id",
        "scan_id",
        "truepositive_count",
        "falsepositive_count",
        "falsenegative_count",
        "precision",
        "recall",
        "accuracy",
        "specificity",
        "blast_radius_correctness",
        "actionability",
        "calibration",
        "created_at",
    }.issubset(columns)


# --- CRUD tests ---

def test_insert_repository():
    """Can insert and read back a repository."""
    session, _ = _get_test_session()
    repo = Repository(name="test-repo", url="https://github.com/test/repo")
    session.add(repo)
    session.commit()
    assert repo.id is not None
    assert repo.name == "test-repo"


def test_insert_scan_with_repository():
    """A scan links to a repository via foreign key."""
    session, _ = _get_test_session()
    repo = Repository(name="test-repo", url="https://github.com/test/repo")
    session.add(repo)
    session.commit()

    scan = Scan(repository_id=repo.id, pr_number=42, commit_sha="abc1234", status="pending")
    session.add(scan)
    session.commit()
    assert scan.id is not None
    assert scan.repository_id == repo.id


def test_insert_graph_with_jsonb():
    """Can store and retrieve D3-compatible JSON as graph_data."""
    session, _ = _get_test_session()
    repo = Repository(name="test-repo", url="https://github.com/test/repo")
    session.add(repo)
    session.commit()

    scan = Scan(repository_id=repo.id, status="completed")
    session.add(scan)
    session.commit()

    graph_data = {
        "nodes": [{"id": "vpc-1", "type": "vpc"}],
        "edges": [{"source": "vpc-1", "target": "subnet-1"}],
        "metadata": {"node_count": 1, "edge_count": 1},
    }
    graph = Graph(scan_id=scan.id, graph_type="base", graph_data=graph_data)
    session.add(graph)
    session.commit()

    # Read it back
    stored = session.query(Graph).filter_by(id=graph.id).first()
    assert stored.graph_data["nodes"][0]["id"] == "vpc-1"
    assert stored.graph_type == "base"


def test_insert_finding():
    """Can insert a finding with JSONB details."""
    session, _ = _get_test_session()
    repo = Repository(name="test-repo", url="https://github.com/test/repo")
    session.add(repo)
    session.commit()

    scan = Scan(repository_id=repo.id, status="completed")
    session.add(scan)
    session.commit()

    finding = Finding(
        scan_id=scan.id,
        finding_type="internet_exposure",
        severity="critical",
        details={"resource_id": "sg-1", "port": 22, "cidr": "0.0.0.0/0"},
    )
    session.add(finding)
    session.commit()

    stored = session.query(Finding).filter_by(id=finding.id).first()
    assert stored.severity == "critical"
    assert stored.details["port"] == 22


def test_cascade_delete():
    """Deleting a repository should cascade-delete its scans, graphs, findings."""
    session, _ = _get_test_session()
    repo = Repository(name="test-repo", url="https://github.com/test/repo")
    session.add(repo)
    session.commit()

    scan = Scan(repository_id=repo.id, status="completed")
    session.add(scan)
    session.commit()

    graph = Graph(scan_id=scan.id, graph_type="base", graph_data={"nodes": []})
    finding = Finding(scan_id=scan.id, finding_type="test", severity="low", details={})
    session.add_all([graph, finding])
    session.commit()

    session.delete(repo)
    session.commit()

    assert session.query(Repository).count() == 0
    assert session.query(Scan).count() == 0
    assert session.query(Graph).count() == 0
    assert session.query(Finding).count() == 0


def test_insert_override_and_evaluation():
    session, _ = _get_test_session()
    repo = Repository(name="test-repo", url="https://github.com/test/repo")
    session.add(repo)
    session.commit()
    scan = Scan(repository_id=repo.id, status="completed")
    session.add(scan)
    session.commit()

    override = Override(
        finding_type="SSH_EXPOSED_TO_PUBLIC",
        resource_pattern="*",
        justification="temporary acceptance",
        active=True,
    )
    session.add(override)
    session.commit()

    evaluation = Evaluation(
        scan_id=scan.id,
        precision=0.8,
        recall=0.7,
        accuracy=4.0,
        specificity=3.8,
        blast_radius_correctness=4.2,
        actionability=3.9,
        calibration=3.5,
    )
    session.add(evaluation)
    session.commit()

    assert session.query(Override).count() == 1
    assert session.query(Evaluation).count() == 1


def test_scan_relationship_navigation():
    """Can navigate from scan to repository and vice versa."""
    session, _ = _get_test_session()
    repo = Repository(name="test-repo", url="https://github.com/test/repo")
    session.add(repo)
    session.commit()

    scan = Scan(repository_id=repo.id, pr_number=7, status="running")
    session.add(scan)
    session.commit()

    # Navigate scan → repository
    assert scan.repository.name == "test-repo"
    # Navigate repository → scans
    assert len(repo.scans) == 1
    assert repo.scans[0].pr_number == 7
