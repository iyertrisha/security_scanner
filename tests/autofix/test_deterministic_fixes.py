"""Tests for deterministic (no-LLM) security fixes."""

from services.autofix.deterministic_fixes import try_deterministic_fix

# ── Fixtures ────────────────────────────────────────────────────────────────

SSH_SG = '''\
resource "aws_security_group" "ssh_open_to_world" {
  name   = "demo-ssh-open-to-world"
  vpc_id = aws_vpc.primary.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
'''

ALL_PORTS_SG = '''\
resource "aws_security_group" "wide_open" {
  name   = "wide-open"
  vpc_id = "vpc-1"

  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
'''

DB_SG = '''\
resource "aws_security_group" "db_exposed_to_internet" {
  name   = "demo-db-exposed-internet"
  vpc_id = aws_vpc.primary.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
'''

EBS_UNENCRYPTED = '''\
resource "aws_ebs_volume" "unencrypted_data" {
  availability_zone = "us-east-1a"
  size              = 100
  encrypted         = false
}
'''

EBS_MISSING_ENCRYPTED = '''\
resource "aws_ebs_volume" "no_enc_attr" {
  availability_zone = "us-east-1a"
  size              = 100
}
'''

MULTI_FILE = {
    "terraform/insecure_exposure.tf": SSH_SG + "\n" + DB_SG + "\n" + ALL_PORTS_SG + "\n" + EBS_UNENCRYPTED,
}


# ── SSH_EXPOSED_TO_PUBLIC ───────────────────────────────────────────────────

def test_fix_ssh_exposed():
    fm = {"sg.tf": SSH_SG}
    new_map, ok, rationale = try_deterministic_fix(
        fm, "SSH_EXPOSED_TO_PUBLIC", "aws_security_group.ssh_open_to_world", "sg.tf",
    )
    assert ok
    assert '"10.0.0.0/8"' in new_map["sg.tf"]
    assert '"0.0.0.0/0"' not in new_map["sg.tf"].split("ingress")[1].split("}")[0]
    assert "egress" in new_map["sg.tf"]
    assert "SSH" in rationale


def test_fix_ssh_preserves_egress_cidr():
    fm = {"sg.tf": SSH_SG}
    new_map, ok, _ = try_deterministic_fix(
        fm, "SSH_EXPOSED_TO_PUBLIC", "aws_security_group.ssh_open_to_world", "sg.tf",
    )
    assert ok
    egress_block = new_map["sg.tf"].split("egress")[1]
    assert '"0.0.0.0/0"' in egress_block, "egress CIDR must not be touched"


# ── ALL_PORTS_OPEN ──────────────────────────────────────────────────────────

def test_fix_all_ports_open():
    fm = {"sg.tf": ALL_PORTS_SG}
    new_map, ok, rationale = try_deterministic_fix(
        fm, "ALL_PORTS_OPEN", "aws_security_group.wide_open", "sg.tf",
    )
    assert ok
    content = new_map["sg.tf"]
    assert "from_port" in content and "443" in content
    assert "to_port" in content
    assert "65535" not in content
    assert '"10.0.0.0/8"' in content


# ── PUBLIC_DB_PORT_EXPOSED ──────────────────────────────────────────────────

def test_fix_public_db_port():
    fm = {"sg.tf": DB_SG}
    new_map, ok, rationale = try_deterministic_fix(
        fm, "PUBLIC_DB_PORT_EXPOSED", "aws_security_group.db_exposed_to_internet", "sg.tf",
    )
    assert ok
    ingress = new_map["sg.tf"].split("ingress")[1].split("}")[0]
    assert '"10.0.0.0/16"' in ingress
    assert '"0.0.0.0/0"' not in ingress


# ── UNENCRYPTED_STORAGE ────────────────────────────────────────────────────

def test_fix_unencrypted_storage_false_to_true():
    fm = {"ebs.tf": EBS_UNENCRYPTED}
    new_map, ok, _ = try_deterministic_fix(
        fm, "UNENCRYPTED_STORAGE", "aws_ebs_volume.unencrypted_data", "ebs.tf",
    )
    assert ok
    assert "encrypted         = true" in new_map["ebs.tf"] or "encrypted = true" in new_map["ebs.tf"]


def test_fix_unencrypted_storage_injects_attribute():
    fm = {"ebs.tf": EBS_MISSING_ENCRYPTED}
    new_map, ok, _ = try_deterministic_fix(
        fm, "UNENCRYPTED_STORAGE", "aws_ebs_volume.no_enc_attr", "ebs.tf",
    )
    assert ok
    assert "encrypted = true" in new_map["ebs.tf"]


# ── MISSING_TAGS ────────────────────────────────────────────────────────────

def test_fix_missing_tags_via_deterministic():
    fm = {"sg.tf": SSH_SG}
    new_map, ok, _ = try_deterministic_fix(
        fm, "MISSING_TAGS", "aws_security_group.ssh_open_to_world", "sg.tf",
    )
    assert ok
    assert "environment = var.environment" in new_map["sg.tf"]


# ── Path resolution ────────────────────────────────────────────────────────

def test_path_resolution_with_prefix():
    fm = {"terraform/sg.tf": SSH_SG}
    new_map, ok, _ = try_deterministic_fix(
        fm, "SSH_EXPOSED_TO_PUBLIC", "aws_security_group.ssh_open_to_world", "sg.tf",
    )
    assert ok, "should resolve 'sg.tf' to 'terraform/sg.tf'"
    assert '"10.0.0.0/8"' in new_map["terraform/sg.tf"]


# ── Unsupported finding type returns no-op ──────────────────────────────────

def test_unsupported_finding_type_noop():
    fm = {"sg.tf": SSH_SG}
    new_map, ok, _ = try_deterministic_fix(
        fm, "HTTP_WITHOUT_HTTPS", "aws_security_group.ssh_open_to_world", "sg.tf",
    )
    assert not ok


# ── HCL validity after fix ─────────────────────────────────────────────────

def test_all_fixes_produce_valid_hcl():
    try:
        import hcl2
    except ImportError:
        return

    cases = [
        ("SSH_EXPOSED_TO_PUBLIC", "aws_security_group.ssh_open_to_world", SSH_SG),
        ("ALL_PORTS_OPEN", "aws_security_group.wide_open", ALL_PORTS_SG),
        ("PUBLIC_DB_PORT_EXPOSED", "aws_security_group.db_exposed_to_internet", DB_SG),
        ("UNENCRYPTED_STORAGE", "aws_ebs_volume.unencrypted_data", EBS_UNENCRYPTED),
        ("UNENCRYPTED_STORAGE", "aws_ebs_volume.no_enc_attr", EBS_MISSING_ENCRYPTED),
        ("MISSING_TAGS", "aws_security_group.ssh_open_to_world", SSH_SG),
    ]
    for finding_type, rid, content in cases:
        fm = {"test.tf": content}
        new_map, ok, _ = try_deterministic_fix(fm, finding_type, rid, "test.tf")
        assert ok, f"deterministic fix should succeed for {finding_type}"
        parsed = hcl2.loads(new_map["test.tf"])
        assert parsed, f"result must be valid HCL for {finding_type}"
