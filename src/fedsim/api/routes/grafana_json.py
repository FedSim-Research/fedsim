from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from fedsim.services.evaluation_point_store import get_evaluation_rows

router = APIRouter(prefix="/grafana-json", tags=["grafana-json"])
logger = logging.getLogger(__name__)


class JsonDatasourceRange(BaseModel):
    from_: str = Field(alias="from")
    to: str
    raw: dict[str, Any] | None = None


class JsonDatasourceTarget(BaseModel):
    target: str | None = None
    refId: str | None = None
    payload: dict[str, Any] | str | None = None
    expr: str | None = None


class JsonDatasourceQueryRequest(BaseModel):
    range: JsonDatasourceRange | None = None
    rangeRaw: dict[str, Any] | None = None
    interval: str | None = None
    intervalMs: int | None = None
    maxDataPoints: int | None = None
    targets: list[JsonDatasourceTarget] = Field(default_factory=list)
    filters: list[dict[str, Any]] | None = None


class JsonDatasourceMetricOption(BaseModel):
    label: str
    value: str
    payloads: list[dict[str, Any]] | None = None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_payload(payload: dict[str, Any] | str | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return {}
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


@router.get("/")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/metrics")
def metrics(_: dict[str, Any] | None = None) -> list[JsonDatasourceMetricOption]:
    return [
        JsonDatasourceMetricOption(
            label="Evaluation Timeseries",
            value="evaluation_timeseries",
            payloads=[
                {
                    "name": "run_id",
                    "label": "Run ID Regex",
                    "type": "input",
                    "placeholder": ".*",
                },
                {
                    "name": "architecture",
                    "label": "Architecture Regex",
                    "type": "input",
                    "placeholder": ".*",
                },
            ],
        )
    ]


@router.post("/query")
def query(payload: JsonDatasourceQueryRequest) -> list[dict[str, Any]]:
    range_from = _parse_iso_datetime(payload.range.from_) if payload.range else None
    range_to = _parse_iso_datetime(payload.range.to) if payload.range else None
    start_ms = int(range_from.timestamp() * 1000) if range_from else None
    end_ms = int(range_to.timestamp() * 1000) if range_to else None

    results: list[dict[str, Any]] = []
    targets = payload.targets or [JsonDatasourceTarget(target="evaluation_timeseries")]

    for target in targets:
        target_payload = _normalize_payload(target.payload)
        run_id_regex = str(
            target_payload.get("run_id")
            or target_payload.get("run_id_regex")
            or target_payload.get("runId")
            or target_payload.get("runIdRegex")
            or ".*"
        )
        architecture_regex = str(
            target_payload.get("architecture")
            or target_payload.get("architecture_regex")
            or target_payload.get("architectureRegex")
            or ".*"
        )

        rows = get_evaluation_rows(
            run_id_regex=run_id_regex,
            architecture_regex=architecture_regex,
            start_ms=start_ms,
            end_ms=end_ms,
        )

        results.append(
            {
                "target": target.target or target.refId or "evaluation_timeseries",
                "type": "table",
                "columns": [
                    {"text": "T", "type": "number"},
                    {"text": "Acc", "type": "number"},
                    {"text": "Loss", "type": "number"},
                ],
                "rows": [
                    [
                        row["virtual_time"],
                        row["accuracy"],
                        row["loss"],
                    ]
                    for row in rows
                ],
            }
        )

    return results


@router.post("/variable")
def variable(payload: dict[str, Any] | None = None) -> list[dict[str, str]]:
    target = (payload or {}).get("payload", {}).get("target") if isinstance(payload, dict) else None
    if target == "architectures":
        return [
            {"__text": "hierarchical", "__value": "hierarchical"},
            {"__text": "spyker", "__value": "spyker"},
            {"__text": "both", "__value": "both"},
        ]
    return []


@router.post("/tag-keys")
def tag_keys() -> list[dict[str, str]]:
    return [
        {"type": "string", "text": "run_id"},
        {"type": "string", "text": "architecture"},
    ]


@router.post("/tag-values")
def tag_values(payload: dict[str, Any]) -> list[dict[str, str]]:
    key = payload.get("key")
    if key == "architecture":
        return [
            {"text": "hierarchical"},
            {"text": "spyker"},
            {"text": "both"},
        ]
    return []
