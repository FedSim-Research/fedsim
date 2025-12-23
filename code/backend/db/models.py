from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base


class Graph(Base):
    """
    Persisted graph representation.

    A graph is uniquely identified by its hash.
    Graphs are stored in normalized form.
    """

    __tablename__ = "graphs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    architecture: Mapped[str] = mapped_column(String(20), nullable=False)

    graph_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    nodes_json: Mapped[str] = mapped_column(Text, nullable=False)
    edges_json: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )