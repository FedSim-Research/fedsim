from typing import Any, Dict, List, Literal

from pydantic import BaseModel


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


class NetworkConfig(BaseModel):
    pingMs: int
    jitterMs: int
    packetloss: float
    packetlossStddev: float


class GraphResponse(BaseModel):
    """
    Response returned after persisting a graph.
    """

    graph_id: int
    name: str | None = None
    architecture: str
    metadata: Dict[str, Any] | None = None


class GraphRename(BaseModel):
    name: str


class GraphMetadataPatch(BaseModel):
    patch: Dict[str, Any]


class NodeCreate(BaseModel):
    type: Literal["ClientNode", "ServerNode", "SuperServerNode"]
    config: Dict[str, Any]
    position: Position


class NodeUpdate(BaseModel):
    type: Literal["ClientNode", "ServerNode", "SuperServerNode"] | None = None
    config: Dict[str, Any] | None = None
    position: Position | None = None


class NodeResponse(BaseModel):
    node_id: str
    graph_id: int
    type: str
    config: Dict[str, Any]
    position: Position


class EdgeCreate(BaseModel):
    source_node_id: str | None = None
    target_node_id: str | None = None
    config: NetworkConfig | None = None


class EdgeUpdate(BaseModel):
    config: NetworkConfig


class EdgeResponse(BaseModel):
    edge_id: int
    graph_id: int
    source_node_id: str
    target_node_id: str
    config: NetworkConfig | None = None


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
    config: NetworkConfig | None = None
    sourceHandle: str | None = None
    targetHandle: str | None = None
    reconnectable: bool = True
    floating: bool = False


class VflowGraph(BaseModel):
    nodes: List[VflowNode]
    edges: List[VflowEdge]


class PresetCreate(BaseModel):
    architecture: Literal["spyker", "hierfl"]
    node_type: Literal["SuperServerNode", "ServerNode", "ClientNode"]
    name: str
    config: Dict[str, Any]


class PresetUpdate(BaseModel):
    name: str | None = None
    config: Dict[str, Any] | None = None


class PresetResponse(BaseModel):
    preset_id: int
    architecture: Literal["spyker", "hierfl"]
    node_type: Literal["SuperServerNode", "ServerNode", "ClientNode"]
    name: str
    config: Dict[str, Any]
