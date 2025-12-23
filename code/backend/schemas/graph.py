from pydantic import BaseModel
from typing import List, Dict, Any, Literal

class GraphNodeData(BaseModel):
    """
    Data payload of a node coming from the frontend (ngx-vflow).

    - type: logical architecture type used by the backend
    - config: node-specific configuration (architecture dependent)
    """
    type: Literal["ClientNode", "ServerNode", "SuperServerNode"]
    config: Dict[str, Any]

class GraphNode(BaseModel):
    """
    A single graph node

    - id: frontend-generated ID (used for edges, normalized in backend)
    - data: node metadata and configuration
    """
    id: str
    data: GraphNodeData

class GraphEdge(BaseModel):
    """
    A directed edge between two nodes

    - source: source node ID
    - target: target node ID
    """
    source: str
    target: str

class GraphCreate(BaseModel):
    """
    Graph definition sent by the frontend

    This represents ONLY the topology:
    - no dataset
    - no model
    - no simulation parameters
    """
    architecture: Literal["spyker", "hierfl"]
    nodes: List[GraphNode]
    edges: List[GraphEdge]

class GraphResponse(BaseModel):
    """
    Response returned after persisting a graph.
    """
    graph_id: int
    architecture: str