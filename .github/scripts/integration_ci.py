"""Advisory integration selection and reporting; no application imports or APIs."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

# Trace/rationale: Documentation/technical/testing/dincli-testing-guide.md.
PREFIXES = (
    "foundry/src/",
    "foundry/script/",
    "foundry/test/",
    "foundry/lib/",
    "hardhat/",
    "dincli/",
    "tests/dincli/",
)
FILES = frozenset(
    {
        "pyproject.toml",
        "MANIFEST.in",
        ".github/constraints-ci.txt",
        ".gitmodules",
        ".dockerignore",
        "foundry/anvil.sh",
        "foundry/foundry.toml",
        "foundry/foundry.lock",
        "foundry/remappings.txt",
        "foundry/package.json",
        "foundry/package-lock.json",
        ".github/workflows/ci.yml",
        ".github/scripts/integration_ci.py",
    }
)
REASONS = {
    "manual-enabled": "Manual integration requested.",
    "manual-disabled": "Manual integration option was not selected.",
    "relevant-paths": "Relevant integration inputs changed.",
    "unrelated-paths": "No relevant integration inputs changed.",
    "unavailable-base": "Base unavailable; conservatively running integration.",
    "unavailable-diff": "Diff unavailable; conservatively running integration.",
    "unsupported-event": "Unrecognized event; conservatively running integration.",
}


def relevant(path):
    return path in FILES or path.startswith(PREFIXES)


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout


def select(event, before="", manual=False, cwd=None):
    """Return an explicit decision/reason; inability to diff never means skip."""
    if event == "workflow_dispatch":
        return manual, "manual-enabled" if manual else "manual-disabled"
    if event == "pull_request":
        base = "HEAD^1"  # checkout's merge preview, compared to its base parent
    elif event == "push":
        if not re.fullmatch(r"[0-9a-fA-F]{40}", before) or set(before) == {"0"}:
            return True, "unavailable-base"
        base = before
        try:
            git("fetch", "-q", "--depth=1", "origin", before, cwd=cwd)
        except (subprocess.SubprocessError, OSError):
            return True, "unavailable-base"
    else:
        return True, "unsupported-event"
    try:
        paths = git(
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            "--ignore-submodules=none",
            base,
            "HEAD",
            "--",
            cwd=cwd,
        )
    except (subprocess.SubprocessError, OSError):
        return True, "unavailable-diff"
    changed = any(relevant(os.fsdecode(path)) for path in paths.split(b"\0") if path)
    return changed, "relevant-paths" if changed else "unrelated-paths"


def summary(needs):
    """Use raw step outcomes, never advisory job success, as suite evidence."""
    detector = needs.get("integration-paths", {})
    integration = needs.get("integration", {})
    decision = detector.get("outputs", {})
    evidence = integration.get("outputs", {})
    run = decision.get("run", "")
    reason = decision.get("reason", "")
    valid = (
        detector.get("result") == "success"
        and run in {"true", "false"}
        and reason in REASONS
    )
    intentional = (
        valid
        and run == "false"
        and reason
        in {
            "manual-disabled",
            "unrelated-paths",
        }
        and integration.get("result") == "skipped"
    )
    suite = evidence.get("suite_outcome", "")
    status = evidence.get("execution_status", "")
    if suite == "success":
        outcome = "Passed — integration suite exited successfully"
    elif suite == "failure":
        outcome = "Failed — integration suite failed"
    elif (
        suite == "cancelled"
        or status == "cancelled"
        or integration.get("result") == "cancelled"
    ):
        outcome = "Cancelled — no completed suite result"
    elif intentional:
        outcome = "Intentionally skipped — integration was not requested"
    elif status == "failure" and evidence.get("setup_outcome") != "success":
        outcome = "Failed — integration setup failed; suite did not run"
    else:
        outcome = "Incomplete/unknown — no completed suite result"
    if not valid:
        selection = "Detection failed/incomplete — no valid detector decision; this is not an intentional skip."
    else:
        selection = REASONS.get(reason, "Detector reason unavailable.")
    upload = evidence.get("upload_outcome", "")
    logs = (
        "integration-logs artifact uploaded; see the run's artifacts."
        if evidence.get("artifact_url")
        else "See integration job logs; integration-logs artifact may be absent."
    )
    if intentional:
        logs = "Integration was not started; no integration logs or artifact expected."
    if upload == "failure":
        logs += " Artifact upload failed (separate from the suite outcome)."
    return (
        "## Integration (advisory)\n\n"
        f"**{outcome}.**\n\n{selection}\n\n{logs}\n\n"
        "Integration does not gate CI OK. A skipped, failed or incomplete run is not "
        "a successful full GI. A passing suite result alone does not establish "
        "full-round lifecycle coverage or satisfy the promotion criteria in #270.\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("select", "summary"))
    args = parser.parse_args()
    if args.command == "select":
        run, reason = select(
            os.environ.get("EVENT", ""),
            os.environ.get("BEFORE", ""),
            os.environ.get("MANUAL_INTEGRATION") == "true",
        )
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write(f"run={str(run).lower()}\nreason={reason}\n")
        print(REASONS[reason])
    else:
        report = summary(json.loads(os.environ["INTEGRATION_NEEDS"]))
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write(report)
        print(report)


if __name__ == "__main__":
    main()
