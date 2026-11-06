"""Filesystem locations shared by the API and simulation workers."""

import os
from pathlib import Path
from urllib.parse import quote


def data_dir() -> Path:
    return Path(os.environ.get("FEDSIM_DATA_DIR", "var")).expanduser().resolve()


def dataset_cache_dir() -> Path:
    configured = os.environ.get("HF_DATASETS_CACHE")
    path = Path(configured).expanduser() if configured else data_dir() / "cache" / "datasets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def evaluation_data_dir() -> Path:
    return data_dir() / "datasets"


def telemetry_dir() -> Path:
    configured = os.environ.get("FEDSIM_TELEMETRY_LOG_DIR")
    return Path(configured).expanduser() if configured else data_dir() / "logs"


def telemetry_log_path(run_id: str) -> Path:
    return telemetry_dir() / f"sim_{quote(run_id, safe='-_.')}.jsonl"


def checkpoint_path(filename: str) -> Path:
    path = Path(filename).expanduser()
    if not path.is_absolute():
        path = data_dir() / "models" / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
