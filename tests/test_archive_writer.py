"""Regression coverage for Windows-held archive destination files."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from fedsim.experiments import campaign


def test_transient_destination_lock_keeps_old_json_until_atomic_replace(tmp_path, monkeypatch):
    target = tmp_path / "status.json"
    target.write_text('{"old":true}')
    original_replace = Path.replace
    seen = []

    def replace(source, destination):
        seen.append(source)
        if len(seen) < 3:
            assert json.loads(target.read_text()) == {"old": True}
            raise PermissionError("reader holds destination")
        return original_replace(source, destination)

    sleep = Mock()
    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(campaign.time, "sleep", sleep)
    campaign._write_json(target, {"new": 42})
    assert len(seen) == 3
    assert sleep.call_count == 2
    assert json.loads(target.read_text()) == {"new": 42}
    assert not target.with_suffix(".json.tmp").exists()


def test_persistent_destination_lock_remains_bounded_and_preserves_old_json(tmp_path, monkeypatch):
    target = tmp_path / "status.json"
    target.write_text('{"old":true}')
    replace = Mock(side_effect=PermissionError("persistent denial"))
    sleep = Mock()
    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(campaign.time, "monotonic", Mock(side_effect=[0, 0, 9]))
    monkeypatch.setattr(campaign.time, "sleep", sleep)
    with pytest.raises(PermissionError, match="persistent denial"):
        campaign._write_json(target, {"new": 42})
    assert replace.call_count == 2
    sleep.assert_called_once_with(0.05)
    assert json.loads(target.read_text()) == {"old": True}


def test_other_filesystem_errors_are_not_retried(tmp_path, monkeypatch):
    target = tmp_path / "status.json"
    replace = Mock(side_effect=OSError("disk error"))
    sleep = Mock()
    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(campaign.time, "sleep", sleep)
    with pytest.raises(OSError, match="disk error"):
        campaign._write_json(target, {"new": 42})
    replace.assert_called_once()
    sleep.assert_not_called()
