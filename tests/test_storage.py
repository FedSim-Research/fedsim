from sqlalchemy import select

from fedsim.persistence.models import EvaluationPoint
from fedsim.services.evaluation_point_store import backfill_periodic_evaluations_from_log_file
from fedsim.settings import checkpoint_path, data_dir, telemetry_log_path
from fedsim.telemetry.logging import setup_telemetry_logger


def test_run_telemetry_can_be_backfilled_once_on_windows_and_linux(database):
    run_id = "test:hierfl:42:1"
    logger = setup_telemetry_logger(run_id)
    logger.info(
        "Evaluation Complete",
        extra={
            "extra_data": {
                "log_type": "periodic_evaluation",
                "run_id": run_id,
                "architecture": "hierfl",
                "virtual_time": 10,
                "round": 1,
                "accuracy": 0.5,
                "loss": 0.8,
            }
        },
    )
    for handler in logger.handlers:
        handler.flush()
    assert ":" not in telemetry_log_path(run_id).name
    assert backfill_periodic_evaluations_from_log_file(run_id) == 1
    assert backfill_periodic_evaluations_from_log_file(run_id) == 0
    with database.SessionLocal() as session:
        point = session.execute(
            select(EvaluationPoint).where(EvaluationPoint.run_id == run_id)
        ).scalar_one()
        assert point.accuracy == 0.5
        assert point.virtual_time == 10


def test_relative_checkpoints_use_runtime_storage(tmp_path):
    assert checkpoint_path("nested/model.pth") == data_dir() / "models/nested/model.pth"
    assert checkpoint_path(str(tmp_path / "absolute.pth")) == tmp_path / "absolute.pth"
