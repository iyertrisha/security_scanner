"""
Pydantic models for the Graph Engine Service.

These define the 'contract' — the exact shape of data coming IN (requests)
and going OUT (responses) of the graph engine endpoints.
"""

from typing import Optional
from pydantic import BaseModel


# --- Building blocks ---

class Rule(BaseModel):
    """A single firewall/network rule on a security group."""
    port: int
    protocol: str
    cidr: str


class Resource(BaseModel):
    """A normalized infrastructure resource (server, firewall, network, etc.)."""
    resource_id: str
    type: str
    provider: str
    rules: list[Rule] = []


# --- Request models (what clients send to us) ---

class GraphBuildRequest(BaseModel):
    """Input to POST /graph/build — a list of resources to turn into a graph."""
    resources: list[Resource]


class GraphDiffRequest(BaseModel):
    """Input to POST /graph/diff — two resource lists to compare."""
    base: list[Resource]
    head: list[Resource]


# --- Response building blocks ---

class NodeResponse(BaseModel):
    """A single node in the returned graph."""
    id: str
    type: str
    provider: str
    attributes: dict = {}


class EdgeResponse(BaseModel):
    """A single edge (connection) in the returned graph."""
    source: str
    target: str
    relationship: str
    port: Optional[int] = None
    protocol: Optional[str] = None
    direction: str = "inbound"
    exposure_type: str = "private"


# --- Response models (what we send back) ---

class GraphBuildResponse(BaseModel):
    """Output of POST /graph/build — the full graph as nodes + edges."""
    nodes: list[NodeResponse]
    edges: list[EdgeResponse]
    metadata: dict


class GraphDiffResponse(BaseModel):
    """Output of POST /graph/diff — what changed between base and head."""
    added_nodes: list[str]
    removed_nodes: list[str]
    added_edges: list[EdgeResponse]
    removed_edges: list[EdgeResponse]
    modified_nodes: list[str] = []
    newly_exposed: list[str] = []
    no_longer_exposed: list[str] = []
    exposure_delta: int = 0
