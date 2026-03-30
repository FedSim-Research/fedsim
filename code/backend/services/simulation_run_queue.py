from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from queue import Queue, Empty
from threading import Event, Lock, Thread
from typing import Any, Literal
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import ray

from backend.services import graph_service
from backend.simulation_controller import SimulationController

RunStatus = Literal["queued", "running", "completed", "failed"]
logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunJob:
    run_id: str
    graph_id: int
    architecture: str
    training_config: dict[str, Any] | None
    simulation_settings: dict[str, Any] | None
    spyker_config: dict[str, Any] | None
    combined_payload: dict[str, Any] | None = None
    status: RunStatus = "queued"
    queued_at: str = field(default_factory=_utcnow_iso)
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_api_dict(self) -> dict[str, Any]:
        result = self.result or {}
        return {
            "run_id": self.run_id,
            "status": self.status,
            "graph_id": self.graph_id,
            "architecture": self.architecture,
            "seed": (self.simulation_settings or {}).get("seed"),
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "output_filename": result.get("output_filename"),
            "evaluation": result.get("evaluation"),
            "results_by_architecture": result.get("results_by_architecture"),
            "error": self.error,
        }


class SimulationRunQueue:
    def __init__(self, max_concurrent_runs: int = 1) -> None:
        if max_concurrent_runs != 1:
            raise ValueError("Only max_concurrent_runs=1 is supported right now")
        self._queue: Queue[str] = Queue()
        self._jobs: dict[str, RunJob] = {}
        self._lock = Lock()
        self._stop_event = Event()
        self._worker: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                logger.debug("simulation_queue_worker_already_running")
                return
            self._stop_event.clear()
            self._worker = Thread(target=self._worker_loop, name="simulation-run-worker", daemon=True)
            self._worker.start()
            logger.info("simulation_queue_worker_started")

    def stop(self, timeout_seconds: float = 10.0) -> None:
        self._stop_event.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=timeout_seconds)
            logger.info("simulation_queue_worker_stopped")

    def enqueue(
        self,
        *,
        graph_id: int,
        architecture: str,
        training_config: dict[str, Any] | None,
        simulation_settings: dict[str, Any] | None,
        spyker_config: dict[str, Any] | None,
    ) -> RunJob:
        run_id = str(uuid4())
        job = RunJob(
            run_id=run_id,
            graph_id=graph_id,
            architecture=architecture,
            training_config=training_config,
            simulation_settings=simulation_settings,
            spyker_config=spyker_config,
        )
        with self._lock:
            self._jobs[run_id] = job
        self._queue.put(run_id)
        logger.info(
            "simulation_run_enqueued run_id=%s graph_id=%s architecture=%s queue_size=%s",
            run_id,
            graph_id,
            architecture,
            self._queue.qsize(),
        )
        return job

    def enqueue_combined(self, combined_payload: dict[str, Any]) -> RunJob:
        run_id = str(uuid4())
        job = RunJob(
            run_id=run_id,
            graph_id=-1,
            architecture="both",
            training_config=None,
            simulation_settings=None,
            spyker_config=None,
            combined_payload=combined_payload,
        )
        with self._lock:
            self._jobs[run_id] = job
        self._queue.put(run_id)
        logger.info(
            "simulation_combined_run_enqueued run_id=%s queue_size=%s",
            run_id,
            self._queue.qsize(),
        )
        return job

    def get(self, run_id: str) -> RunJob | None:
        with self._lock:
            return self._jobs.get(run_id)

    def list_runs(self) -> list[RunJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda run: run.queued_at, reverse=True)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                run_id = self._queue.get(timeout=0.5)
            except Empty:
                continue

            try:
                self._run_job(run_id)
            finally:
                self._queue.task_done()

    def _run_job(self, run_id: str) -> None:
        job = self.get(run_id)
        if job is None:
            logger.warning("simulation_run_missing run_id=%s", run_id)
            return

        started_at = datetime.now(timezone.utc)
        with self._lock:
            job.status = "running"
            job.started_at = started_at.isoformat()
            job.error = None
        logger.info(
            "simulation_run_started run_id=%s graph_id=%s architecture=%s",
            job.run_id,
            job.graph_id,
            job.architecture,
        )

        try:
            if job.architecture == "both":
                result = self._run_combined_job(job)
            else:
                graph = graph_service.get_graph(job.graph_id)
                if graph is None:
                    raise ValueError("graph_not_found")
                controller = SimulationController(
                    job.architecture,
                    graph=graph,
                    training_config=job.training_config,
                    simulation_settings=job.simulation_settings,
                    spyker_config=job.spyker_config,
                )
                result = controller.start()
            status: RunStatus = "completed"
            error = None
        except Exception as exc:
            result = None
            status = "failed"
            error = str(exc)
            logger.exception(
                "simulation_run_failed run_id=%s graph_id=%s architecture=%s error=%s",
                job.run_id,
                job.graph_id,
                job.architecture,
                error,
            )

        finished_at = datetime.now(timezone.utc)
        duration_seconds = (finished_at - started_at).total_seconds()
        with self._lock:
            job.status = status
            job.result = result
            job.error = error
            job.finished_at = finished_at.isoformat()
            job.duration_seconds = duration_seconds
        if status == "completed":
            logger.info(
                "simulation_run_completed run_id=%s graph_id=%s architecture=%s duration_seconds=%.3f",
                job.run_id,
                job.graph_id,
                job.architecture,
                duration_seconds,
            )

    def _run_combined_job(self, job: RunJob) -> dict[str, Any]:
        if not job.combined_payload:
            raise ValueError("combined_payload_missing")

        payload = job.combined_payload
        hier_cfg = payload["hierfl"]
        spyker_cfg = payload["spyker"]

        hier_budget = (hier_cfg.get("simulation_settings") or {}).get("gpu_budget")
        spyker_budget = (spyker_cfg.get("simulation_settings") or {}).get("gpu_budget")
        if hier_budget is not None and spyker_budget is not None:
            available_gpu = float(ray.available_resources().get("GPU", 0.0))
            combined_budget = float(hier_budget) + float(spyker_budget)
            if combined_budget > available_gpu + 1e-9 and combined_budget > 0.0:
                scale = max(0.0, available_gpu) / combined_budget
                hier_scaled = float(hier_budget) * scale
                spyker_scaled = float(spyker_budget) * scale
                (hier_cfg.setdefault("simulation_settings", {}))["gpu_budget"] = hier_scaled
                (spyker_cfg.setdefault("simulation_settings", {}))["gpu_budget"] = spyker_scaled
                logger.warning(
                    "combined_gpu_budget_scaled requested=%s available=%s hier_scaled=%s spyker_scaled=%s",
                    combined_budget,
                    available_gpu,
                    hier_scaled,
                    spyker_scaled,
                )

        hier_graph = graph_service.get_graph(int(hier_cfg["graph_id"]))
        spyker_graph = graph_service.get_graph(int(spyker_cfg["graph_id"]))
        if hier_graph is None or hier_graph.architecture != "hierfl":
            raise ValueError("hierfl_graph_not_found")
        if spyker_graph is None or spyker_graph.architecture != "spyker":
            raise ValueError("spyker_graph_not_found")

        hier_controller = SimulationController(
            "hierfl",
            graph=hier_graph,
            training_config=hier_cfg.get("training_config"),
            simulation_settings=hier_cfg.get("simulation_settings"),
            spyker_config=None,
        )
        spyker_controller = SimulationController(
            "spyker",
            graph=spyker_graph,
            training_config=spyker_cfg.get("training_config"),
            simulation_settings=spyker_cfg.get("simulation_settings"),
            spyker_config=spyker_cfg.get("spyker_config"),
        )

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_hier = pool.submit(hier_controller.start)
            fut_spyker = pool.submit(spyker_controller.start)
            hier_result = fut_hier.result()
            spyker_result = fut_spyker.result()

        return {
            "results_by_architecture": {
                "hierfl": hier_result,
                "spyker": spyker_result,
            }
        }


run_queue = SimulationRunQueue(max_concurrent_runs=1)
