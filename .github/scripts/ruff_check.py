"""Run Ruff once; findings and execution/report failures block CI."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


def report(status, output):
    if status not in (0, 1):
        raise ValueError(f"Ruff failed with exit status {status}")
    findings = json.loads(output)
    if not isinstance(findings, list) or bool(findings) != bool(status):
        raise ValueError("Ruff status and JSON findings disagree")
    for item in findings:
        if not isinstance(item, dict):
            raise ValueError("Ruff finding must be an object")
        for field in ("code", "filename", "message"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"Invalid Ruff finding {field}")
        location = item.get("location")
        if not isinstance(location, dict) or any(
            type(location.get(field)) is not int or location[field] < 1
            for field in ("row", "column")
        ):
            raise ValueError("Invalid Ruff finding location")
        if item["code"] == "E902":
            raise ValueError(f"Ruff could not read {item['filename']}")
        location = item["location"]
        print(f"{item['filename']}:{location['row']}:{location['column']}: "
              f"{item['code']} {item['message']}")
    counts = dict(sorted(Counter(item["code"] for item in findings).items()))
    print(f"Ruff findings: {len(findings)}; by rule: {counts}")


def main():
    destination = Path(sys.argv[1])
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--output-format", "json"],
        capture_output=True, text=True, check=False,
    )
    destination.write_text(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    try:
        report(result.returncode, result.stdout)
    except (ValueError, KeyError, TypeError) as error:
        print(f"Ruff reporting failed: {error}", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
