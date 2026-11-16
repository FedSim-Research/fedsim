from types import SimpleNamespace
from unittest.mock import Mock

import flwr_datasets.federated_dataset as flower_data
import pytest
from datasets import Dataset, DatasetDict
from PIL import Image

from fedsim import learning
from fedsim.engines.hierarchical import simulation as hierarchical
from fedsim.engines.spyker import simulation as spyker
from fedsim.simulation.randomness import derive_seed
from fedsim.specs.performance_metrics import Performance


@pytest.fixture
def local_dataset(monkeypatch):
    dataset = Dataset.from_dict(
        {
            "sample_id": list(range(60)),
            "img": [Image.new("RGB", (32, 32), (index, 20, 30)) for index in range(60)],
            "label": [index % 2 for index in range(60)],
        }
    )
    loader = Mock(return_value=DatasetDict(train=dataset))
    monkeypatch.setattr(flower_data.datasets, "load_dataset", loader)
    monkeypatch.setattr(flower_data, "event", lambda *args, **kwargs: None)
    return loader


def assignments(partition):
    return {split: list(partition[split]["sample_id"]) for split in ("train", "test")}


def test_provider_is_lazy_and_caches_each_requested_split_once(
    monkeypatch, local_actor, local_dataset
):
    split = Dataset.train_test_split
    calls = []

    def tracked_split(dataset, *args, **kwargs):
        calls.append(kwargs["seed"])
        return split(dataset, *args, **kwargs)

    monkeypatch.setattr(Dataset, "train_test_split", tracked_split)
    provider = local_actor(learning.DatasetProvider, "local/images", 3, 17)
    local_dataset.assert_not_called()
    first = provider.get_partition(2)
    assert provider.get_partition(2) is first
    assert set(provider.partitions) == {2}
    assert calls == [derive_seed(17, "data", "split", "2")]
    provider.get_partition(0)
    assert calls == [derive_seed(17, "data", "split", "2"), derive_seed(17, "data", "split", "0")]
    local_dataset.assert_called_once()
    assert local_dataset.call_args.kwargs["cache_dir"] == str(learning.dataset_cache_dir())


def test_seeded_assignments_are_repeatable_disjoint_and_independent_of_request_order(
    local_actor, local_dataset
):
    first = local_actor(learning.DatasetProvider, "local/images", 3, 17)
    second = local_actor(learning.DatasetProvider, "local/images", 3, 17)
    left = {index: assignments(first.get_partition(index)) for index in (2, 0, 1)}
    right = {index: assignments(second.get_partition(index)) for index in (1, 2, 0)}
    assert left == right
    all_samples = []
    for partition in left.values():
        assert len(partition["train"]) == 16 and len(partition["test"]) == 4
        assert set(partition["train"]).isdisjoint(partition["test"])
        all_samples.extend(partition["train"] + partition["test"])
    assert len(all_samples) == len(set(all_samples)) == 60
    assert set(all_samples) == set(range(60))


def test_run_seed_controls_global_partition_membership(local_actor, local_dataset):
    first = local_actor(learning.DatasetProvider, "local/images", 3, 17)
    second = local_actor(learning.DatasetProvider, "local/images", 3, 18)
    left = assignments(first.get_partition(0))
    right = assignments(second.get_partition(0))
    assert set(left["train"] + left["test"]) != set(right["train"] + right["test"])


@pytest.mark.parametrize("partition_id", [-1, 3])
def test_provider_rejects_invalid_partition_before_loading_data(
    local_actor, local_dataset, partition_id
):
    provider = local_actor(learning.DatasetProvider, "local/images", 3, 17)
    with pytest.raises(ValueError, match="dataset_partition_id_out_of_range"):
        provider.get_partition(partition_id)
    local_dataset.assert_not_called()


def test_provider_identity_separates_datasets_counts_seeds_and_jobs():
    definitions = [
        ("a/b", 3, 17, "job1"),
        ("a_b", 3, 17, "job1"),
        ("a/b", 4, 17, "job1"),
        ("a/b", 3, 18, "job1"),
        ("a/b", 3, 17, "job2"),
    ]
    names = [learning.dataset_provider_name(*definition) for definition in definitions]
    assert len(set(names)) == len(names)
    assert learning.dataset_provider_name(*definitions[0]) == names[0]


def test_provider_factory_uses_atomic_job_owned_creation(monkeypatch):
    factory = Mock()
    handle = object()
    factory.options.return_value.remote.return_value = handle
    monkeypatch.setattr(learning, "DatasetProvider", factory)
    monkeypatch.setattr(
        learning.ray, "get_runtime_context", lambda: SimpleNamespace(get_job_id=lambda: "job1")
    )
    assert learning.get_dataset_provider(" local/images ", 3, 17) is handle
    factory.options.assert_called_once_with(
        name=learning.dataset_provider_name("local/images", 3, 17, "job1"),
        get_if_exists=True,
        lifetime="non_detached",
    )
    factory.options.return_value.remote.assert_called_once_with("local/images", 3, 17, "iid", None)


def test_provider_factory_normalizes_default_dataset_and_data_seed(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(learning, "DatasetProvider", factory)
    monkeypatch.setattr(
        learning.ray, "get_runtime_context", lambda: SimpleNamespace(get_job_id=lambda: "job1")
    )
    learning.get_dataset_provider(" ", 3)
    factory.options.return_value.remote.assert_called_once_with(
        learning.DEFAULT_DATASET_ID, 3, 42, "iid", None
    )


@pytest.mark.parametrize("count", [0, -1])
def test_provider_factory_rejects_nonpositive_partition_count(monkeypatch, count):
    factory = Mock()
    monkeypatch.setattr(learning, "DatasetProvider", factory)
    with pytest.raises(ValueError, match="positive_partition_count"):
        learning.get_dataset_provider("local/images", count, 17)
    factory.options.assert_not_called()


def test_client_shuffle_does_not_change_shared_train_test_membership(
    monkeypatch, local_actor, local_dataset
):
    provider = local_actor(learning.DatasetProvider, "local/images", 3, 17)
    handle = SimpleNamespace(get_partition=SimpleNamespace(remote=provider.get_partition))
    monkeypatch.setattr(learning.ray, "get", lambda value: value)
    factory = Mock(side_effect=AssertionError("Explicit provider must be reused"))
    monkeypatch.setattr(learning, "get_dataset_provider", factory)

    def load(shuffle_seed):
        train, test = learning.load_data(
            1,
            3,
            seed=shuffle_seed,
            dataset_id="local/images",
            partition_seed=17,
            dataset_provider=handle,
        )
        return (
            [int(value) for batch in train for value in batch["sample_id"]],
            [int(value) for batch in test for value in batch["sample_id"]],
        )

    first, repeated, changed = load(100), load(100), load(200)
    assert first == repeated
    assert first[0] != changed[0]
    assert set(first[0]) == set(changed[0])
    assert first[1] == changed[1]
    assert set(first[0]).isdisjoint(first[1])
    assert set(provider.partitions) == {1}
    factory.assert_not_called()


def test_loader_passes_data_seed_to_factory_independently_of_shuffle_seed(
    monkeypatch, local_actor, local_dataset
):
    provider = local_actor(learning.DatasetProvider, "local/images", 3, 17)
    handle = SimpleNamespace(get_partition=SimpleNamespace(remote=provider.get_partition))
    factory = Mock(return_value=handle)
    monkeypatch.setattr(learning, "get_dataset_provider", factory)
    monkeypatch.setattr(learning.ray, "get", lambda value: value)
    train, _ = learning.load_data(0, 3, seed=999, dataset_id="local/images", partition_seed=17)
    factory.assert_called_once_with("local/images", 3, 17)
    assert train.generator.initial_seed() == 999


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
def test_engines_create_provider_in_driver_and_pass_its_handle_in_context(
    monkeypatch, architecture
):
    module = hierarchical if architecture == "hierfl" else spyker
    simulation = (
        hierarchical.HierarchicalSimulation(dataset_id="local/images", seed=17)
        if architecture == "hierfl"
        else spyker.SpykerSimulation(dataset_id="local/images", seed=17)
    )
    if architecture == "hierfl":
        simulation.super_id = "coordinator"
        simulation.edge_ids = ["server"]
    else:
        simulation.add_server("server", "Server", Performance(10, 0), {}, 10, 10)
    simulation.client_registry = {"client0": object(), "client1": object()}
    provider = object()
    factory = Mock(return_value=provider)
    monkeypatch.setattr(module, "ensure_ray_initialized", lambda: None)
    monkeypatch.setattr(module, "get_cpu_execution_pool", lambda: object())
    monkeypatch.setattr(module, "SimulationOrchestrator", Mock())
    monkeypatch.setattr(module, "get_dataset_provider", factory)
    monkeypatch.setattr(simulation, "_spawn_actors", lambda: None)
    monkeypatch.setattr(simulation, "_configure_network", lambda: None)
    simulation.build()
    factory.assert_called_once_with("local/images", 2, 17, "iid", None)
    assert simulation.context.dataset_provider is provider
    assert simulation.context.seed == 17
