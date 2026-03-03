from __future__ import annotations

from backend.db.models import Graph
from backend.services.hierfl_simulation_builder import validate_hierfl_graph
from backend.services.spyker_simulation_builder import validate_spyker_graph


def validate_start_payload(
    architecture: str,
    graph: Graph,
    training_config: dict | None,
    simulation_settings: dict | None,
    spyker_config: dict | None,
) -> None:
    if architecture == "hierfl":
        _validate_hierfl_payload(training_config, simulation_settings)
        validate_hierfl_graph(graph)
        return
    if architecture == "spyker":
        _validate_spyker_payload(training_config, simulation_settings, spyker_config)
        validate_spyker_graph(graph)
        return
    raise ValueError("unsupported_architecture")


def _validate_hierfl_payload(
    training_config: dict | None,
    simulation_settings: dict | None,
) -> None:
    if training_config is None:
        raise ValueError("hierfl_missing_training_config")
    model_complexity = training_config.get("model_complexity")
    if model_complexity is not None:
        _parse_float_gt_zero(model_complexity, "hierfl_invalid_model_complexity")
    if simulation_settings:
        evaluate_model = bool(simulation_settings.get("evaluate_model"))
        output_filename = simulation_settings.get("output_filename")
        if evaluate_model and not output_filename:
            raise ValueError("hierfl_missing_output_filename")
        run_time_limit = simulation_settings.get("run_time_limit")
        if run_time_limit is not None:
            _parse_float_gt_zero(run_time_limit, "hierfl_invalid_run_time_limit")
        seed = simulation_settings.get("seed")
        if seed is not None:
            _parse_int_ge_zero(seed, "hierfl_invalid_seed")


def _validate_spyker_payload(
    training_config: dict | None,
    simulation_settings: dict | None,
    spyker_config: dict | None,
) -> None:
    if training_config is None:
        raise ValueError("spyker_missing_training_config")
    model_complexity = training_config.get("model_complexity")
    if model_complexity is not None:
        _parse_float_gt_zero(model_complexity, "spyker_invalid_model_complexity")
    if simulation_settings:
        evaluate_model = bool(simulation_settings.get("evaluate_model"))
        output_filename = simulation_settings.get("output_filename")
        if evaluate_model and not output_filename:
            raise ValueError("spyker_missing_output_filename")
        run_time_limit = simulation_settings.get("run_time_limit")
        if run_time_limit is not None:
            _parse_float_gt_zero(run_time_limit, "spyker_invalid_run_time_limit")
        idle_token_delay = simulation_settings.get("idle_token_delay")
        if idle_token_delay is not None:
            _parse_float_ge_zero(idle_token_delay, "spyker_invalid_idle_token_delay")
        seed = simulation_settings.get("seed")
        if seed is not None:
            _parse_int_ge_zero(seed, "spyker_invalid_seed")

    if not spyker_config:
        return
    decay_beta = spyker_config.get("decay_beta")
    min_learning_rate = spyker_config.get("min_learning_rate")
    h_inter = spyker_config.get("h_inter")
    h_intra = spyker_config.get("h_intra")
    sigmoid_phi = spyker_config.get("sigmoid_phi")
    server_learning_rate = spyker_config.get("server_learning_rate")
    tcp_rto_delay = spyker_config.get("tcp_rto_delay")
    if decay_beta is not None:
        _parse_float_ge_zero(decay_beta, "spyker_invalid_decay_beta")
    if min_learning_rate is not None:
        _parse_float_gt_zero(min_learning_rate, "spyker_invalid_min_learning_rate")
    if h_inter is not None:
        _parse_int_min_one(h_inter, "spyker_invalid_h_inter")
    if h_intra is not None:
        _parse_int_min_one(h_intra, "spyker_invalid_h_intra")
    if sigmoid_phi is not None:
        _parse_float_gt_zero(sigmoid_phi, "spyker_invalid_sigmoid_phi")
    if server_learning_rate is not None:
        _parse_float_gt_zero(server_learning_rate, "spyker_invalid_server_learning_rate")
    if tcp_rto_delay is not None:
        _parse_float_ge_zero(tcp_rto_delay, "spyker_invalid_tcp_rto_delay")


def _parse_float_gt_zero(value: object, error_code: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(error_code)
    if parsed <= 0:
        raise ValueError(error_code)
    return parsed


def _parse_float_ge_zero(value: object, error_code: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(error_code)
    if parsed < 0:
        raise ValueError(error_code)
    return parsed


def _parse_int_min_one(value: object, error_code: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(error_code)
    if parsed < 1:
        raise ValueError(error_code)
    return parsed


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
