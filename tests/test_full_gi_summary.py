"""Offline evidence and failure-propagation checks for manual Full GI reporting."""

import json
import os
import re
import subprocess
import sys
import textwrap
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/full_gi_summary.py"
SPEC = spec_from_file_location("full_gi_summary", SCRIPT)
reporter = module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)
WORKFLOW = (ROOT / ".github/workflows/full-gi.yml").read_text()


def needs(result="success", **outputs):
    return {"integration": {"result": result, "outputs": outputs}}


def test_completed_suite_with_no_artifact_requested():
    report = reporter.summary(
        needs(
            setup_outcome="success",
            suite_outcome="success",
            pytest_exit="0",
            log_exit="0",
            elapsed_seconds="65",
            upload_outcome="skipped",
        )
    )
    assert "| Integration job | Succeeded |" in report
    assert "| Setup | Completed |" in report
    assert "| Pytest | Completed successfully (exit 0) |" in report
    assert "| Log capture | Captured (tee exit 0) |" in report
    assert "| Suite elapsed time | 65s |" in report
    assert "Not requested (successful integration job)" in report
    assert "manual-only and outside CI OK" in report
    assert (
        "exit 0 alone does not establish full training-round lifecycle coverage"
        in report
    )


@pytest.mark.parametrize("exit_code", [1, 2, 3, 4, 5, 130, 137])
def test_nonzero_pytest_is_not_success_even_if_job_reports_success(exit_code):
    report = reporter.summary(needs(pytest_exit=str(exit_code)))
    assert f"Failed/errored (exit {exit_code})" in report
    assert "Completed successfully" not in report


def test_setup_failure_before_suite():
    report = reporter.summary(
        needs(result="failure", setup_outcome="skipped", suite_outcome="skipped")
    )
    assert "| Integration job | Failed |" in report
    assert "Failed before the suite" in report
    assert "Not run (suite step skipped)" in report
    assert "Completed successfully" not in report


@pytest.mark.parametrize("result", ["success", "failure", "cancelled", "skipped", ""])
def test_missing_outputs_never_claim_suite_or_setup_success(result):
    report = reporter.summary(needs(result=result))
    assert "no recorded pytest exit" in report
    assert "no setup completion evidence" in report
    assert "Completed successfully" not in report
    assert "No artifact confirmed" in report
    assert "| Suite elapsed time | Unknown |" in report


def test_missing_integration_is_unknown():
    assert "| Integration job | Incomplete/unknown |" in reporter.summary({})


@pytest.mark.parametrize("value", ["", "garbage", "-1", "256", "0\n", "0.0"])
def test_malformed_pytest_exit_is_unknown(value):
    report = reporter.summary(needs(suite_outcome="success", pytest_exit=value))
    assert "no recorded pytest exit" in report
    assert "Completed successfully" not in report


@pytest.mark.parametrize(
    "outcome,label", [("failure", "Failed/interrupted"), ("cancelled", "Cancelled")]
)
def test_interrupted_suite_without_exit(outcome, label):
    report = reporter.summary(needs(result=outcome, suite_outcome=outcome))
    assert f"{label} before an exit was recorded" in report
    assert "Completed successfully" not in report


@pytest.mark.parametrize(
    "result,label", [("failure", "Failed"), ("cancelled", "Cancelled")]
)
def test_completed_pytest_does_not_override_job_result(result, label):
    report = reporter.summary(needs(result=result, pytest_exit="0", log_exit="0"))
    assert f"| Integration job | {label} |" in report
    assert "Completed successfully (exit 0)" in report


def test_log_capture_failure_is_separate():
    report = reporter.summary(needs(result="failure", pytest_exit="0", log_exit="7"))
    assert "Completed successfully (exit 0)" in report
    assert "Failed (tee exit 7); pytest result is separate" in report


@pytest.mark.parametrize(
    "outcome,label",
    [
        ("failure", "Upload failed"),
        ("cancelled", "Upload cancelled"),
        ("skipped", "Upload skipped"),
        ("success", "Upload step succeeded; no artifact URL confirmed"),
    ],
)
def test_upload_outcomes_do_not_rewrite_suite(outcome, label):
    report = reporter.summary(
        needs(result="failure", pytest_exit="1", upload_outcome=outcome)
    )
    assert "Failed/errored (exit 1)" in report
    assert label in report
    assert "](" not in report


def test_confirmed_artifact_link():
    url = "https://github.com/InfiniteZeroFoundation/DevNet/actions/runs/123/artifacts/456"
    report = reporter.summary(needs(upload_outcome="success", artifact_url=url))
    assert f"[integration-logs]({url}) uploaded" in report


def test_unexpected_artifact_output_is_not_rendered_as_markdown():
    report = reporter.summary(
        needs(upload_outcome="success", artifact_url="bad)\n| fake | passed |")
    )
    assert "no artifact URL confirmed" in report
    assert "fake" not in report


def job(name, workflow=WORKFLOW):
    return re.search(
        rf"^  {name}:\n(.*?)(?=^  [a-z][\w-]*:|\Z)", workflow, re.MULTILINE | re.DOTALL
    ).group(1)


def step_script(step_id):
    step = re.search(
        rf"^      - name: [^\n]+\n        id: {step_id}\n(.*?)(?=^      - |\Z)",
        job("integration"),
        re.MULTILINE | re.DOTALL,
    ).group(1)
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


@pytest.mark.parametrize(
    "pytest_exit,log_exit,expected",
    [(0, 0, 0), (1, 0, 1), (2, 0, 2), (5, 0, 5), (0, 7, 7), (2, 7, 2)],
)
def test_actual_suite_shell_preserves_both_pipeline_exits(
    tmp_path, pytest_exit, log_exit, expected
):
    fake_pytest = tmp_path / "pytest"
    fake_pytest.write_text(
        '#!/bin/sh\nprintf "pytest fixture\\n"\nexit "$FAKE_PYTEST_EXIT"\n'
    )
    fake_tee = tmp_path / "tee"
    fake_tee.write_text('#!/bin/sh\ncat > "$1"\nexit "$FAKE_TEE_EXIT"\n')
    fake_pytest.chmod(0o755)
    fake_tee.chmod(0o755)
    output = tmp_path / "outputs"
    result = subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            "-c",
            step_script("suite"),
        ],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.defpath,
            "FAKE_PYTEST_EXIT": str(pytest_exit),
            "FAKE_TEE_EXIT": str(log_exit),
            "DIN_TEST_RESULTS_DIR": str(tmp_path / "results"),
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == expected, result.stderr
    evidence = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert evidence["pytest_exit"] == str(pytest_exit)
    assert evidence["log_exit"] == str(log_exit)
    assert int(evidence["elapsed_seconds"]) >= 0
    assert (tmp_path / "results/pytest.log").read_text() == "pytest fixture\n"


@pytest.mark.parametrize("pytest_exit,expected", [(0, 1), (2, 2)])
def test_evidence_write_failure_cannot_hide_pytest_failure(
    tmp_path, pytest_exit, expected
):
    fake_pytest = tmp_path / "pytest"
    fake_pytest.write_text(f"#!/bin/sh\nexit {pytest_exit}\n")
    fake_pytest.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step_script("suite")],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.defpath,
            "DIN_TEST_RESULTS_DIR": str(tmp_path / "results"),
            "GITHUB_OUTPUT": str(tmp_path),  # A directory cannot receive outputs.
        },
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == expected


def test_workflow_keeps_manual_policy_and_independent_reporting():
    triggers = WORKFLOW.split("on:\n", 1)[1].split("permissions:", 1)[0]
    assert triggers.strip() == "workflow_dispatch:"
    assert "continue-on-error" not in WORKFLOW
    assert "integration-paths" not in WORKFLOW
    integration = job("integration")
    assert "needs:" not in integration
    for key, expression in {
        "setup_outcome": "steps.ready.outcome",
        "suite_outcome": "steps.suite.outcome",
        "pytest_exit": "steps.suite.outputs.pytest_exit",
        "log_exit": "steps.suite.outputs.log_exit",
        "elapsed_seconds": "steps.suite.outputs.elapsed_seconds",
        "upload_outcome": "steps.upload.outcome",
        "artifact_url": "steps.upload.outputs.artifact-url",
    }.items():
        assert f"{key}: ${{{{ {expression} }}}}" in integration
    assert "if: failure() || cancelled()\n        timeout-minutes: 3" in integration
    assert "path: ${{ runner.temp }}/din-results" in integration
    report = job("integration-summary")
    assert "needs: integration" in report
    assert "if: always()" in report
    assert "timeout-minutes: 5" in report
    assert "timeout-minutes: 2" in report
    assert "INTEGRATION_NEEDS: ${{ toJSON(needs) }}" in report
    assert "run: python3 .github/scripts/full_gi_summary.py" in report
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "merge_group:\n    types: [checks_requested]" in ci
    assert "needs: [solidity, python, docs]" in job("ci-ok", ci)
    assert set(
        re.findall(r"^  ([a-z][\w-]*):$", ci.split("jobs:\n", 1)[1], re.MULTILINE)
    ) == {"solidity", "python", "docs", "ci-ok"}


def test_cli_appends_report(tmp_path):
    output = tmp_path / "summary"
    output.write_text("Existing summary\n")
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env={
            **os.environ,
            "INTEGRATION_NEEDS": json.dumps(needs(result="cancelled")),
            "GITHUB_STEP_SUMMARY": str(output),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert (
        output.read_text() == "Existing summary\n" + result.stdout.rstrip("\n") + "\n"
    )
    assert "| Integration job | Cancelled |" in output.read_text()
