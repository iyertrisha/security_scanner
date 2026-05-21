def sample_parser_payload():
    return {
        "resources": [
            {
                "resource_id": "aws_security_group.sg_web",
                "resource_type": "aws_security_group",
                "provider": "aws",
                "properties": {"name": "web"},
                "inbound_rules": [{"port": "22", "protocol": "tcp", "cidr": "0.0.0.0/0"}],
                "outbound_rules": [],
                "tags": {"environment": "dev"},
            }
        ],
        "module_sources": [
            {
                "source_url": "github.com/org/module",
                "version_status": "unpinned",
                "trust_level": "non_registry",
                "flag_severity": "MEDIUM",
            }
        ],
    }
