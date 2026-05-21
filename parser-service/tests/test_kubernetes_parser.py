import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.kubernetes_parser import parse_kubernetes


def test_yaml_manifest_maps_source_line_and_file():
    content = """apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: default
spec:
  type: ClusterIP
"""
    resources = parse_kubernetes(content, source_file="k8s/svc.yaml")
    assert len(resources) >= 1
    svc = resources[0]
    assert svc["source_file"] == "k8s/svc.yaml"
    assert svc["source_line"] == 1


def test_kustomizegoat():
    folder = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "benchmarks", "kustomizegoat")
    )

    for file in os.listdir(folder):

        if file.endswith(".yaml") or file.endswith(".yml"):

            path = os.path.join(folder, file)

            # IMPORTANT: Force UTF-8
            with open(path, encoding="utf-8", errors="ignore") as f:

                resources = parse_kubernetes(f.read())

                assert isinstance(resources, list)