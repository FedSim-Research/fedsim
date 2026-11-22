import json
import logging
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from filelock import Timeout

from fedsim.telemetry.logging import JSONFormatter, ProcessSafeFileHandler


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("failure", ["lock", "write"])
def test_telemetry_failure_policy_is_explicit(tmp_path, capsys, strict, failure):
    handler = ProcessSafeFileHandler(tmp_path / "events.jsonl", strict=strict)
    handler.setFormatter(JSONFormatter())
    record = logging.LogRecord("test", logging.INFO, "", 0, "original event", (), None)
    record.extra_data = {"run_id": "example", "log_type": "client_update"}
    if failure == "lock":

        @contextmanager
        def unavailable(**kwargs):
            raise Timeout("busy.lock")
            yield

        handler._process_lock = SimpleNamespace(acquire=unavailable)
        expected = Timeout
    else:
        handler.stream.close()
        handler.stream = SimpleNamespace(
            write=Mock(side_effect=OSError("disk unavailable")), flush=Mock(), close=Mock()
        )
        expected = OSError
    try:
        if strict:
            with pytest.raises(expected):
                handler.emit(record)
            assert handler.fallback_records == 0
        else:
            handler.emit(record)
            event = json.loads(capsys.readouterr().err)
            assert event["message"] == "original event"
            assert event["run_id"] == "example"
            assert event["telemetry_file_fallback"] is True
            assert handler.fallback_records == 1
    finally:
        handler.close()
