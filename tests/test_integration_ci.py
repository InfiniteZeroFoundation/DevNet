"""Offline contract tests for integration selection, raw reporting and CI wiring."""

import json
import os
import re
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/integration_ci.py"
spec = spec_from_file_location("integration_ci", SCRIPT)
ci = module_from_spec(spec)
spec.loader.exec_module(ci)
WORKFLOW = (ROOT / ".github/workflows/ci.yml").read_text()


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo).decode().strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    # All remotes below are local disposable directories; no host Git config.
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "develop")
    git(path, "config", "user.email", "ci@example.invalid")
    git(path, "config", "user.name", "CI test")
    commit(path, "README.md")
    return path


def commit(repo, path, content="fixture\n"):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    git(repo, "add", "--", path)
    git(repo, "commit", "-qm", "fixture")
    return git(repo, "rev-parse", "HEAD")


def local_origin(repo):
    origin = repo.parent / "origin.git"
    git(repo, "clone", "-q", "--bare", str(repo), str(origin))
    git(repo, "remote", "add", "origin", str(origin))


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "MANIFEST.in",
        "tests/__init__.py",
        ".github/constraints-ci.txt",
        ".gitmodules",
        ".dockerignore",
        "foundry/foundry.toml",
        "foundry/foundry.lock",
        "foundry/remappings.txt",
        "foundry/package.json",
        "foundry/package-lock.json",
        "foundry/lib/forge-std",
        "foundry/lib/openzeppelin-contracts",
        "foundry/lib/openzeppelin-contracts-upgradeable",
        "foundry/lib/openzeppelin-foundry-upgrades",
        "foundry/test/Example.t.sol",
        "foundry/src/Example.sol",
        "foundry/script/Deploy.s.sol",
        "foundry/anvil.sh",
        "hardhat/hardhat.config.ts",
        "dincli/config/din_info.json",
        "dincli/docker/worker/Dockerfile",
        "tests/dincli/conftest.py",
        ".github/workflows/ci.yml",
        ".github/scripts/integration_ci.py",
    ],
)
def test_consumed_inputs(path):
    assert ci.relevant(path)


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "Documentation/guide.md",
        "tests/test_unrelated.py",
        "cache_model_0/manifest.json",
        "cid_services/requirements.txt",
        "foundry/.gitmodules",
        "foundry/README.md",
        "pyproject.toml.bak",
        "other/dincli/main.py",
    ],
)
def test_excluded_inputs(path):
    assert not ci.relevant(path)


@pytest.mark.parametrize("enabled", [True, False])
def test_dispatch_does_not_diff_or_fetch(monkeypatch, enabled):
    def forbidden(*args, **kwargs):
        pytest.fail("manual selection must not execute git")

    monkeypatch.setattr(ci, "git", forbidden)
    assert ci.select("workflow_dispatch", manual=enabled) == (
        enabled,
        "manual-enabled" if enabled else "manual-disabled",
    )


@pytest.mark.parametrize(
    "path,expected",
    [
        ("Documentation/guide.md", False),
        ("pyproject.toml", True),
        ("tests/__init__.py", True),
        ("dincli/space tab\tand newline\n.py", True),
        (os.fsdecode(b"dincli/nonutf8-\xff.py"), True),
    ],
)
def test_real_pr_merge_preview(repo, path, expected):
    git(repo, "checkout", "-qb", "feature")
    commit(repo, path)
    git(repo, "checkout", "-q", "develop")
    # Base-only application changes must not be attributed to this PR.
    commit(repo, "dincli/base.py")
    git(repo, "merge", "--no-ff", "-qm", "preview", "feature")
    assert ci.select("pull_request", cwd=repo)[0] is expected


def test_push_compares_all_commits(repo):
    before = git(repo, "rev-parse", "HEAD")
    commit(repo, "pyproject.toml")
    commit(repo, "Documentation/guide.md")
    local_origin(repo)
    assert ci.select("push", before, cwd=repo) == (True, "relevant-paths")


def test_docs_only_push(repo):
    before = git(repo, "rev-parse", "HEAD")
    commit(repo, "Documentation/guide.md")
    local_origin(repo)
    assert ci.select("push", before, cwd=repo) == (False, "unrelated-paths")


def test_force_push_compares_endpoints(repo):
    before = commit(repo, "dincli/old.py")
    git(repo, "checkout", "--orphan", "replacement")
    git(repo, "rm", "-qrf", ".")
    commit(repo, "Documentation/guide.md")
    local_origin(repo)
    assert ci.select("push", before, cwd=repo) == (True, "relevant-paths")


@pytest.mark.parametrize("before", ["", "0" * 40, "f" * 40, "--help", "HEAD"])
def test_unavailable_push_base_runs(repo, before):
    local_origin(repo)
    assert ci.select("push", before, cwd=repo) == (True, "unavailable-base")


def test_missing_pr_parent_runs(repo):
    assert ci.select("pull_request", cwd=repo) == (True, "unavailable-diff")


@pytest.mark.parametrize(
    "error",
    [
        subprocess.CalledProcessError(128, "git"),
        subprocess.TimeoutExpired("git", 60),
        OSError("git unavailable"),
    ],
)
def test_failed_diff_runs(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(ci, "git", fail)
    assert ci.select("pull_request") == (True, "unavailable-diff")
    assert ci.select("push", "1" * 40) == (True, "unavailable-base")


@pytest.mark.parametrize(
    "old,new",
    [
        ("dincli/input.py", "Documentation/input.py"),
        ("Documentation/input.py", "dincli/input.py"),
    ],
)
def test_renames_both_directions(repo, old, new):
    commit(repo, old)
    (repo / new).parent.mkdir(parents=True, exist_ok=True)
    git(repo, "mv", old, new)
    git(repo, "commit", "-qm", "rename")
    assert ci.select("pull_request", cwd=repo) == (True, "relevant-paths")


def test_deletion(repo):
    commit(repo, "foundry/foundry.lock")
    git(repo, "rm", "foundry/foundry.lock")
    git(repo, "commit", "-qm", "delete")
    assert ci.select("pull_request", cwd=repo) == (True, "relevant-paths")


def test_gitlink_change(repo):
    first = git(repo, "rev-parse", "HEAD")
    second = commit(repo, "Documentation/guide.md")
    for sha in (first, second):
        git(
            repo,
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{sha},foundry/lib/forge-std",
        )
        git(repo, "commit", "-qm", "gitlink")
    assert ci.select("pull_request", cwd=repo) == (True, "relevant-paths")


def needs(
    run="true",
    reason="relevant-paths",
    detector="success",
    result="success",
    **evidence,
):
    return {
        "integration-paths": {
            "result": detector,
            "outputs": {"run": run, "reason": reason},
        },
        "integration": {"result": result, "outputs": evidence},
    }


@pytest.mark.parametrize(
    "outcome,label", [("success", "Passed"), ("failure", "Failed")]
)
def test_raw_suite_outcome_beats_masked_job_success(outcome, label):
    report = ci.summary(needs(suite_outcome=outcome, setup_outcome="success"))
    assert f"**{label} — integration suite" in report


@pytest.mark.parametrize("reason", ["unrelated-paths", "manual-disabled"])
def test_explicit_skip(reason):
    assert "**Intentionally skipped" in ci.summary(
        needs(run="false", reason=reason, result="skipped"),
    )


@pytest.mark.parametrize(
    "data",
    [
        {},
        needs(run="", result="skipped"),
        needs(run="false", detector="failure", result="skipped"),
        needs(run="false", reason="", result="skipped"),
        needs(result="skipped"),
        needs(run="false", detector="cancelled", result="skipped"),
        needs(run="false", result="success"),
    ],
)
def test_missing_or_failed_detection_is_never_intentional_skip(data):
    report = ci.summary(data)
    assert "**Intentionally skipped" not in report
    assert "**Passed" not in report


def test_detector_failure_is_visible_even_if_fallback_suite_passes():
    report = ci.summary(needs(run="", detector="failure", suite_outcome="success"))
    assert "Detection failed/incomplete" in report
    assert "suite exited successfully" in report


def test_setup_failure_not_suite_failure():
    report = ci.summary(
        needs(
            execution_status="failure", setup_outcome="skipped", suite_outcome="skipped"
        )
    )
    assert "setup failed; suite did not run" in report
    assert "artifact may be absent" in report


@pytest.mark.parametrize(
    "evidence",
    [
        {"suite_outcome": "cancelled"},
        {"execution_status": "cancelled"},
        {"result": "cancelled"},
    ],
)
def test_cancellation(evidence):
    assert "**Cancelled" in ci.summary(needs(**evidence))


def test_masked_success_without_evidence_is_unknown():
    assert "**Incomplete/unknown" in ci.summary(needs())


def test_upload_failure_cannot_rewrite_suite_result():
    report = ci.summary(needs(suite_outcome="success", upload_outcome="failure"))
    assert "**Passed" in report
    assert "Artifact upload failed" in report


def job(name):
    return re.search(
        rf"^  {name}:\n(.*?)(?=^  [a-z][\w-]*:|\Z)", WORKFLOW, re.MULTILINE | re.DOTALL
    ).group(1)


def step(job_text, step_id):
    return re.search(
        rf"      - name: [^\n]+\n        id: {step_id}\n(.*?)(?=      - |\Z)",
        job_text,
        re.DOTALL,
    ).group(1)


def test_workflow_preserves_gate_and_raw_evidence_wiring():
    gate = job("ci-ok")
    assert "needs: [solidity, python, docs]" in gate
    assert 'if [ "$r" != "success" ]' in gate
    assert "if: always()" in gate
    assert "continue-on-error" not in gate
    assert "paths:" not in WORKFLOW.split("jobs:")[0]
    integration = job("integration")
    assert "continue-on-error: true" in integration
    assert "needs.integration-paths.result != 'success'" in integration
    assert "needs.integration-paths.outputs.run != 'false'" in integration
    assert "!cancelled()" in integration
    assert "!inputs.run_integration" in integration
    evidence = step(integration, "evidence")
    for raw in ("steps.suite.outcome", "steps.ready.outcome", "job.status"):
        assert "${{ " + raw + " }}" in evidence
    assert "if: always()" in evidence
    assert "steps.evidence.outputs.suite_outcome" in integration
    assert "needs: [integration-paths, integration]" in job("integration-summary")
    assert "if: always()" in job("integration-summary")
    assert "${{ toJSON(needs) }}" in job("integration-summary")
    assert "MANUAL_INTEGRATION: ${{ inputs.run_integration }}" in job(
        "integration-paths"
    )


@pytest.mark.parametrize("exit_code", [0, 1, 2, 5])
def test_suite_shell_keeps_pytest_exit_status(tmp_path, exit_code):
    suite = step(job("integration"), "suite")
    script = suite.split("        run: |\n", 1)[1]
    script = "\n".join(line[10:] for line in script.splitlines())
    fake = tmp_path / "pytest"
    fake.write_text(f"#!/bin/sh\necho 'pytest fixture'\nexit {exit_code}\n")
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.defpath,
        "DIN_TEST_RESULTS_DIR": str(tmp_path / "results"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == exit_code
    assert f"exit {exit_code} after" in (tmp_path / "summary").read_text()


def test_cli_outputs_and_summary(tmp_path):
    output = tmp_path / "outputs"
    env = {
        **os.environ,
        "EVENT": "workflow_dispatch",
        "MANUAL_INTEGRATION": "false",
        "GITHUB_OUTPUT": str(output),
    }
    subprocess.run([sys.executable, str(SCRIPT), "select"], env=env, check=True)
    assert output.read_text() == "run=false\nreason=manual-disabled\n"
    report = tmp_path / "summary"
    env.update(
        INTEGRATION_NEEDS=json.dumps(
            needs(run="false", reason="manual-disabled", result="skipped")
        ),
        GITHUB_STEP_SUMMARY=str(report),
    )
    subprocess.run([sys.executable, str(SCRIPT), "summary"], env=env, check=True)
    assert "**Intentionally skipped" in report.read_text()


def test_push_fetch_success_does_not_hide_diff_failure(monkeypatch):
    calls = []

    def fetch_then_fail(*args, **kwargs):
        calls.append(args[0])
        if args[0] == "fetch":
            return b""
        raise subprocess.CalledProcessError(128, "git diff")

    monkeypatch.setattr(ci, "git", fetch_then_fail)
    assert ci.select("push", "1" * 40) == (True, "unavailable-diff")
    assert calls == ["fetch", "diff"]


def test_unknown_event_runs_conservatively():
    assert ci.select("unrecognized") == (True, "unsupported-event")
