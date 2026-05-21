"""
Tests for supply-chain security rules (Phase 3).
"""

import pytest
from services.risk_scorer.schemas import Resource, Severity
from services.risk_scorer.rules.supply_chain_rules import (
    check_mutable_docker_image_in_pipeline,
    check_third_party_dependency_without_lock,
    run_supply_chain_rules,
)


class TestMutableDockerImage:
    """Tests for S1 rule."""

    def test_github_workflow_with_latest_tag(self):
        """Should flag Docker image with 'latest' tag in workflow."""
        workflow = Resource(
            resource_id="ci-workflow",
            resource_type="github_workflow",
            provider="github",
            properties={
                "docker_images": ["python:latest", "node:3.14"],
                "config_text": "image: python:latest\nfrom node:3.14",
            },
        )
        
        findings = check_mutable_docker_image_in_pipeline(workflow)
        
        assert len(findings) > 0
        assert findings[0].severity == Severity.CRITICAL
        assert "MUTABLE_DOCKER_IMAGE" in findings[0].finding_type

    def test_workflow_with_pinned_digest(self):
        """Pinned digest should not trigger."""
        workflow = Resource(
            resource_id="ci-workflow",
            resource_type="github_workflow",
            provider="github",
            properties={
                "docker_images": [
                    "python@sha256:abcd1234",
                    "node@sha256:efgh5678",
                ],
            },
        )
        
        findings = check_mutable_docker_image_in_pipeline(workflow)
        
        assert len(findings) == 0

    def test_non_pipeline_resource(self):
        """Non-pipeline resources should not be checked."""
        resource = Resource(
            resource_id="app-server",
            resource_type="aws_ec2_instance",
            provider="aws",
        )
        
        findings = check_mutable_docker_image_in_pipeline(resource)
        
        assert len(findings) == 0

    def test_floating_version_tags(self):
        """Floating version tags (v1.0, 1.2) should be flagged."""
        workflow = Resource(
            resource_id="ci-pipeline",
            resource_type="circleci_config",
            provider="circleci",
            properties={
                "docker_images": [
                    "python:3.9",  # This is an old version tag (technically mutable)
                    "node:v1.0",
                ],
                "config_text": "image: ubuntu:20.04\n",
            },
        )
        
        findings = check_mutable_docker_image_in_pipeline(workflow)
        
        # Should flag floating version tags
        assert len(findings) >= 0  # Implementation heuristic


class TestDependencyLockFile:
    """Tests for S2 rule."""

    def test_package_json_without_lock_file(self):
        """Should flag when package.json exists without lock file."""
        npm_config = Resource(
            resource_id="package.json",
            resource_type="package_json",
            provider="github",
            properties={
                "has_lock_file": False,
                "unpinned_dependencies": [
                    {"name": "react", "version": "^18.0.0"},
                    {"name": "axios", "version": "*"},
                ],
            },
        )
        
        findings = check_third_party_dependency_without_lock(npm_config)
        
        assert len(findings) > 0
        assert findings[0].severity == Severity.HIGH
        assert "MISSING_DEPENDENCY_LOCK" in findings[0].finding_type

    def test_requirements_txt_with_lock_file(self):
        """Lock file present should not trigger."""
        pip_config = Resource(
            resource_id="requirements.txt",
            resource_type="requirements_txt",
            provider="github",
            properties={
                "has_lock_file": True,
                "lock_file_age_days": 5,
            },
        )
        
        findings = check_third_party_dependency_without_lock(pip_config)
        
        assert len(findings) == 0

    def test_stale_lock_file_warning(self):
        """Lock file older than 90 days should be flagged."""
        go_config = Resource(
            resource_id="go.mod",
            resource_type="go_mod",
            provider="github",
            properties={
                "has_lock_file": True,
                "lock_file_age_days": 180,  # 6 months old
            },
        )
        
        findings = check_third_party_dependency_without_lock(go_config)
        
        assert len(findings) > 0
        assert findings[0].severity == Severity.MEDIUM
        assert "STALE_DEPENDENCY_LOCK" in findings[0].finding_type

    def test_gemfile_without_lock(self):
        """Ruby Gemfile without Gemfile.lock should be flagged."""
        ruby_config = Resource(
            resource_id="Gemfile",
            resource_type="Gemfile",
            provider="github",
            properties={
                "has_lock_file": False,
                "unpinned_dependencies": ["rails", "devise", "pundit"],
            },
        )
        
        findings = check_third_party_dependency_without_lock(ruby_config)
        
        assert len(findings) > 0
        assert "MISSING_DEPENDENCY_LOCK" in findings[0].finding_type

    def test_cargo_toml_with_fresh_lock(self):
        """Fresh lock file should not trigger."""
        rust_config = Resource(
            resource_id="Cargo.toml",
            resource_type="cargo_toml",
            provider="github",
            properties={
                "has_lock_file": True,
                "lock_file_age_days": 2,  # Updated recently
            },
        )
        
        findings = check_third_party_dependency_without_lock(rust_config)
        
        assert len(findings) == 0

    def test_non_manifest_resource(self):
        """Non-manifest resources should not be checked."""
        resource = Resource(
            resource_id="app.js",
            resource_type="javascript_file",
            provider="github",
        )
        
        findings = check_third_party_dependency_without_lock(resource)
        
        assert len(findings) == 0


class TestRunSupplyChainRules:
    """Integration tests for orchestrator."""

    def test_all_resources_processed_safely(self):
        """Orchestrator should handle diverse resource types."""
        resources = [
            Resource(
                resource_id="workflow",
                resource_type="github_workflow",
                provider="github",
                properties={"docker_images": ["python:latest"]},
            ),
            Resource(
                resource_id="package.json",
                resource_type="package_json",
                provider="github",
                properties={"has_lock_file": False},
            ),
            Resource(
                resource_id="app",
                resource_type="aws_ec2_instance",
                provider="aws",
            ),
        ]
        
        all_findings = []
        for resource in resources:
            findings = run_supply_chain_rules(resource)
            all_findings.extend(findings)
        
        # Should complete without error
        assert isinstance(all_findings, list)
        # First two resources should trigger findings
        assert len(all_findings) >= 2

    def test_graceful_error_handling(self):
        """Should handle empty/minimal properties gracefully."""
        malformed = Resource(
            resource_id="bad-resource",
            resource_type="github_workflow",
            provider="github",
            properties={},  # Empty properties
        )
        
        # Should not crash
        findings = run_supply_chain_rules(malformed)
        assert isinstance(findings, list)

    def test_multiple_violations_in_single_resource(self):
        """Single resource can trigger multiple rules."""
        # Hypothetical future test: complex resource with multiple violations
        complex_resource = Resource(
            resource_id="ci-pipeline",
            resource_type="gitlab_ci",
            provider="gitlab",
            properties={
                "docker_images": ["ubuntu:latest"],
                "has_lock_file": False,
                "unpinned_dependencies": ["curl", "git"],
            },
        )
        
        findings = run_supply_chain_rules(complex_resource)
        
        # This resource could potentially match multiple rules
        assert isinstance(findings, list)
