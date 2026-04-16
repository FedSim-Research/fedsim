from sqlalchemy import String, Text, DateTime, Float, func, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base


class Graph(Base):
    """
    Graph representation with stable node/edge IDs.
    """

    __tablename__ = "graphs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=False)
    architecture: Mapped[str] = mapped_column(String(20), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    nodes: Mapped[list["Node"]] = relationship(
        "Node",
        back_populates="graph",
        cascade="all, delete-orphan",
    )
    edges: Mapped[list["Edge"]] = relationship(
        "Edge",
        back_populates="graph",
        cascade="all, delete-orphan",
    )


class Node(Base):
    """
    Node with ID, bound to a graph.
    """

    __tablename__ = "nodes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_id: Mapped[int] = mapped_column(
        ForeignKey("graphs.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    position_json: Mapped[str] = mapped_column(Text, nullable=False)

    graph: Mapped["Graph"] = relationship("Graph", back_populates="nodes")


class Edge(Base):
    """
    Edge with ID, bound to a graph.
    """

    __tablename__ = "edges"
    __table_args__ = (
        UniqueConstraint(
            "graph_id",
            "source_node_id",
            "target_node_id",
            name="uq_edges_graph_source_target",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    graph_id: Mapped[int] = mapped_column(
        ForeignKey("graphs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    graph: Mapped["Graph"] = relationship("Graph", back_populates="edges")
    source_node: Mapped["Node"] = relationship(
        "Node",
        foreign_keys=[source_node_id],
    )
    target_node: Mapped["Node"] = relationship(
        "Node",
        foreign_keys=[target_node_id],
    )


class NodePreset(Base):
    """
    Persisted node configuration preset by architecture and node type.
    """

    __tablename__ = "node_presets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    architecture: Mapped[str] = mapped_column(String(20), nullable=False)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SimulationRun(Base):
    """
    Persisted simulation run lifecycle, metadata, and final summary.
    """

    __tablename__ = "simulation_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_id: Mapped[int | None] = mapped_column(nullable=True)
    architecture: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    queued_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
