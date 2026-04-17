from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

DEFAULT_BENCHMARK_SEED_SET = [42, 43, 44, 45, 46]


def normalize_simulation_settings(
    simulation_settings: dict[str, Any] | None,
    *,
    error_prefix: str,
) -> dict[str, Any]:
    settings = dict(simulation_settings or {})
    seed_set = _normalize_seed_set(
        settings.get("seed_set"),
        settings.get("seed"),
        error_prefix=error_prefix,
    )
    repetitions = settings.get("repetitions")
    if repetitions is None:
        repetitions = len(seed_set)
    else:
        repetitions = _parse_int_min_one(repetitions, f"{error_prefix}_invalid_repetitions")
        if repetitions != len(seed_set):
            raise ValueError(f"{error_prefix}_seed_repetitions_mismatch")

    settings["seed_set"] = seed_set
    settings["repetitions"] = repetitions
    settings["seed"] = seed_set[0] if len(seed_set) == 1 else None
    return settings


def build_seeded_output_filename(
    output_filename: str | None,
    *,
    seed: int,
    repetition_index: int,
    total_repetitions: int,
) -> str | None:
    if not output_filename:
        return output_filename
    if total_repetitions <= 1:
        return output_filename

    path = Path(output_filename)
    suffix = f".seed{seed}.rep{repetition_index}"
    if path.suffix:
        return str(path.with_name(f"{path.stem}{suffix}{path.suffix}"))
    return f"{output_filename}{suffix}"


def shared_seed_set_or_raise(
    first_settings: dict[str, Any] | None,
    second_settings: dict[str, Any] | None,
) -> list[int]:
    first = list((first_settings or {}).get("seed_set") or [])
    second = list((second_settings or {}).get("seed_set") or [])
    if first != second:
        raise ValueError("combined_seed_set_mismatch")
    return first


def _normalize_seed_set(
    raw_seed_set: object,
    raw_seed: object,
    *,
    error_prefix: str,
) -> list[int]:
    if raw_seed_set is None:
        if raw_seed is not None:
            return [_parse_seed(raw_seed, error_prefix=error_prefix)]
        return list(DEFAULT_BENCHMARK_SEED_SET)

    if not isinstance(raw_seed_set, Iterable) or isinstance(raw_seed_set, (str, bytes)):
        raise ValueError(f"{error_prefix}_invalid_seed_set")

    normalized: list[int] = []
    for value in raw_seed_set:
        seed = _parse_seed(value, error_prefix=error_prefix)
        normalized.append(seed)

    if not normalized:
        raise ValueError(f"{error_prefix}_invalid_seed_set")
    return normalized


def _parse_seed(value: object, *, error_prefix: str) -> int:
    return _parse_int_ge_zero(value, f"{error_prefix}_invalid_seed")


def _parse_int_ge_zero(value: object, error_code: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(error_code)
    if parsed < 0:
        raise ValueError(error_code)
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(error_code)
    return parsed


def _parse_int_min_one(value: object, error_code: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(error_code)
    if parsed < 1:
        raise ValueError(error_code)
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(error_code)
    return parsed
