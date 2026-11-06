import pytest
import ray
from fastapi.testclient import TestClient


def test_graph_round_trip_and_cascade_delete(api):
    created = api.post("/graphs/", json={"name": "Round trip", "architecture": "hierfl"})
    assert created.status_code == 200
    graph_id = created.json()["graph_id"]

    node_ids = []
    for kind in ("ServerNode", "ClientNode"):
        response = api.post(
            f"/graphs/{graph_id}/nodes",
            json={"type": kind, "config": {"count": 2}, "position": {"x": 1, "y": 2}},
        )
        assert response.status_code == 200
        node_ids.append(response.json()["node_id"])

    edge = api.post(
        f"/graphs/{graph_id}/edges",
        json={
            "source_node_id": node_ids[0],
            "target_node_id": node_ids[1],
            "config": {"pingMs": 10, "jitterMs": 0, "packetloss": 0, "packetlossStddev": 0},
        },
    )
    assert edge.status_code == 200
    graph = api.get(f"/graphs/{graph_id}").json()
    assert {node["node_id"] for node in graph["nodes"]} == set(node_ids)
    assert len(graph["edges"]) == 1
    assert api.get(f"/graphs/{graph_id}/vflow").json()["edges"][0]["source"] == node_ids[0]

    assert api.delete(f"/graphs/{graph_id}").json() == {"status": "deleted"}
    assert api.get(f"/graphs/{graph_id}").status_code == 404
    assert not ray.is_initialized()


def test_startup_seeds_default_topologies_and_serves_openapi(api):
    response = api.get("/graphs/")
    assert response.status_code == 200
    assert any(graph["architecture"] == "spyker" for graph in response.json())
    assert all(graph["architecture"] in {"hierfl", "spyker"} for graph in response.json())
    assert "/graphs/" in api.get("/openapi.json").json()["paths"]
    assert not ray.is_initialized()


@pytest.mark.parametrize("root_path", ["", "/api"])
def test_api_root_redirect_preserves_proxy_prefix(root_path):
    from fedsim.api.app import app

    with TestClient(
        app, root_path=root_path, base_url="http://testserver:8088", follow_redirects=False
    ) as client:
        response = client.get("/")
        assert response.status_code == 307
        assert response.headers["location"] == f"{root_path}/docs"
