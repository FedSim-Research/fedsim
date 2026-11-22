import pytest
from pydantic import ValidationError
from test_builders import topology

from fedsim.api.routes.simulation import SimulationSettings
from fedsim.services.controller import SimulationController
from fedsim.services.run_definition import RunDefinition
from fedsim.services.simulation_validation import validate_start_payload


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
@pytest.mark.parametrize("mode", ["completion", "parent"])
def test_api_ordering_survives_definition_controller_and_builder(architecture, mode):
    from fedsim.services.hierfl_simulation_builder import build_hierfl_simulation
    from fedsim.services.spyker_simulation_builder import build_spyker_simulation

    graph = topology(architecture)
    settings = SimulationSettings(event_order=mode).model_dump(exclude_none=True)
    training = {"epochs": 1, "lr": 0.01}
    validate_start_payload(architecture, graph, training, settings, {})
    definition = RunDefinition.capture(
        {architecture: dict(graph=graph, training_config=training, simulation_settings=settings)}
    )
    frozen = definition.configurations()[architecture]["simulation_settings"]
    controller = SimulationController(architecture, simulation_settings=frozen)
    builder = build_hierfl_simulation if architecture == "hierfl" else build_spyker_simulation
    simulation = builder(
        definition.graph(architecture), training_config=training, **controller._data_settings()
    )
    actual = (
        simulation.event_order
        if architecture == "hierfl"
        else simulation.config.simulation.event_order
    )
    assert actual == mode
    assert frozen["event_order"] == mode


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
@pytest.mark.parametrize("value", ["fastest", True, 1, [], {}])
def test_invalid_order_is_rejected_by_api_and_native_validation(architecture, value):
    with pytest.raises(ValidationError):
        SimulationSettings(event_order=value)
    with pytest.raises(ValueError, match=f"{architecture}_invalid_event_order"):
        validate_start_payload(
            architecture,
            topology(architecture),
            {"epochs": 1, "lr": 0.01},
            {"event_order": value},
            {},
        )
