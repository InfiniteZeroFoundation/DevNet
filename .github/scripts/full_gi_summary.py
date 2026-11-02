"""Report manual Full GI evidence without changing the integration job result."""

import json
import os
import re
from pathlib import Path


def number(value):
    """Actions outputs are strings; absent or malformed evidence stays unknown."""
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    return None


def summary(needs):
    integration = needs.get("integration", {})
    result = integration.get("result", "")
    outputs = integration.get("outputs", {})
    setup = outputs.get("setup_outcome", "")
    suite = outputs.get("suite_outcome", "")
    pytest_exit = number(outputs.get("pytest_exit", ""))
    log_exit = number(outputs.get("log_exit", ""))
    elapsed = number(outputs.get("elapsed_seconds", ""))
    upload = outputs.get("upload_outcome", "")
    artifact_url = outputs.get("artifact_url", "")

    job_status = {
        "success": "Succeeded",
        "failure": "Failed",
        "cancelled": "Cancelled",
        "skipped": "Skipped",
    }.get(result, "Incomplete/unknown")
    setup_status = "Incomplete/unknown — no setup completion evidence"
    if setup == "success":
        setup_status = "Completed"
    elif setup == "skipped" and suite == "skipped" and result == "failure":
        setup_status = "Failed before the suite; setup completion was not reached"
    elif setup == "failure":
        setup_status = "Failed at the setup completion step"
    elif setup == "cancelled":
        setup_status = "Cancelled before setup completion"

    if pytest_exit is not None and pytest_exit <= 255:
        pytest_status = (
            "Completed successfully (exit 0)"
            if pytest_exit == 0
            else f"Failed/errored (exit {pytest_exit})"
        )
    else:
        pytest_status = {
            "failure": "Failed/interrupted before an exit was recorded",
            "cancelled": "Cancelled before an exit was recorded",
            "skipped": "Not run (suite step skipped)",
        }.get(suite, "Incomplete/unknown — no recorded pytest exit")

    log_status = "Incomplete/unknown — no recorded log capture exit"
    if log_exit is not None and log_exit <= 255:
        log_status = (
            "Captured (tee exit 0)"
            if log_exit == 0
            else f"Failed (tee exit {log_exit}); pytest result is separate"
        )

    artifact_status = "No artifact confirmed"
    if upload == "success":
        # Link only the canonical URL emitted by upload-artifact, never arbitrary
        # Markdown from an unexpected output. Success can also mean no files.
        if re.fullmatch(
            r"https://github\.com/[\w.-]+/[\w.-]+/actions/runs/[0-9]+/artifacts/[0-9]+",
            artifact_url,
        ):
            artifact_status = f"[integration-logs]({artifact_url}) uploaded"
        else:
            artifact_status = "Upload step succeeded; no artifact URL confirmed"
    elif upload == "failure":
        artifact_status = "Upload failed; no artifact confirmed"
    elif upload == "cancelled":
        artifact_status = "Upload cancelled; no artifact confirmed"
    elif upload == "skipped":
        artifact_status = (
            "Not requested (successful integration job)"
            if result == "success"
            else "Upload skipped; no artifact confirmed"
        )

    runtime = f"{elapsed}s" if elapsed is not None else "Unknown"
    rows = (
        ("Integration job", job_status),
        ("Setup", setup_status),
        ("Pytest", pytest_status),
        ("Log capture", log_status),
        ("Suite elapsed time", runtime),
        ("Artifact", artifact_status),
    )
    return (
        "## Full GI outcome\n\n"
        "| Evidence | Result |\n| --- | --- |\n"
        + "".join(f"| {label} | {value} |\n" for label, value in rows)
        + "\nFull GI is manual-only and outside CI OK. A completed pytest result "
        "does not override job failure or cancellation, and exit 0 alone does "
        "not establish full training-round lifecycle coverage.\n\n"
        "Reporting and artifacts are best effort. Cancellation, timeouts or runner "
        "loss can prevent collection; missing evidence is not a successful suite. "
        "See the integration job logs for details.\n"
    )


def main():
    report = summary(json.loads(os.environ["INTEGRATION_NEEDS"]))
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
        output.write(report)
    print(report)


if __name__ == "__main__":
    main()
