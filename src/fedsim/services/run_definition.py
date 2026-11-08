"""Capture ordered experiment inputs independently of mutable editor graphs."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from fedsim.persistence.models import Edge, Graph, Node
from fedsim.settings import data_dir


def _decode(value: str | None):
    return None if value is None else json.loads(value)


def _encode(value):
    return None if value is None else json.dumps(value, ensure_ascii=False, allow_nan=False)


def _capture_graph(graph: Graph) -> dict[str, Any]:
    return {
        "id": graph.id,
        "name": graph.name,
        "architecture": graph.architecture,
        "metadata": _decode(graph.metadata_json),
        # List order affects server registration, token order and partition IDs.
        "nodes": [
            {
                "id": node.id,
                "type": node.type,
                "config": _decode(node.config_json),
                "position": _decode(node.position_json),
            }
            for node in graph.nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "config": _decode(edge.config_json),
            }
            for edge in graph.edges
        ],
    }


def definition_path(run_id: str) -> Path:
    return data_dir() / "exports" / "run-definitions" / f"{UUID(run_id)}.json"


@dataclass(frozen=True)
class RunDefinition:
    """Canonical JSON is immutable; every decoded execution view is independent."""

    _json: str

    @classmethod
    def capture(cls, runs: dict[str, dict[str, Any]]) -> "RunDefinition":
        if not runs or not set(runs) <= {"hierfl", "spyker"}:
            raise ValueError("run_definition_invalid_architectures")
        captured = {}
        for architecture, config in runs.items():
            graph = config["graph"]
            if graph.architecture != architecture:
                raise ValueError("run_definition_graph_architecture_mismatch")
            captured[architecture] = {
                "graph": _capture_graph(graph),
                "training_config": config.get("training_config"),
                "simulation_settings": config.get("simulation_settings"),
                "spyker_config": config.get("spyker_config"),
            }
        return cls(
            json.dumps(
                {
                    "schema_version": 1,
                    "architecture": "both" if len(runs) == 2 else next(iter(runs)),
                    "runs": captured,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self._json.encode("utf-8")).hexdigest()

    @property
    def architecture(self) -> str:
        return json.loads(self._json)["architecture"]

    def to_metadata(self) -> dict[str, Any]:
        return {"sha256": self.sha256, "definition": json.loads(self._json)}

    def configurations(self) -> dict[str, dict[str, Any]]:
        runs = json.loads(self._json)["runs"]
        for config in runs.values():
            config["graph_id"] = config.pop("graph")["id"]
        return runs

    def graph(self, architecture: str) -> Graph:
        captured = json.loads(self._json)["runs"][architecture]["graph"]
        graph = Graph(
            id=captured["id"],
            name=captured["name"],
            architecture=captured["architecture"],
            metadata_json=_encode(captured["metadata"]),
        )
        graph.nodes = [
            Node(
                id=node["id"],
                graph_id=captured["id"],
                type=node["type"],
                config_json=_encode(node["config"]),
                position_json=_encode(node["position"]),
            )
            for node in captured["nodes"]
        ]
        graph.edges = [
            Edge(
                id=edge["id"],
                graph_id=captured["id"],
                source_node_id=edge["source_node_id"],
                target_node_id=edge["target_node_id"],
                config_json=_encode(edge["config"]),
            )
            for edge in captured["edges"]
        ]
        return graph

    def archive(self, run_id: str) -> None:
        path = definition_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(self.to_metadata(), ensure_ascii=False, allow_nan=False),
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def read_archived_definition(run_id: str) -> dict[str, Any] | None:
    try:
        path = definition_path(run_id)
    except ValueError:
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    metadata = json.loads(content)
    canonical = json.dumps(
        metadata["definition"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != metadata["sha256"]:
        raise ValueError("run_definition_checksum_mismatch")
    return metadata


def delete_archived_definition(run_id: str) -> None:
    try:
        path = definition_path(run_id)
    except ValueError:
        return  # Historical run IDs need not be UUIDs and have no new archive.
    path.unlink(missing_ok=True)
