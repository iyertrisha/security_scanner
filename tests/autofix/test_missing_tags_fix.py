from services.autofix.missing_tags_fix import apply_missing_tags_terraform, canonical_basename


SAMPLE_SG = '''\
resource "aws_security_group" "svc" {
  vpc_id = "vpc-1"
}
'''

SAMPLE_SG_WITH_TAGS = '''\
resource "aws_instance" "admin_exposed" {
  ami           = "ami-abc"
  instance_type = "t3.large"

  tags = {
    Name = "demo-admin-exposed-instance"
    Data = "sensitive-customer-pii"
  }
}
'''

MULTI_RESOURCE = '''\
resource "aws_security_group" "sg_a" {
  vpc_id = "vpc-1"
}

resource "aws_security_group" "sg_b" {
  vpc_id = "vpc-2"
}
'''


def test_apply_missing_tags_injects_block():
    out, ok = apply_missing_tags_terraform(SAMPLE_SG, "aws_security_group.svc")
    assert ok
    assert "environment = var.environment" in out
    assert "owner       = var.owner" in out
    assert "project     = var.project" in out
    assert out.count("tags") == 1


def test_apply_missing_tags_merges_into_existing():
    out, ok = apply_missing_tags_terraform(SAMPLE_SG_WITH_TAGS, "aws_instance.admin_exposed")
    assert ok
    assert "environment = var.environment" in out
    assert "owner = var.owner" in out
    assert "project = var.project" in out
    assert "Name = " in out
    assert "Data = " in out
    lines = out.splitlines()
    env_line = next(l for l in lines if "environment" in l)
    name_line = next(l for l in lines if "Name" in l)
    assert len(env_line) - len(env_line.lstrip()) == len(name_line) - len(name_line.lstrip()), \
        "merged tags must share indentation with existing keys"


def test_no_double_newline_after_opening_brace():
    out, ok = apply_missing_tags_terraform(SAMPLE_SG, "aws_security_group.svc")
    assert ok
    assert "\n\n\n" not in out, "should not produce triple newlines"


def test_second_resource_still_findable():
    out1, ok1 = apply_missing_tags_terraform(MULTI_RESOURCE, "aws_security_group.sg_a")
    assert ok1
    out2, ok2 = apply_missing_tags_terraform(out1, "aws_security_group.sg_b")
    assert ok2, "second resource must be taggable after first is modified"
    assert out2.count("environment = var.environment") == 2


def test_canonical_basename_windows_style():
    assert canonical_basename(r"x\y\z.tf") == "z.tf"
