"""Unit tests for autofix edit validation."""
from services.autofix.validators import (
    apply_edits,
    policy_denies_edits,
    resolve_path_to_snapshot_key,
    validate_aws_security_group_rule_blocks,
    validate_patched_terraform_syntax,
)


def test_apply_edits_all_or_nothing():
    fm = {"a.tf": 'resource "aws_vpc" "x" { cidr_block = "10.0.0.0/16" }\n'}
    edits = [
        {
            "path": "a.tf",
            "search": "10.0.0.0/16",
            "replace": "10.1.0.0/16",
        }
    ]
    new_map, errs = apply_edits(fm, edits)
    assert not errs
    assert new_map["a.tf"] != fm["a.tf"]


def test_apply_edits_rejects_short_multi_match():
    fm = {"a.tf": "foo foo"}
    edits = [{"path": "a.tf", "search": "foo", "replace": "bar"}]
    _, errs = apply_edits(fm, edits)
    assert errs


def test_apply_edits_allows_specific_multi_match():
    fm = {"a.tf": 'cidr_blocks = ["0.0.0.0/0"]\ncidr_blocks = ["0.0.0.0/0"]\n'}
    edits = [
        {
            "path": "a.tf",
            "search": 'cidr_blocks = ["0.0.0.0/0"]',
            "replace": 'cidr_blocks = ["10.0.0.0/24"]',
        }
    ]
    new_map, errs = apply_edits(fm, edits)
    assert not errs
    assert new_map["a.tf"].count('cidr_blocks = ["10.0.0.0/24"]') == 2


def test_policy_denies_widen_cidr_pattern():
    edits = [
        {
            "path": "a.tf",
            "search": 'cidr = "10.0.0.0/8"',
            "replace": 'cidr = "0.0.0.0/0"',
        }
    ]
    err = policy_denies_edits(edits)
    assert err


def test_policy_denies_placeholder_resource_identifier():
    edits = [
        {
            "path": "a.tf",
            "search": 'encrypted = false',
            "replace": 'encrypted = true\nkms_key_id = "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"',
        }
    ]
    err = policy_denies_edits(edits)
    assert err


def test_validate_patched_terraform_syntax_catches_syntax_error():
    errs = validate_patched_terraform_syntax({"x.tf": 'resource "aws_s3_bucket" "b" { bucket = "x"\n'})
    assert errs


def test_resolve_path_to_snapshot_key_suffix():
    keys = ["terraform/insecure.tf"]
    assert resolve_path_to_snapshot_key("insecure.tf", keys) == "terraform/insecure.tf"


def test_apply_edits_resolves_relative_path():
    fm = {"terraform/foo.tf": "aaa\n"}
    edits = [{"path": "foo.tf", "search": "aaa", "replace": "bbb"}]
    new_map, errs = apply_edits(fm, edits)
    assert not errs
    assert new_map["terraform/foo.tf"] == "bbb\n"


def test_validate_sg_rejects_missing_ports():
    tf = """
resource "aws_security_group" "bad" {
  vpc_id = "vpc-1"
  ingress {
    protocol = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
}
"""
    errs = validate_aws_security_group_rule_blocks({"m.tf": tf})
    assert errs
