from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests
from requests.exceptions import RequestException

DEFAULT_GRAFANA_BASE_URL = "http://localhost:3000"
DOCKER_GRAFANA_BASE_URL = "http://grafana:3000"
ACCURACY_LOSS_DASHBOARD_UID = "fedsimFrontendDashboard"


def _base_urls() -> list[str]:
    configured = [
        os.getenv("FEDSIM_GRAFANA_INTERNAL_BASE_URL", "").strip(),
        os.getenv("FEDSIM_GRAFANA_BASE_URL", "").strip(),
    ]
    urls = [url.rstrip("/") for url in configured if url]
    if not urls:
        urls.append(DEFAULT_GRAFANA_BASE_URL)
    if DEFAULT_GRAFANA_BASE_URL in urls and DOCKER_GRAFANA_BASE_URL not in urls:
        urls.append(DOCKER_GRAFANA_BASE_URL)
    return urls


def _headers() -> dict[str, str]:
    token = os.getenv("FEDSIM_GRAFANA_API_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _auth() -> tuple[str, str] | None:
    user = os.getenv("FEDSIM_GRAFANA_USER")
    password = os.getenv("FEDSIM_GRAFANA_PASSWORD")
    if user and password:
        return (user, password)
    return None


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_headers())
    auth = _auth()
    if auth is not None:
        session.auth = auth
    return session


def _dashboard_payload(
    dashboard: dict[str, Any],
    *,
    run_id: str,
    architecture: str,
    range_from_ms: int,
    range_to_ms: int,
) -> dict[str, Any]:
    payload = dict(dashboard)
    payload["uid"] = None
    payload["id"] = None
    payload["title"] = f"Accuracy Loss Snapshot {run_id} {architecture}"
    payload["time"] = {
        "from": datetime.utcfromtimestamp(range_from_ms / 1000.0).isoformat() + "Z",
        "to": datetime.utcfromtimestamp(range_to_ms / 1000.0).isoformat() + "Z",
    }

    templating = payload.get("templating")
    if isinstance(templating, dict):
        templating_list = templating.get("list")
        if isinstance(templating_list, list):
            for item in templating_list:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if name == "run_id":
                    item["current"] = {"text": run_id, "value": run_id}
                elif name == "architecture":
                    item["current"] = {"text": architecture, "value": architecture}

    return payload


def create_accuracy_loss_snapshot_url(
    *,
    run_id: str,
    architecture: str,
    range_from_ms: int,
    range_to_ms: int,
) -> str | None:
    session = _session()
    for base in _base_urls():
        try:
            dashboard_resp = session.get(
                f"{base}/api/dashboards/uid/{ACCURACY_LOSS_DASHBOARD_UID}",
                timeout=10,
            )
        except RequestException:
            continue

        if dashboard_resp.status_code >= 400:
            continue

        payload = dashboard_resp.json()
        dashboard = payload.get("dashboard")
        if not isinstance(dashboard, dict):
            continue

        snapshot_payload = {
            "name": f"Accuracy Loss {run_id} {architecture}",
            "expires": 0,
            "external": False,
            "dashboard": _dashboard_payload(
                dashboard,
                run_id=run_id,
                architecture=architecture,
                range_from_ms=range_from_ms,
                range_to_ms=range_to_ms,
            ),
        }

        try:
            snapshot_resp = session.post(
                f"{base}/api/snapshots",
                json=snapshot_payload,
                timeout=15,
            )
        except RequestException:
            continue

        if snapshot_resp.status_code >= 400:
            continue

        snapshot_json = snapshot_resp.json()
        url = snapshot_json.get("url")
        if isinstance(url, str) and url.strip():
            return url
    return None
