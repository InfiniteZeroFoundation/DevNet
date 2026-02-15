import json
import logging
from pathlib import Path

from platformdirs import user_config_dir

CONFIG_DIR = Path(user_config_dir("dincli"))
CONFIG_FILE = CONFIG_DIR / "config.json"

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"Error decoding config file at {CONFIG_FILE}. Returning empty config.")
                return {}
    else:
        print(f"No config found at {CONFIG_FILE}")
    return {}

def get_config(key, default=None):
    config = load_config()
    return config.get(key, default)

# Initialize logging
log_level_str = get_config("log_level", default="INFO")
log_level = getattr(logging, log_level_str.upper(), logging.INFO)

logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("dincli")