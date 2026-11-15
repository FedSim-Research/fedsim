"""Independent hand-calculated checks for the post-hoc equal-wave control."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def analysis(monkeypatch):
    folder = Path(__file__).resolve().parents[1] / "experiments/analysis"
    monkeypatch.syspath_prepend(str(folder))
    return importlib.import_module("reconstruct_feedback")


@pytest.mark.parametrize("clients,expected", [(20, 16), (50, 40), (140, 112)])
def test_archived_floor_counts_follow_inclusive_wave_boundary(analysis, clients, expected):
    assert analysis.floor_assignments_per_wave(clients, 0.01, 0.000001, 0.05) == expected


def test_floor_count_respects_boundary_and_moderate_penalty(analysis):
    # Surpluses for four positions are 3/4, 1/2, 1/4, 0. The inclusive
    # threshold 1/2 accepts exactly the first two; 9/10 accepts none.
    assert analysis.floor_assignments_per_wave(4, 0.03, 0.01, 0.04) == 2
    assert analysis.floor_assignments_per_wave(4, 0.1, 0.01, 0.1) == 0
    assert analysis.floor_assignments_per_wave(50, 0.05, 0.000001, 0.05) == 0
    assert analysis.floor_assignments_per_wave(140, 0.01, 0.000001, 0) == 0


@pytest.mark.parametrize(
    "clients,base,minimum,beta",
    [
        (0, 0.01, 1e-6, 0.05),
        (True, 0.01, 1e-6, 0.05),
        (3, 0.01, 0.01, 0.05),
        (3, 0.01, 1e-6, -1),
        (3, float("nan"), 1e-6, 0.05),
    ],
)
def test_invalid_analytical_control_inputs_are_rejected(analysis, clients, base, minimum, beta):
    with pytest.raises(ValueError):
        analysis.floor_assignments_per_wave(clients, base, minimum, beta)


def test_distribution_distinguishes_equal_totals_from_client_exposure(analysis):
    rotating = analysis.summarize_client_floor([1, 1, 1, 1], 4)
    persistent = analysis.summarize_client_floor([0, 0, 2, 2], 4)
    assert (
        rotating["total_completed_floor_updates"]
        == persistent["total_completed_floor_updates"]
        == 4
    )
    assert rotating["clients_never_at_floor"] == rotating["clients_at_every_eligible_floor"] == 0
    assert (
        persistent["clients_never_at_floor"] == persistent["clients_at_every_eligible_floor"] == 2
    )


def test_distribution_rejects_more_floor_updates_than_eligible_waves(analysis):
    with pytest.raises(ValueError):
        analysis.summarize_client_floor([3], 4)


def test_metric_scope_uses_assigned_clients_without_replacing_macro(analysis):
    result = analysis.metric_scope(
        {"a": 3, "b": 1}, {"a": {"accuracy": 0.8}, "b": {"accuracy": 0.4}}
    )
    assert result["server_macro_accuracy"] == pytest.approx(0.6)
    assert result["assigned_client_weighted_accuracy"] == pytest.approx(0.7)
    assert result["minimum_server_accuracy"] == 0.4
    assert result["weighted_minus_macro_pp"] == pytest.approx(10)


def test_metric_scope_rejects_missing_server_instead_of_renormalizing(analysis):
    with pytest.raises(ValueError):
        analysis.metric_scope({"a": 3, "b": 1}, {"a": {"accuracy": 0.8}})
