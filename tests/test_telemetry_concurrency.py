import json
import multiprocessing
import os
from pathlib import Path

from fedsim.telemetry.logging import setup_telemetry_logger


def _emit_records(directory, worker):
    os.environ["FEDSIM_DATA_DIR"] = directory
    logger = setup_telemetry_logger("shared-run")
    for index in range(40):
        logger.info("x" * 5000, extra={"extra_data": {"worker": worker, "index": index}})
    for handler in logger.handlers:
        handler.close()


def test_multiple_processes_preserve_complete_unique_json_records(tmp_path):
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_emit_records, args=(str(tmp_path), worker)) for worker in range(3)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        if process.is_alive():
            process.terminate()
            process.join()
        assert process.exitcode == 0
    rows = [
        json.loads(line)
        for line in (Path(tmp_path) / "logs/sim_shared-run.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(rows) == 120
    assert {(row["worker"], row["index"]) for row in rows} == {
        (worker, index) for worker in range(3) for index in range(40)
    }
    assert all(row["message"] == "x" * 5000 for row in rows)
