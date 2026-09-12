from pathlib import Path


class StateDirs:
    def __init__(self, state_dir: str | Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self.state_dir / "dind.db"

    @property
    def pid_path(self) -> Path:
        return self.state_dir / "dind.pid"

    @property
    def lock_path(self) -> Path:
        return self.state_dir / "dind.lock"

    @property
    def control_path(self) -> Path:
        """Descriptor naming the AF_UNIX control endpoint of whichever
        instance currently holds ``lock_path`` (dincli/dind/control.py,
        review finding 4). An ordinary file in the state dir — unlike the
        socket itself, it has no path-length constraint."""
        return self.state_dir / "dind.control.json"

    @property
    def preferences_path(self) -> Path:
        return self.state_dir / "preferences.json"
