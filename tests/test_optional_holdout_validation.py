import pytest

from fedsim.services.simulation_validation import _validate_partitioning


@pytest.mark.parametrize("prefix", ["hierfl", "spyker"])
@pytest.mark.parametrize("value", [-0.1, 1, 1.2, float("nan"), float("inf")])
def test_holdout_is_validated_without_partition_selection(prefix, value):
    with pytest.raises(ValueError, match="invalid_local_holdout"):
        _validate_partitioning({"local_holdout": value}, prefix)


@pytest.mark.parametrize("value", [0, 0.2, 0.9])
def test_valid_holdout_uses_default_partitioning(value):
    _validate_partitioning({"local_holdout": value}, "spyker")
