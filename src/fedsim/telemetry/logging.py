import datetime
import json
import logging
import os
import sys
import threading

from filelock import FileLock, Timeout

from fedsim.settings import telemetry_log_path

_setup_lock = threading.Lock()


# Barebones Logger for simple log pushing
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp_real": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Additional data added through record kwargs
        if hasattr(record, "extra_data"):
            log_record.update(record.extra_data)

        return json.dumps(log_record)


class ProcessSafeFileHandler(logging.FileHandler):
    """Keep complete records together across Ray processes on shared mounts."""

    def __init__(self, filename, *, strict: bool = False):
        super().__init__(filename, encoding="utf-8")
        self.strict = strict
        self.fallback_records = 0
        self._process_lock = FileLock(str(filename) + ".lock", timeout=30)

    def emit(self, record):
        # Handler's thread lock is process-local. TextIO append alone does not
        # protect whole JSON records on all Docker/host shared filesystems.
        try:
            with self._process_lock.acquire(poll_interval=0.005):
                super().emit(record)
        except (Timeout, OSError) as error:
            if self.strict:
                raise
            self._fallback(record, error)

    def handleError(self, record):
        error = sys.exc_info()[1]
        if self.strict:
            raise error if error is not None else RuntimeError("telemetry_write_failed")
        self._fallback(record, error)

    def _fallback(self, record, error):
        self.fallback_records += 1
        try:
            payload = json.loads(self.format(record))
        except Exception:
            payload = {
                "level": "ERROR",
                "message": "Telemetry record could not be encoded",
                "logger": record.name,
            }
        payload.update(telemetry_file_fallback=True, telemetry_error=type(error).__name__)
        try:
            sys.stderr.write(json.dumps(payload) + "\n")
            sys.stderr.flush()
        except (OSError, ValueError):
            # A closed stderr during shutdown must not turn best-effort logging
            # into a training error. Strict research writers never take this path.
            pass


def setup_telemetry_logger(run_id: str):
    """Sets up a file logger that outputs strict JSON lines."""
    log_filename = telemetry_log_path(run_id)
    log_filename.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"telemetry_{run_id}")
    logger.setLevel(logging.INFO)

    # Avoid duplicate logs if called multiple times
    with _setup_lock:
        if not logger.handlers:
            strict = os.environ.get("FEDSIM_TELEMETRY_STRICT", "off").strip().lower() in {
                "on",
                "true",
                "1",
            }
            file_handler = ProcessSafeFileHandler(log_filename, strict=strict)
            file_handler.setFormatter(JSONFormatter())
            logger.addHandler(file_handler)

    return logger
