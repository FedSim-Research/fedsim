from pydantic import BaseModel
from typing import List, Dict, Any, Literal


class GraphCreate(BaseModel):
    """
    Graph creation.
    """
    name: str | None = None
    architecture: Literal["spyker", "hierfl"]
    metadata: Dict[str, Any] | None = None


class Position(BaseModel):
    x: float
    y: float


class GraphResponse(BaseModel):
    """
    Response returned after persisting a graph.
    """
    graph_id: int
    name: str | None = None
    architecture: str
    metadata: Dict[str, Any] | None = None


class NodeCreate(BaseModel):
    external_id: str | None = None
    type: Literal["ClientNode", "ServerNode", "SuperServerNode"]
    config: Dict[str, Any]
    position: Position


class NodeUpdate(BaseModel):
    type: Literal["ClientNode", "ServerNode", "SuperServerNode"] | None = None
    config: Dict[str, Any] | None = None
    position: Position | None = None


class NodeResponse(BaseModel):
    node_id: int
    graph_id: int
    external_id: str
    type: str
    config: Dict[str, Any]
    position: Position


class EdgeCreate(BaseModel):
    source_node_id: int | None = None
    target_node_id: int | None = None
    source_external_id: str | None = None
    target_external_id: str | None = None


class EdgeResponse(BaseModel):
    edge_id: int
    graph_id: int
    source_node_id: int
    target_node_id: int


class GraphDetail(BaseModel):
    graph_id: int
    name: str | None = None
    architecture: str
    metadata: Dict[str, Any] | None = None
    nodes: List[NodeResponse]
    edges: List[EdgeResponse]


class VflowNodeData(BaseModel):
    type: Literal["ClientNode", "ServerNode", "SuperServerNode"]
    config: Dict[str, Any]
    environment: str | None = None
    fromJson: bool = True
    selected: bool = False


class VflowNode(BaseModel):
    id: str
    point: Position
    type: str
    data: VflowNodeData


class VflowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None
    reconnectable: bool = True
    floating: bool = False


class VflowGraph(BaseModel):
    nodes: List[VflowNode]
    edges: List[VflowEdge]
