"""Structured JSON logging for the dind daemon (T0.2d, BL-21).

JsonFormatter emits line-delimited JSON with fields:
ts, level, logger, msg, (+ context: role, network, model_id, gi, job_id, error_code).

configure_logging(mode, state_dir) is idempotent — repeat calls don't stack
handlers. It attaches to the "dincli" logger (which otherwise propagates to
the root logger's text handler installed by sdk/log.py), sets
propagate=False so records fire only the JSON handler(s), and
captures/restores the level.

When ``state_dir`` is given, a ``RotatingFileHandler`` on
``<state_dir>/dind.log`` is attached ALONGSIDE the stderr handler, never
replacing it — systemd and container users still want stderr. If the log
file can't be opened, the failure is caught, a warning goes to stderr, and
the daemon starts anyway: losing file logs must not be fatal. A malformed
size/backup-count env var is a different kind of failure — a configuration
mistake, not a runtime fault — and is left to propagate from the resolvers
so it fails loudly at startup instead of silently logging nowhere.

``RotatingFileHandler`` is a ``StreamHandler`` subclass (via
``FileHandler``), so handler identification here uses exact type or the
``_DAEMON_HANDLER_MARKER``, never a bare ``isinstance(h, StreamHandler)``,
which would double-count it.

Error details reuse sdk.errors sanitize_details for secrets safety.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dincli.dind.config import resolve_log_backup_count, resolve_log_max_bytes
from dincli.sdk.config import CONFIG_FILE

_CONTEXT_FIELDS = ("role", "network", "model_id", "gi", "job_id", "error_code")
_DAEMON_HANDLER_MARKER = "__dind_json_handler__"


def _resolve_log_level() -> int:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            level_str = config.get("log_level", "INFO")
            return getattr(logging, level_str.upper(), logging.INFO)
        except (json.JSONDecodeError, OSError):
            return logging.INFO
    return logging.INFO


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in _CONTEXT_FIELDS:
            val = getattr(record, key, None)
            if val is not None:
                obj[key] = val

        if record.exc_info and record.exc_info[1]:
            obj["exception"] = str(record.exc_info[1])

        return json.dumps(obj)


def configure_logging(mode: str = "json", state_dir: str | Path | None = None) -> None:
    logger = logging.getLogger("dincli")

    # Remove THEN close, in that order: removing first stops the handler
    # from receiving any further records, so closing it afterwards can never
    # log into a stream that's mid-teardown. The old code only removed,
    # leaking the fd on every repeat call in a long-lived process.
    for h in list(logger.handlers):
        if isinstance(h.formatter, JsonFormatter):
            logger.removeHandler(h)
            h.close()

    if mode != "json":
        return

    level = _resolve_log_level()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    setattr(handler, _DAEMON_HANDLER_MARKER, True)
    logger.addHandler(handler)

    if state_dir is not None:
        # Resolver failures (bad env config) propagate — a startup mistake
        # should fail loudly, not degrade to stderr-only logging silently.
        max_bytes = resolve_log_max_bytes()
        backup_count = resolve_log_backup_count()
        log_path = Path(state_dir) / "dind.log"
        try:
            file_handler = RotatingFileHandler(
                str(log_path), maxBytes=max_bytes, backupCount=backup_count
            )
        except OSError as e:
            print(
                f"warning: dind could not open log file {log_path}: {e}",
                file=sys.stderr,
            )
        else:
            file_handler.setFormatter(JsonFormatter())
            setattr(file_handler, _DAEMON_HANDLER_MARKER, True)
            logger.addHandler(file_handler)

    logger.propagate = False
    logger.setLevel(level)
