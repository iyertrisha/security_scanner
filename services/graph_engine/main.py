import os
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from services.graph_engine.models import (
    GraphBuildRequest,
    GraphBuildResponse,
    GraphDiffRequest,
    GraphDiffResponse,
)
from services.graph_engine.builder import build_graph
from services.graph_engine.differ import diff_graphs
from services.graph_engine.serializer import serialize_graph
from services.graph_engine.subgraph import extract_subgraph, get_immediate_neighbors
from services.database.database import get_db, Base, engine
from services.database.models import Graph

import logging
import time

load_dotenv()

logger = logging.getLogger("netguard.graph_engine")

app = FastAPI(
    title="NetGuard Graph Engine Service",
    description="Builds network topology graphs from normalized resources and performs PR-level graph diffing",
    version="0.1.0",
)


@app.on_event("startup")
def _create_tables_with_retry():
    for attempt in range(1, 11):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables created/verified (attempt %d).", attempt)
            return
        except Exception as exc:
            logger.warning("create_all attempt %d failed: %s", attempt, exc)
            if attempt < 10:
                time.sleep(2)
    logger.error("Could not create tables after 10 attempts.")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "graph_engine"}


@app.post("/graph/build", response_model=GraphBuildResponse)
def graph_build(request: GraphBuildRequest):
    """
    Build a directed network topology graph from a list of resources.

    Accepts normalized resources, returns D3-compatible JSON with
    nodes, edges, and metadata.
    """
    graph = build_graph(request.resources)
    return serialize_graph(graph)


@app.post("/graph/diff", response_model=GraphDiffResponse)
def graph_diff(request: GraphDiffRequest):
    """
    Compare two resource sets (base vs head) and return what changed.

    Builds a graph for each, diffs them, and returns added/removed
    nodes and edges.
    """
    base_graph = build_graph(request.base)
    head_graph = build_graph(request.head)
    return diff_graphs(base_graph, head_graph)


@app.post("/graph/store")
def graph_store(request: GraphBuildRequest, scan_id: int = 1, graph_type: str = "base", db: Session = Depends(get_db)):
    """
    Build a graph and persist it to the database as JSONB.
    """
    graph = build_graph(request.resources)
    data = serialize_graph(graph)

    db_graph = Graph(
        scan_id=scan_id,
        graph_type=graph_type,
        graph_data=data,
    )
    db.add(db_graph)
    db.commit()
    db.refresh(db_graph)

    return {"graph_id": db_graph.id, "graph_type": db_graph.graph_type, **data}


@app.get("/graph/{graph_id}")
def graph_get(graph_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a stored graph by ID.
    """
    db_graph = db.query(Graph).filter(Graph.id == graph_id).first()
    if not db_graph:
        raise HTTPException(status_code=404, detail="Graph not found")
    return {
        "graph_id": db_graph.id,
        "graph_type": db_graph.graph_type,
        "created_at": str(db_graph.created_at),
        **db_graph.graph_data,
    }


@app.post("/graph/blast-radius")
def get_blast_radius_for_node(request: GraphBuildRequest, node_id: str):
    """
    Get the blast radius (reachable nodes) for a specific node.
    
    Query params:
    - node_id: The resource ID to compute blast radius for
    
    Returns:
    {
        "node_id": "vpc-1",
        "blast_radius": {
            "count": 5,
            "resources": ["subnet-1", "ec2-1", "rds-1", "s3-1", "backup-1"]
        }
    }
    """
    graph = build_graph(request.resources)
    
    # Extract blast radius from node attributes
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in graph")
    
    blast_data = graph.nodes[node_id].get("blast_radius", {"count": 0, "resources": []})
    
    return {
        "node_id": node_id,
        "blast_radius": blast_data,
    }


@app.post("/graph/subgraph")
def extract_graph_subgraph(request: GraphBuildRequest, center_node: str, hops: int = 2):
    """
    Extract a subgraph (neighborhood) around a specific node.
    
    Query params:
    - center_node: The resource ID to center the subgraph on
    - hops: Number of hops to include (default: 2)
    
    Returns: D3-compatible subgraph with nodes and edges within specified range
    """
    graph = build_graph(request.resources)
    
    if center_node not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node '{center_node}' not found in graph")
    
    subgraph, nodes = extract_subgraph(graph, center_node, hops=hops)
    
    return {
        "center_node": center_node,
        "hops": hops,
        **serialize_graph(subgraph),
    }


@app.post("/graph/neighbors")
def get_neighbors(request: GraphBuildRequest, node_id: str):
    """
    Get immediate predecessors and successors of a node.
    
    Query params:
    - node_id: The resource ID to get neighbors for
    
    Returns:
    {
        "node_id": "vpc-1",
        "predecessors": ["internet"],
        "successors": ["subnet-1"]
    }
    """
    graph = build_graph(request.resources)
    
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in graph")
    
    neighbors = get_immediate_neighbors(graph, node_id)
    
    return {
        "node_id": node_id,
        **neighbors,
    }

