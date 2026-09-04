"""The tests/dincli/ marker hook is load-bearing; assert it actually classifies.

Guards two failure modes, both of which are silent:
  - hook missing or no-op  -> integration tests run in CI and fail on a
                              missing chain / IPFS / Docker
  - hook not path-scoped   -> the entire suite is marked integration and CI
                              passes having run nothing
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COLLECT_TIMEOUT = 60


def _collect(marker_expr):
    """Node IDs selected by `-m <marker_expr>`.

    A non-zero exit is always a failure of the assertion that follows, never
    silently-empty output: pytest returns 5 when a selection is empty, which is
    precisely the broken-hook case this module exists to catch.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", marker_expr],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=COLLECT_TIMEOUT,
    )
    assert result.returncode == 0, (
        f"collection for -m {marker_expr!r} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    return [line for line in result.stdout.splitlines() if "::" in line]


def test_integration_selection_is_exactly_the_dincli_directory():
    """-m integration must select every tests/dincli item and nothing else."""
    selected = _collect("integration")
    assert selected, "no tests carry the integration marker - hook missing or no-op"
    leaked = [line for line in selected if not line.startswith("tests/dincli/")]
    assert not leaked, (
        f"integration marker leaked outside tests/dincli/ - the hook lost its "
        f"path filter: {leaked[:5]}"
    )


def test_unit_selection_is_non_empty_and_excludes_dincli():
    """-m 'not integration' must still select the unit suite."""
    selected = _collect("not integration")
    assert selected, "the unit suite is empty - the hook is over-marking"
    assert not any(line.startswith("tests/dincli/") for line in selected)
