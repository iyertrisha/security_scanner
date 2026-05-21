"""
Supply-chain security rules (Phase 3 Part 2) — check IaC & dependencies.

These rules detect supply-chain vulnerabilities in CI/CD pipelines and
dependency management.

BLOCKED: These rules require Parser service outputs (Person 1).
Implemented with mock/placeholder logic for now.
Each function takes: Resource → List[Finding]
"""

from typing import List

from ..schemas import Resource, Finding, Severity, finding_location_kwargs as _loc


def check_mutable_docker_image_in_pipeline(resource: Resource) -> List[Finding]:
    """
    Rule S1 — Mutable Docker image tags in pipeline → CRITICAL
    
    Docker images without pinned digests are vulnerable to supply chain attacks.
    Attacker can push malicious 'latest' tag and inject code into builds.
    
    REQUIRES: Parser to extract Dockerfile/CI pipeline configs
    """
    findings = []
    
    # Only check CI/CD pipeline resources
    if resource.resource_type not in ("github_workflow", "gitlab_ci", "circleci_config", "buildkite_config"):
        return findings
    
    # Check for mutable image references
    docker_images = resource.properties.get("docker_images", [])
    cicd_config = resource.properties.get("config_text", "")
    
    mutable_images = []
    mutability_risks = {}
    
    for image in docker_images:
        # Check for 'latest' tag or no tag
        if "latest" in image or ":" not in image:
            mutable_images.append(image)
            mutability_risks[image] = "uses 'latest' or no tag"
        
        # Check for floating major/minor versions
        if any(tag in image for tag in [":v1.", ":1.", ":latest", ":master", ":main"]):
            mutable_images.append(image)
            mutability_risks[image] = "uses floating version tag"
    
    # Also check for mutable refs in config text
    for line in cicd_config.split("\n"):
        if "image:" in line.lower() or "from" in line.lower():
            # Simple heuristic: if no @ (digest ref) and no pin, it's mutable
            if "@" not in line and ("latest" in line or line.strip().endswith((":latest", ":"))):
                mutable_images.append(line.strip())
    
    if mutable_images:
        findings.append(Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="MUTABLE_DOCKER_IMAGE",
            severity=Severity.CRITICAL,
            explanation=(
                f"Pipeline uses {len(mutable_images)} mutable Docker image reference(s). "
                "Attackers can publish malicious versions and inject code into your builds."
            ),
            remediation=(
                "Pin Docker images to specific digests (e.g., image@sha256:abc123). "
                "Use image scanning (Trivy, Grype) in build stages. "
                "Sign images with Docker Content Trust. "
                "Use private image registries with access controls."
            ),
            **_loc(resource),
        ))
    
    return findings


def check_third_party_dependency_without_lock(resource: Resource) -> List[Finding]:
    """
    Rule S2 — Third-party dependencies without lock file → HIGH
    
    Dependencies downloaded without pinned versions are vulnerable to:
    - Dependency confusion attacks
    - Typosquatting
    - Compromised maintainer accounts
    
    REQUIRES: Parser to extract package manifests (package.json, requirements.txt, go.mod, etc.)
    """
    findings = []
    
    # Check if this is a package manifest
    if resource.resource_type not in (
        "package_json",
        "requirements_txt",
        "go_mod",
        "Gemfile",
        "pom_xml",
        "package_php",
        "cargo_toml",
    ):
        return findings
    
    # Check for presence of lock file
    has_lock_file = resource.properties.get("has_lock_file", False)
    
    if has_lock_file:
        # Lock file exists, check its freshness
        lock_file_age = resource.properties.get("lock_file_age_days", 0)
        
        if lock_file_age > 90:
            findings.append(Finding(
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                finding_type="STALE_DEPENDENCY_LOCK",
                severity=Severity.MEDIUM,
                explanation=(
                    f"Lock file is {lock_file_age} days old. "
                    "Dependencies may have been compromised or superseded by patches."
                ),
                remediation=(
                    "Update lock file regularly (at least monthly). "
                    "Use dependabot or renovate to automate updates. "
                    "Review security advisories for all dependencies."
                ),
                **_loc(resource),
            ))
        
        return findings
    
    # No lock file found
    unpinned_dependencies = resource.properties.get("unpinned_dependencies", [])
    
    findings.append(Finding(
        resource_id=resource.resource_id,
        resource_type=resource.resource_type,
        finding_type="MISSING_DEPENDENCY_LOCK",
        severity=Severity.HIGH,
        explanation=(
            f"No lock file found. {len(unpinned_dependencies) if unpinned_dependencies else 'All'} dependencies "
            "are unpinned, allowing arbitrary version downloads. "
            "Vulnerable to dependency confusion and supply chain attacks."
        ),
        remediation=(
            "Generate and commit lock files: npm ci, pip freeze, go mod tidy, etc. "
            "Use reproducible builds with dependency verification. "
            "Scan dependencies with safety/snyk for known CVEs. "
            "Use private package mirrors / nexus repository to audit packages."
        ),
        **_loc(resource),
    ))
    
    return findings


# Master orchestrator
def run_supply_chain_rules(resource: Resource) -> list[Finding]:
    """
    Run all supply-chain rules.
    
    NOTE: These rules require Parser outputs (Person 1's responsibility).
    Currently implemented with heuristic matching on available properties.
    """
    findings = []
    
    rule_functions = [
        check_mutable_docker_image_in_pipeline,
        check_third_party_dependency_without_lock,
    ]
    
    for rule_fn in rule_functions:
        try:
            results = rule_fn(resource)
            findings.extend(results)
        except Exception:
            # Gracefully handle errors
            pass
    
    return findings
