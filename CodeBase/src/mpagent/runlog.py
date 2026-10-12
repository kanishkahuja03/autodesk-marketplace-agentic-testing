"""Run logging: the readable run.log (also shown on the console) and the machine-readable trace.jsonl.

The run folder only exists after S0 has created it, so log lines are kept in memory until
attach_run_folder() is called and then written to run.log, followed by every later line.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

LOGGER_NAME = "mpagent"
RUN_LOG = "run.log"
TRACE_FILE = "trace.jsonl"

log = logging.getLogger(LOGGER_NAME)
_FORMAT = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")


def start_logging() -> None:
    """Console output now; run.log output once the run folder is known."""
    log.handlers.clear()
    log.setLevel(logging.INFO)
    log.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_FORMAT)
    log.addHandler(console)

    # Holds every line until attach_run_folder(); never flushes on its own.
    buffer = logging.handlers.MemoryHandler(capacity=100_000, flushLevel=logging.CRITICAL + 1)
    log.addHandler(buffer)


def attach_run_folder(run_dir: Path) -> None:
    """Write the buffered lines to <run_dir>/run.log and keep logging there."""
    file_handler = logging.FileHandler(run_dir / RUN_LOG, encoding="utf-8")
    file_handler.setFormatter(_FORMAT)
    for handler in list(log.handlers):
        if isinstance(handler, logging.handlers.MemoryHandler):
            handler.setTarget(file_handler)
            handler.flush()
            log.removeHandler(handler)
            handler.close()
    log.addHandler(file_handler)


def stop_logging() -> None:
    """Close run.log so the file is complete and not locked."""
    for handler in list(log.handlers):
        handler.flush()
        handler.close()
        log.removeHandler(handler)


class Trace:
    """Appends one JSON object per line to <run_dir>/trace.jsonl (LLM requests/responses, MCP calls)."""

    def __init__(self, run_dir: Path):
        self.path = run_dir / TRACE_FILE

    def write(self, event: str, **data) -> None:
        record = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "event": event, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
