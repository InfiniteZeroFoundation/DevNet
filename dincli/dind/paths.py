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
