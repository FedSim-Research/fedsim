import logging
import os
from tempfile import TemporaryDirectory

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
