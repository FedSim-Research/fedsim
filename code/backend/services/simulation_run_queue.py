from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib
import logging
from queue import Queue, Empty
import statistics
from threading import Event, Lock, Thread
from typing import Any, Callable, Literal
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import ray

from backend.services import graph_service
from backend.services.grafana_snapshot_service import create_accuracy_loss_snapshot_url
from backend.services.simulation_seed_sets import build_seeded_output_filename, shared_seed_set_or_raise
from backend.services import simulation_run_store
from backend.simulation_controller import SimulationController

RunStatus = Literal["queued", "running", "completed", "failed"]
logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_ray_initialized_for_resources() -> None:
    """Initialize Ray lazily for resource checks in the queue worker."""
    if ray.is_initialized():
        return
    try:
        ray_runtime = importlib.import_module("main.ray_runtime")
        ray_runtime.ensure_ray_initialized()
        return
    except Exception:
        # Fallback keeps this worker resilient if dynamic import path is unavailable.
        pass
    try:
        ray.init(address="auto", ignore_reinit_error=True, include_dashboard=False, log_to_driver=False)
    except Exception:
        ray.init(ignore_reinit_error=True, include_dashboard=False, log_to_driver=False)


def _get_cluster_gpu_capacity() -> float:
    try:
        _ensure_ray_initialized_for_resources()
        return float(ray.cluster_resources().get("GPU", 0.0))
    except Exception:
        logger.exception("ray_gpu_capacity_probe_failed")
        return 0.0


def _variance_or_zero(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return float(statistics.variance(values))


def _single_seed_or_none(seed_set: list[int]) -> int | None:
    return seed_set[0] if len(seed_set) == 1 else None


def _build_series_result(seed_set: list[int], runs: list[dict[str, Any]]) -> dict[str, Any]:
    evaluation_runs = [run["evaluation"] for run in runs if run.get("evaluation") is not None]
    evaluation_summary: dict[str, float | int] | None = None
    if evaluation_runs:
        accuracy_values = [float(item["accuracy"]) for item in evaluation_runs]
        loss_values = [float(item["avg_loss"]) for item in evaluation_runs]
        evaluation_summary = {
            "evaluated_repetitions": len(evaluation_runs),
            "mean_accuracy": float(sum(accuracy_values) / len(accuracy_values)),
            "variance_accuracy": _variance_or_zero(accuracy_values),
            "mean_avg_loss": float(sum(loss_values) / len(loss_values)),
            "variance_avg_loss": _variance_or_zero(loss_values),
        }

    return {
        "seed": _single_seed_or_none(seed_set),
        "seed_set": list(seed_set),
        "repetitions": len(seed_set),
        "completed_repetitions": len(runs),
        "output_filename": runs[0].get("output_filename") if len(seed_set) == 1 and runs else None,
        "evaluation": runs[0].get("evaluation") if len(seed_set) == 1 and runs else None,
        "evaluation_summary": evaluation_summary,
        "runs": runs,
    }


@dataclass
class RunJob:
    run_id: str
    graph_id: int | None
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
        primary_settings = self._primary_simulation_settings()
        return {
            "run_id": self.run_id,
            "status": self.status,
            "graph_id": self.graph_id,
            "architecture": self.architecture,
            "seed": result.get("seed", primary_settings.get("seed")),
            "seed_set": result.get("seed_set", primary_settings.get("seed_set")),
            "repetitions": result.get("repetitions", primary_settings.get("repetitions")),
            "completed_repetitions": result.get("completed_repetitions"),
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "output_filename": result.get("output_filename"),
            "dataset": self._dataset_for_architecture(),
            "datasets_by_architecture": self._datasets_by_architecture(),
            "accuracy_loss_snapshot_url": result.get("accuracy_loss_snapshot_url"),
            "accuracy_loss_snapshot_urls_by_architecture": result.get("accuracy_loss_snapshot_urls_by_architecture"),
            "evaluation": result.get("evaluation"),
            "evaluation_summary": result.get("evaluation_summary"),
            "runs": result.get("runs"),
            "results_by_architecture": result.get("results_by_architecture"),
            "error": self.error,
        }

    def _primary_simulation_settings(self) -> dict[str, Any]:
        if self.architecture == "both":
            payload = self.combined_payload or {}
            return (payload.get("hierfl") or {}).get("simulation_settings") or {}
        return self.simulation_settings or {}

    def _dataset_for_architecture(self) -> str | None:
        if self.architecture == "both":
            return None
        settings = self.simulation_settings or {}
        dataset = settings.get("dataset")
        return dataset if isinstance(dataset, str) and dataset.strip() else None

    def _datasets_by_architecture(self) -> dict[str, str | None] | None:
        if self.architecture != "both":
            return None
        payload = self.combined_payload or {}
        hierfl_settings = (payload.get("hierfl") or {}).get("simulation_settings") or {}
        spyker_settings = (payload.get("spyker") or {}).get("simulation_settings") or {}

        def _dataset_from(settings: dict[str, Any]) -> str | None:
            value = settings.get("dataset")
            if isinstance(value, str) and value.strip():
                return value
            return None

        return {
            "hierfl": _dataset_from(hierfl_settings),
            "spyker": _dataset_from(spyker_settings),
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

    def _persist_final_run_safe(self, job: RunJob) -> None:
        try:
            simulation_run_store.persist_final_run(job)
        except Exception:
            logger.exception("simulation_run_persist_failed run_id=%s", job.run_id)

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
            graph_id=None,
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

    def get_run_api(self, run_id: str) -> dict[str, Any] | None:
        persisted = simulation_run_store.get_run_api(run_id)
        with self._lock:
            job = self._jobs.get(run_id)
        if job is None:
            return persisted
        runtime = job.to_api_dict()
        if persisted is None:
            return runtime
        merged = {**persisted, **runtime}
        merged["run_metadata"] = persisted.get("run_metadata")
        merged["final_run_summary"] = persisted.get("final_run_summary")
        return merged

    def list_runs_api(self) -> list[dict[str, Any]]:
        persisted = {item["run_id"]: item for item in simulation_run_store.list_runs_api()}
        with self._lock:
            for job in self._jobs.values():
                runtime = job.to_api_dict()
                existing = persisted.get(job.run_id)
                if existing is None:
                    persisted[job.run_id] = runtime
                    continue
                merged = {**existing, **runtime}
                merged["run_metadata"] = existing.get("run_metadata")
                merged["final_run_summary"] = existing.get("final_run_summary")
                persisted[job.run_id] = merged
        return sorted(persisted.values(), key=lambda item: item.get("queued_at") or "", reverse=True)

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
                result = self._run_architecture_series(
                    architecture=job.architecture,
                    graph=graph,
                    training_config=job.training_config,
                    simulation_settings=job.simulation_settings,
                    spyker_config=job.spyker_config,
                    run_id_prefix=job.run_id,
                    progress_callback=lambda partial_result: self._update_job_partial_result(job.run_id, partial_result),
                )
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
        if status == "completed" and isinstance(result, dict):
            snapshot_data = self._create_accuracy_loss_snapshots(
                run_id=job.run_id,
                architecture=job.architecture,
                started_at=started_at,
                finished_at=finished_at,
            )
            result.update(snapshot_data)
        with self._lock:
            job.status = status
            job.result = result
            job.error = error
            job.finished_at = finished_at.isoformat()
            job.duration_seconds = duration_seconds
        self._persist_final_run_safe(job)
        if status == "completed":
            logger.info(
                "simulation_run_completed run_id=%s graph_id=%s architecture=%s duration_seconds=%.3f",
                job.run_id,
                job.graph_id,
                job.architecture,
                duration_seconds,
            )

    def _create_accuracy_loss_snapshots(
        self,
        *,
        run_id: str,
        architecture: str,
        started_at: datetime,
        finished_at: datetime,
    ) -> dict[str, Any]:
        range_from_ms = int(started_at.timestamp() * 1000)
        range_to_ms = int(finished_at.timestamp() * 1000)

        try:
            if architecture == "both":
                urls_by_architecture: dict[str, str | None] = {}
                for arch in ("hierfl", "spyker"):
                    urls_by_architecture[arch] = create_accuracy_loss_snapshot_url(
                        run_id=run_id,
                        architecture=arch,
                        range_from_ms=range_from_ms,
                        range_to_ms=range_to_ms,
                    )
                return {
                    "accuracy_loss_snapshot_url": None,
                    "accuracy_loss_snapshot_urls_by_architecture": urls_by_architecture,
                }

            url = create_accuracy_loss_snapshot_url(
                run_id=run_id,
                architecture=architecture,
                range_from_ms=range_from_ms,
                range_to_ms=range_to_ms,
            )
            return {
                "accuracy_loss_snapshot_url": url,
                "accuracy_loss_snapshot_urls_by_architecture": None,
            }
        except Exception:
            logger.exception(
                "simulation_snapshot_creation_failed run_id=%s architecture=%s",
                run_id,
                architecture,
            )
            return {
                "accuracy_loss_snapshot_url": None,
                "accuracy_loss_snapshot_urls_by_architecture": None,
            }

    def _run_architecture_series(
        self,
        *,
        architecture: str,
        graph,
        training_config: dict[str, Any] | None,
        simulation_settings: dict[str, Any] | None,
        spyker_config: dict[str, Any] | None,
        run_id_prefix: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        settings = dict(simulation_settings or {})
        seed_set = list(settings.get("seed_set") or [])
        if not seed_set:
            seed = settings.get("seed")
            if seed is None:
                raise ValueError(f"{architecture}_missing_seed_set")
            seed_set = [int(seed)]

        runs: list[dict[str, Any]] = []
        total_repetitions = len(seed_set)
        for repetition_index, seed in enumerate(seed_set, start=1):
            run_result = self._run_architecture_once(
                architecture=architecture,
                graph=graph,
                training_config=training_config,
                simulation_settings=settings,
                spyker_config=spyker_config,
                run_id=f"{run_id_prefix}:{architecture}:{seed}:{repetition_index}",
                seed=seed,
                seed_set=seed_set,
                repetition_index=repetition_index,
                total_repetitions=total_repetitions,
            )
            runs.append(run_result)
            if progress_callback is not None:
                progress_callback(_build_series_result(seed_set, runs))

        return _build_series_result(seed_set, runs)

    def _run_architecture_once(
        self,
        *,
        architecture: str,
        graph,
        training_config: dict[str, Any] | None,
        simulation_settings: dict[str, Any],
        spyker_config: dict[str, Any] | None,
        run_id: str,
        seed: int,
        seed_set: list[int],
        repetition_index: int,
        total_repetitions: int,
    ) -> dict[str, Any]:
        per_run_settings = dict(simulation_settings)
        per_run_settings["seed"] = seed
        per_run_settings["seed_set"] = list(seed_set)
        per_run_settings["repetitions"] = total_repetitions
        per_run_settings["output_filename"] = build_seeded_output_filename(
            simulation_settings.get("output_filename"),
            seed=seed,
            repetition_index=repetition_index,
            total_repetitions=total_repetitions,
        )

        controller = SimulationController(
            architecture,
            graph=graph,
            training_config=training_config,
            simulation_settings=per_run_settings,
            spyker_config=spyker_config,
            run_id=run_id,
        )

        started_at = datetime.now(timezone.utc)
        result = controller.start()
        duration_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
        result["seed"] = seed
        result["repetition_index"] = repetition_index
        result["duration_seconds"] = duration_seconds
        return result

    def _update_job_partial_result(self, run_id: str, partial_result: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(run_id)
            if job is None:
                return
            job.result = partial_result

    def _run_combined_job(self, job: RunJob) -> dict[str, Any]:
        if not job.combined_payload:
            raise ValueError("combined_payload_missing")

        payload = job.combined_payload
        hier_cfg = payload["hierfl"]
        spyker_cfg = payload["spyker"]

        hier_budget = (hier_cfg.get("simulation_settings") or {}).get("gpu_budget")
        spyker_budget = (spyker_cfg.get("simulation_settings") or {}).get("gpu_budget")
        if hier_budget is not None and spyker_budget is not None:
            available_gpu = _get_cluster_gpu_capacity()
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

        hier_settings = dict(hier_cfg.get("simulation_settings") or {})
        spyker_settings = dict(spyker_cfg.get("simulation_settings") or {})
        seed_set = shared_seed_set_or_raise(hier_settings, spyker_settings)

        hier_results: list[dict[str, Any]] = []
        spyker_results: list[dict[str, Any]] = []
        total_repetitions = len(seed_set)

        for repetition_index, seed in enumerate(seed_set, start=1):
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_hier = pool.submit(
                    self._run_architecture_once,
                    architecture="hierfl",
                    graph=hier_graph,
                    training_config=hier_cfg.get("training_config"),
                    simulation_settings=hier_settings,
                    spyker_config=None,
                    run_id=f"{job.run_id}:hierfl:{seed}:{repetition_index}",
                    seed=seed,
                    seed_set=seed_set,
                    repetition_index=repetition_index,
                    total_repetitions=total_repetitions,
                )
                fut_spyker = pool.submit(
                    self._run_architecture_once,
                    architecture="spyker",
                    graph=spyker_graph,
                    training_config=spyker_cfg.get("training_config"),
                    simulation_settings=spyker_settings,
                    spyker_config=spyker_cfg.get("spyker_config"),
                    run_id=f"{job.run_id}:spyker:{seed}:{repetition_index}",
                    seed=seed,
                    seed_set=seed_set,
                    repetition_index=repetition_index,
                    total_repetitions=total_repetitions,
                )
                hier_results.append(fut_hier.result())
                spyker_results.append(fut_spyker.result())

            self._update_job_partial_result(
                job.run_id,
                {
                    "seed": _single_seed_or_none(seed_set),
                    "seed_set": list(seed_set),
                    "repetitions": total_repetitions,
                    "completed_repetitions": repetition_index,
                    "results_by_architecture": {
                        "hierfl": _build_series_result(seed_set, hier_results),
                        "spyker": _build_series_result(seed_set, spyker_results),
                    },
                },
            )

        return {
            "seed": _single_seed_or_none(seed_set),
            "seed_set": list(seed_set),
            "repetitions": total_repetitions,
            "completed_repetitions": total_repetitions,
            "results_by_architecture": {
                "hierfl": _build_series_result(seed_set, hier_results),
                "spyker": _build_series_result(seed_set, spyker_results),
            }
        }


run_queue = SimulationRunQueue(max_concurrent_runs=1)
