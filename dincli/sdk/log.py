import json
import logging
from pathlib import Path

from dincli.sdk.config import CONFIG_DIR, CONFIG_FILE

_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _read_log_level() -> int:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            level_str = config.get("log_level", "INFO")
            return getattr(logging, level_str.upper(), logging.INFO)
        except (json.JSONDecodeError, OSError):
            return logging.INFO
    return logging.INFO


handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(_LOG_FORMAT))

logging.basicConfig(
    level=_read_log_level(),
    format=_LOG_FORMAT,
    handlers=[handler],
)

logger = logging.getLogger("dincli")
