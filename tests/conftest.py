import logging
import os
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

# Configure storage before collection imports the application or its SQLAlchemy engine.
_state = TemporaryDirectory(prefix="fedsim-tests-")
os.environ["FEDSIM_DATA_DIR"] = _state.name
os.environ.pop("FEDSIM_TELEMETRY_LOG_DIR", None)


@pytest.fixture(scope="session", autouse=True)
def database():
    from fedsim.persistence import database

    database.init_db()
    yield database
    database.engine.dispose()
    for name, logger in logging.Logger.manager.loggerDict.items():
        if name.startswith("telemetry_") and isinstance(logger, logging.Logger):
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)
    _state.cleanup()


@pytest.fixture
def api():
    from fastapi.testclient import TestClient

    from fedsim.api.app import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def local_actor(monkeypatch):
    """Exercise pinned Ray actor implementations without starting worker processes."""
    import ray

    runtime = SimpleNamespace(current_actor=object())
    monkeypatch.setattr(ray, "get_runtime_context", lambda: runtime)
    monkeypatch.setattr(ray, "put", lambda value: value)

    def create(actor_type, *args, **kwargs):
        metadata = getattr(actor_type, "__ray_metadata__", None)
        implementation = actor_type if metadata is None else metadata.modified_class
        return implementation(*args, **kwargs)

    return create
