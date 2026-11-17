"""Numeric controls shared by API preflight and direct simulation builders."""

import math
from typing import Any


def _finite_float(value: object, error_code: str) -> float:
    if isinstance(value, bool):
        raise ValueError(error_code)
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(error_code) from None
    if not math.isfinite(parsed):
        raise ValueError(error_code)
    return parsed


def parse_positive_float(value: object, error_code: str) -> float:
    parsed = _finite_float(value, error_code)
    if parsed <= 0:
        raise ValueError(error_code)
    return parsed


def parse_nonnegative_float(value: object, error_code: str) -> float:
    parsed = _finite_float(value, error_code)
    if parsed < 0:
        raise ValueError(error_code)
    return parsed


def _integer(value: object, error_code: str, minimum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(error_code)
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(error_code) from None
    if parsed < minimum or (not isinstance(value, str) and value != parsed):
        raise ValueError(error_code)
    return parsed


def parse_positive_int(value: object, error_code: str) -> int:
    return _integer(value, error_code, 1)


SPYKER_MODE_CHOICES = {
    "decay_mode": ("absolute", "relative"),
    "staleness_mode": ("reciprocal", "none", "delta", "relative"),
    "age_merge": ("monotonic", "weighted"),
}


def parse_choice(value: object, choices: tuple[str, ...], error_code: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(error_code)
    return value


def parse_bool(value: object, error_code: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(error_code)
    return value


def parse_h_inter(value: object, error_code: str) -> int | str:
    return value if value == "auto" else parse_positive_int(value, error_code)


def parse_nonnegative_int(value: object, error_code: str) -> int:
    return _integer(value, error_code, 0)


def parse_training_config(config: dict[str, Any] | None, *, prefix: str) -> dict[str, Any]:
    if config is None:
        raise ValueError(f"{prefix}_missing_training_config")
    for field in ["epochs", "lr"]:
        if config.get(field) is None:
            raise ValueError(f"{prefix}_missing_training_{field}")
    result = {
        "epochs": parse_positive_int(config["epochs"], f"{prefix}_invalid_training_epochs"),
        "lr": parse_positive_float(config["lr"], f"{prefix}_invalid_training_lr"),
    }
    for field, parser in [
        ("batch_size", parse_positive_int),
        ("model_complexity", parse_positive_float),
    ]:
        if config.get(field) is not None:
            result[field] = parser(config[field], f"{prefix}_invalid_{field}")
    return result
