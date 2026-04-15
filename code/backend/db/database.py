from pathlib import Path
import json
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import Engine

DB_DIR = Path(__file__).resolve().parent
DB_PATH = DB_DIR / "fedsim.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True
)

Base = declarative_base()

LEGACY_NODES_BACKUP = "nodes_legacy_backup"
LEGACY_EDGES_BACKUP = "edges_legacy_backup"
DEFAULT_EDGE_CONFIG_JSON = json.dumps(
    {
        "pingMs": 20,
        "jitterMs": 2,
        "packetloss": 0.001,
        "packetlossStddev": 0.0001,
    }
)

@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _table_columns(connection, table_name: str) -> set[str]:
    rows = connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _safe_json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _legacy_edge_config(source_row: dict, target_row: dict) -> str:
    source_config = _safe_json_loads(source_row.get("config_json"))
    target_config = _safe_json_loads(target_row.get("config_json"))

    preferred = source_config
    if source_row.get("type") == "ClientNode":
        preferred = source_config
    elif target_row.get("type") == "ClientNode":
        preferred = target_config
    elif source_row.get("type") == "ServerNode":
        preferred = source_config
    elif target_row.get("type") == "ServerNode":
        preferred = target_config
    elif target_config:
        preferred = target_config

    def to_int(key: str, fallback: int) -> int:
        try:
            return max(0, int(round(float(preferred.get(key, fallback)))))
        except (TypeError, ValueError):
            return fallback

    def to_fraction(key: str, fallback: float) -> float:
        try:
            value = float(preferred.get(key, fallback))
        except (TypeError, ValueError):
            return fallback
        return min(1.0, max(0.0, value))

    return json.dumps(
        {
            "pingMs": to_int("pingMs", 20),
            "jitterMs": to_int("jitterMs", 2),
            "packetloss": to_fraction("packetloss", 0.001),
            "packetlossStddev": to_fraction("packetlossStddev", 0.0001),
        }
    )


def _migrate_legacy_graph_schema() -> None:
    with engine.begin() as connection:
        table_names = {
            str(row[0])
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "nodes" not in table_names or "edges" not in table_names:
            return

        node_columns = _table_columns(connection, "nodes")
        edge_columns = _table_columns(connection, "edges")
        is_legacy_nodes = "external_id" in node_columns
        is_legacy_edges = "config_json" not in edge_columns
        if not is_legacy_nodes and not is_legacy_edges:
            return

        legacy_nodes = [
            dict(row._mapping)
            for row in connection.exec_driver_sql(
                "SELECT id, graph_id, external_id, type, config_json, position_json FROM nodes"
            ).fetchall()
        ]
        legacy_edges = [
            dict(row._mapping)
            for row in connection.exec_driver_sql(
                "SELECT id, graph_id, source_node_id, target_node_id FROM edges"
            ).fetchall()
        ]
        legacy_node_by_id = {int(row["id"]): row for row in legacy_nodes}

        if LEGACY_EDGES_BACKUP not in table_names:
            connection.exec_driver_sql(f"ALTER TABLE edges RENAME TO {LEGACY_EDGES_BACKUP}")
        else:
            connection.exec_driver_sql("DROP TABLE edges")

        if LEGACY_NODES_BACKUP not in table_names:
            connection.exec_driver_sql(f"ALTER TABLE nodes RENAME TO {LEGACY_NODES_BACKUP}")
        else:
            connection.exec_driver_sql("DROP TABLE nodes")

        Base.metadata.create_all(bind=connection)

        for row in legacy_nodes:
            connection.exec_driver_sql(
                """
                INSERT INTO nodes (id, graph_id, type, config_json, position_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(row["external_id"]),
                    int(row["graph_id"]),
                    str(row["type"]),
                    str(row["config_json"]),
                    str(row["position_json"]),
                ),
            )

        for row in legacy_edges:
            source = legacy_node_by_id.get(int(row["source_node_id"]))
            target = legacy_node_by_id.get(int(row["target_node_id"]))
            if source is None or target is None:
                continue

            connection.exec_driver_sql(
                """
                INSERT INTO edges (graph_id, source_node_id, target_node_id, config_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    int(row["graph_id"]),
                    str(source["external_id"]),
                    str(target["external_id"]),
                    _legacy_edge_config(source, target) or DEFAULT_EDGE_CONFIG_JSON,
                ),
            )


def init_db():
    _migrate_legacy_graph_schema()
    Base.metadata.create_all(engine)

if __name__ == "__main__":
    init_db()
