import pytest
from flwr_datasets.partitioner import IidPartitioner, PathologicalPartitioner

from fedsim.learning import build_partitioner, dataset_provider_name
from fedsim.services.simulation_validation import _validate_partitioning


def test_default_partitioner_is_iid():
    assert isinstance(build_partitioner(10), IidPartitioner)


def test_label_skew_uses_pathological_partitioner():
    partitioner = build_partitioner(10, "label-skew", 2, seed=7)
    assert isinstance(partitioner, PathologicalPartitioner)


@pytest.mark.parametrize(
    ("partitioning", "labels", "error"),
    [
        ("label-skew", None, "labels_per_client"),
        ("label-skew", 0, "labels_per_client"),
        ("dirichlet", None, "unsupported_partitioning"),
    ],
)
def test_invalid_partitioner_settings_are_rejected(partitioning, labels, error):
    with pytest.raises(ValueError, match=error):
        build_partitioner(10, partitioning, labels)


def test_iid_provider_name_is_unchanged():
    legacy = dataset_provider_name("cifar", 10, 42, "job")
    assert dataset_provider_name("cifar", 10, 42, "job", "iid", None) == legacy
    assert dataset_provider_name("cifar", 10, 42, "job", "label-skew", 2) != legacy


@pytest.mark.parametrize(
    ("settings", "error"),
    [
        ({"partitioning": "dirichlet"}, "spyker_invalid_partitioning"),
        ({"partitioning": "label-skew"}, "spyker_missing_labels_per_client"),
        ({"partitioning": "label-skew", "labels_per_client": 0}, "invalid_labels_per_client"),
    ],
)
def test_partitioning_validation(settings, error):
    with pytest.raises(ValueError, match=error):
        _validate_partitioning(settings, "spyker")


def test_valid_partitioning_settings_pass():
    _validate_partitioning({"partitioning": "label-skew", "labels_per_client": 2}, "hierfl")
    _validate_partitioning({"partitioning": "iid"}, "hierfl")
    _validate_partitioning({}, "hierfl")
