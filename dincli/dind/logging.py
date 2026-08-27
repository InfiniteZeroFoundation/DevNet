"""Structured JSON logging for the dind daemon (T0.2d).

JsonFormatter emits line-delimited JSON with fields:
ts, level, logger, msg, (+ context: role, network, model_id, gi, job_id, error_code).

configure_logging(mode) is idempotent — repeat calls don't stack handlers.
It attaches to the "dincli" logger (which otherwise propagates to the root
logger's text handler installed by sdk/log.py), sets propagate=False so
records fire only the JSON handler, and captures/restores the level.

Error details reuse sdk.errors sanitize_details for secrets safety.
"""

import json
import logging
from datetime import datetime, timezone

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


def configure_logging(mode: str = "json") -> None:
    logger = logging.getLogger("dincli")

    for h in list(logger.handlers):
        if isinstance(h.formatter, JsonFormatter):
            logger.removeHandler(h)

    if mode == "json":
        level = _resolve_log_level()
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        setattr(handler, _DAEMON_HANDLER_MARKER, True)
        logger.addHandler(handler)
        logger.propagate = False
        logger.setLevel(level)
