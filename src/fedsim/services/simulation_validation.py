from __future__ import annotations

from fedsim.persistence.models import Graph
from fedsim.services.hierfl_simulation_builder import validate_hierfl_graph
from fedsim.services.input_values import parse_nonnegative_float as _parse_float_ge_zero
from fedsim.services.input_values import parse_nonnegative_int as _parse_int_ge_zero
from fedsim.services.input_values import parse_positive_float as _parse_float_gt_zero
from fedsim.services.input_values import parse_positive_int as _parse_int_min_one
from fedsim.services.input_values import parse_training_config
from fedsim.services.spyker_simulation_builder import validate_spyker_graph


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
    parse_training_config(training_config, prefix="hierfl")
    if simulation_settings:
        evaluate_model = bool(simulation_settings.get("evaluate_model"))
        output_filename = simulation_settings.get("output_filename")
        if evaluate_model and not output_filename:
            raise ValueError("hierfl_missing_output_filename")
        run_time_limit = simulation_settings.get("run_time_limit")
        if run_time_limit is not None:
            _parse_float_gt_zero(run_time_limit, "hierfl_invalid_run_time_limit")
        eval_interval = simulation_settings.get("eval_interval")
        if eval_interval is not None:
            _parse_float_ge_zero(eval_interval, "hierfl_invalid_eval_interval")
        gpu_budget = simulation_settings.get("gpu_budget")
        if gpu_budget is not None:
            _parse_float_ge_zero(gpu_budget, "hierfl_invalid_gpu_budget")
        dataset = simulation_settings.get("dataset")
        if dataset is not None:
            _validate_dataset_id(dataset, "hierfl_invalid_dataset")
        seed = simulation_settings.get("seed")
        if seed is not None:
            _parse_int_ge_zero(seed, "hierfl_invalid_seed")
        _validate_seed_controls(simulation_settings, "hierfl")


def _validate_spyker_payload(
    training_config: dict | None,
    simulation_settings: dict | None,
    spyker_config: dict | None,
) -> None:
    parse_training_config(training_config, prefix="spyker")
    if simulation_settings:
        evaluate_model = bool(simulation_settings.get("evaluate_model"))
        output_filename = simulation_settings.get("output_filename")
        if evaluate_model and not output_filename:
            raise ValueError("spyker_missing_output_filename")
        run_time_limit = simulation_settings.get("run_time_limit")
        if run_time_limit is not None:
            _parse_float_gt_zero(run_time_limit, "spyker_invalid_run_time_limit")
        eval_interval = simulation_settings.get("eval_interval")
        if eval_interval is not None:
            _parse_float_ge_zero(eval_interval, "spyker_invalid_eval_interval")
        idle_token_delay = simulation_settings.get("idle_token_delay")
        if idle_token_delay is not None:
            _parse_float_ge_zero(idle_token_delay, "spyker_invalid_idle_token_delay")
        gpu_budget = simulation_settings.get("gpu_budget")
        if gpu_budget is not None:
            _parse_float_ge_zero(gpu_budget, "spyker_invalid_gpu_budget")
        dataset = simulation_settings.get("dataset")
        if dataset is not None:
            _validate_dataset_id(dataset, "spyker_invalid_dataset")
        seed = simulation_settings.get("seed")
        if seed is not None:
            _parse_int_ge_zero(seed, "spyker_invalid_seed")
        _validate_seed_controls(simulation_settings, "spyker")

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


def _validate_seed_controls(simulation_settings: dict, prefix: str) -> None:
    seed_set = simulation_settings.get("seed_set")
    if seed_set is not None:
        if not isinstance(seed_set, list) or not seed_set:
            raise ValueError(f"{prefix}_invalid_seed_set")
        for seed in seed_set:
            _parse_int_ge_zero(seed, f"{prefix}_invalid_seed")

    repetitions = simulation_settings.get("repetitions")
    if repetitions is not None:
        parsed_repetitions = _parse_int_min_one(repetitions, f"{prefix}_invalid_repetitions")
        if seed_set is not None and parsed_repetitions != len(seed_set):
            raise ValueError(f"{prefix}_seed_repetitions_mismatch")


def _validate_dataset_id(value: object, error_code: str) -> str:
    if not isinstance(value, str):
        raise ValueError(error_code)
    dataset = value.strip()
    if not dataset:
        raise ValueError(error_code)
    if len(dataset) > 128:
        raise ValueError(error_code)
    return dataset
