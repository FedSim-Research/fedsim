import logging
import json
import datetime
import os

# Barebones Logger for simple log pushing
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp_real": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Additional data added through record kwargs
        if hasattr(record, 'extra_data'):
            log_record.update(record.extra_data)
        
        return json.dumps(log_record)

def setup_telemetry_logger(run_id: str):
    """Sets up a file logger that outputs strict JSON lines."""
    os.makedirs("logs", exist_ok=True)
    log_filename = f"logs/sim_{run_id}.jsonl"
    
    logger = logging.getLogger(f"telemetry_{run_id}")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate logs if called multiple times
    if not logger.handlers:
        file_handler = logging.FileHandler(log_filename)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
        
    return logger
