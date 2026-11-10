"""Reproduce issue 320 evidence from an internally owned historical snapshot."""

import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path

SOURCE_REF = "b1cd4d55ba2c44ec17248e9fa4a21a215b742e25"
REPOSITORY = Path(__file__).resolve().parents[2]
RUFF = ["uv", "tool", "run", "--from", "ruff==0.16.4", "ruff"]


def run(command, root):
    return subprocess.run(command, cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def main():
    destination = Path(sys.argv[1]).resolve()
    policy = (REPOSITORY / "pyproject.toml").read_bytes()
    source_sha = run(["git", "rev-parse", SOURCE_REF], REPOSITORY)
    archive = subprocess.check_output(["git", "archive", source_sha], cwd=REPOSITORY)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="devnet-320-") as directory:
        root = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archive)) as snapshot:
            snapshot.extractall(root, filter="data")
        version = run(RUFF + ["--version"], root)
        for name in ("old-defaults", "agreed-policy"):
            options = ["--isolated", "--target-version", "py312"]
            if name == "agreed-policy":
                (root / "pyproject.toml").write_bytes(policy)
                options = []
            command = RUFF + ["check", ".", "--no-cache", *options]
            result = subprocess.run(command + ["--output-format", "json"], cwd=root, capture_output=True, text=True, check=False)
            if result.returncode not in (0, 1):
                sys.exit(result.stderr or f"Ruff failed: {result.returncode}")
            findings = json.loads(result.stdout)
            if any(item["code"] == "E902" for item in findings):
                sys.exit("Unreadable input in baseline")
            files = run(command + ["--show-files"], root)

            def relative(filename):
                return str(Path(filename).relative_to(root))

            diagnostics = [dict(path=relative(item["filename"]), line=item["location"]["row"], column=item["location"]["column"], rule=item["code"], message=item["message"]) for item in findings]
            record = dict(
                ruff_version=version, source_sha=source_sha,
                policy_sha256=hashlib.sha256(policy).hexdigest() if name == "agreed-policy" else None,
                target_version="py312", discovery="Ruff includes/excludes and Git ignores; see file inventory",
                command=command + ["--output-format", "json"],
                by_path=dict(sorted(Counter(item["path"] for item in diagnostics).items())),
                exit_status=result.returncode, count=len(findings),
                by_rule=dict(sorted(Counter(item["code"] for item in findings).items())),
                files=sorted(relative(path) for path in files.splitlines()),
            )
            # One diagnostic per line keeps the historical record reviewable.
            header = json.dumps(record, indent=2)[:-2]
            details = ",\n".join("    " + json.dumps(item) for item in diagnostics)
            (destination / f"{name}.json").write_text(
                header + ',\n  "diagnostics": [\n' + details + "\n  ]\n}\n"
            )


if __name__ == "__main__":
    main()
