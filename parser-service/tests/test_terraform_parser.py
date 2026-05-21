import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.terraform_parser import parse_terraform
from app.terraform_parser import parse_module_sources

def test_terragoat_files():
    folder = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "benchmarks", "terragoat")
    )

    for file in os.listdir(folder):

        if file.endswith(".tf"):

            with open(os.path.join(folder,file), encoding="utf-8") as f:

                resources = parse_terraform(f.read())

                assert isinstance(resources,list)


def test_resource_declaration_maps_source_line_and_file():
    content = '''resource "aws_security_group" "web" {
  vpc_id = "vpc-1"
}
'''
    resources = parse_terraform(content, source_file="infra/main.tf")
    assert len(resources) >= 1
    sg = next(r for r in resources if r["resource_id"] == "aws_security_group.web")
    assert sg["source_file"] == "infra/main.tf"
    assert sg["source_line"] == 1


def test_module_source_validation():
    content = """
    module "vpc" {
      source = "github.com/org/module"
    }
    """
    module_sources = parse_module_sources(content)
    assert isinstance(module_sources, list)
    assert len(module_sources) == 1
    assert module_sources[0]["flag_severity"] == "MEDIUM"