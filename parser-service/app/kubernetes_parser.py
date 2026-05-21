import yaml

SUPPORTED_K8S = [
    "Service",
    "Deployment",
    "Ingress",
    "NetworkPolicy",
    "ConfigMap",
    "Namespace",
    "ServiceAccount",
    "Pod",
]


def parse_kubernetes(content: str, *, source_file: str | None = None):

    resources = []

    loader = yaml.SafeLoader(content)
    while loader.check_node():
        node = loader.compose_document()
        start_line = node.start_mark.line + 1 if getattr(node, "start_mark", None) else None
        doc = loader.construct_document(node)

        if not doc:
            continue

        kind = doc.get("kind")

        if kind not in SUPPORTED_K8S:
            continue

        metadata = doc.get("metadata", {})

        ns = metadata.get("namespace") or "default"
        rid = metadata.get("name")
        kube_type = f"kubernetes_{kind.lower()}"

        resources.append(
            {
                "resource_id": f"{ns}/{rid}" if kind != "Namespace" else rid,
                "resource_type": kube_type,
                "provider": "kubernetes",
                "properties": doc.get("spec", {}),
                "inbound_rules": [],
                "outbound_rules": [],
                "tags": metadata.get("labels", {}),
                "source_file": source_file,
                "source_line": start_line,
            }
        )

    return resources
