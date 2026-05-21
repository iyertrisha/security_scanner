from typing import Any, List, Dict, Optional
from pydantic import BaseModel

class Rule(BaseModel):
    port: Any
    protocol: str
    cidr: str

class Resource(BaseModel):
    resource_id: str
    resource_type: str
    provider: str
    properties: Dict
    inbound_rules: List[Rule] = []
    outbound_rules: List[Rule] = []
    tags: Dict = {}
    source_file: Optional[str] = None
    source_line: Optional[int] = None


class ModuleSource(BaseModel):
    source_url: str
    version_status: str
    trust_level: str
    flag_severity: str


class ParseResponse(BaseModel):
    resources: List[Resource]
    module_sources: List[ModuleSource] = []