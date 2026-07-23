from dataclasses import dataclass, field, asdict
import json
from pathlib import Path

VALID_RISK_TOLERANCES = {"conservative", "moderate", "aggressive"}


@dataclass
class Preferences:
    domain: str | None = None
    risk_tolerance: str = "moderate"
    min_expected_reward: int | None = None
    privacy_constraints: list[str] = field(default_factory=list)


def load_preferences(path: Path) -> Preferences:
    if not path.exists():
        return Preferences()
    text = path.read_text()
    if not text.strip():
        return Preferences()
    data = json.loads(text)
    return Preferences(
        **{k: data[k] for k in data if k in Preferences.__dataclass_fields__}
    )


def save_preferences(path: Path, prefs: Preferences) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(prefs), indent=2))
