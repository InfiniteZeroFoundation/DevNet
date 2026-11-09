"""Worker diagnostics policy tests using synthetic state only."""

import json
import os

import pytest

from tests.dincli.reports import collect_worker_reports


ADDRESS = "0x" + "a" * 40
JOBS = {
    "clients": "client_lms_gi_1",
    "auditors": "auditor_score_gi_1_batch_0_lm_0",
    "aggregators": "aggregator_t1_gi_1_batch_0",
}


@pytest.fixture
def roots(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    return scratch, tmp_path / "results"


def output_dir(scratch, role="clients", job=None, address=ADDRESS):
    directory = (
        scratch / "cache" / "dincli" / "local" / "model_0" / "jobs"
        / role / address / f"{job or JOBS[role]}_output"
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def report(scratch, data, **kwargs):
    path = output_dir(scratch, **kwargs) / "result.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def retained(results):
    return [json.loads(path.read_text())
            for path in (results / "worker-reports").glob("report-*.json")]


def test_only_sanitized_known_worker_reports_are_retained(roots):
    scratch, results = roots
    report(scratch, {"status": "ok", "result": "SUCCESS_SECRET"})
    report(scratch, {"status": "error", "error": "training failed",
                     "traceback": "known worker traceback",
                     "private_key": "FIELD_SECRET"}, role="auditors")
    report(scratch, {"status": "ok", "result": {"salt": "SALT_SECRET"}},
           role="aggregators")
    # Adjacent job inputs/config/commit state and fake result trees are excluded.
    (scratch / "config").mkdir()
    (scratch / "config" / "wallet.json").write_text("WALLET_SECRET")
    output = output_dir(scratch)
    (output / "unrelated.json").write_text("NEIGHBOR_SECRET")
    (output.parent / "client_lms_gi_1.json").write_text("INPUT_SECRET")
    (output.parent / "commits.json").write_text("COMMIT_SECRET")
    report(scratch, {"status": "error", "error": "FAKE_ROLE_SECRET"},
           role="wallets", job="client_lms_gi_1")
    report(scratch, {"status": "error", "error": "FAKE_JOB_SECRET"},
           job="config")
    report(scratch, {"status": "error", "error": "FAKE_ADDRESS_SECRET"},
           address="wallet")

    summary = collect_worker_reports(scratch, results)
    assert not summary["collection_failed"]
    assert summary["reports_collected"] == 3
    assert (summary["ok"], summary["error"]) == (2, 1)
    payload = json.dumps(retained(results)) + json.dumps(summary)
    assert "SECRET" not in payload
    assert ADDRESS not in payload
    assert "known worker traceback" in payload
    assert all(set(item) <= {"model", "role", "job", "participant", "status", "error", "traceback"}
               for item in retained(results))


@pytest.mark.parametrize("raw,reason", [
    ("{", "malformed-result"),
    ("", "malformed-result"),
    ('{"status": "error", "traceback":', "malformed-result"),
    ('{"status": "success"}', "invalid-result-schema"),
    ('[]', "invalid-result-schema"),
    ('{"status": "error", "traceback": {"key":"CANARY"}}',
     "invalid-result-schema"),
    ('{"status": "error", "error": ["CANARY"]}', "invalid-result-schema"),
])
def test_malformed_partial_and_invalid_reports_are_collection_failures(roots, raw, reason):
    scratch, results = roots
    (output_dir(scratch) / "result.json").write_text(raw)
    summary = collect_worker_reports(scratch, results)
    assert summary["collection_failed"]
    assert summary["errors"][0]["reason"] == reason
    assert retained(results) == []


def test_missing_result_is_reported_but_absent_inventory_is_not_invented(roots):
    scratch, results = roots
    output_dir(scratch)
    summary = collect_worker_reports(scratch, results)
    assert summary["errors"][0]["reason"] == "missing-result"
    assert summary["inventory"] == "discovered-local-output-directories-only"


def test_no_jobs_is_valid_diagnostics_without_expected_job_inventory(roots):
    summary = collect_worker_reports(*roots)
    assert not summary["collection_failed"]
    assert summary["reports_seen"] == 0


def test_summary_is_durable_and_matches_returned_outcome(roots):
    scratch, results = roots
    output_dir(scratch)
    summary = collect_worker_reports(scratch, results)
    summary_path = results / "worker-reports" / "summary.json"
    assert json.loads(summary_path.read_text()) == summary
    assert summary_path.stat().st_size <= 64 * 1024


def test_same_job_for_different_accounts_has_distinct_pseudonymous_identity(roots):
    scratch, results = roots
    report(scratch, {"status": "ok"})
    report(scratch, {"status": "ok"}, address="0x" + "b" * 40)
    summary = collect_worker_reports(scratch, results)
    assert not summary["collection_failed"]
    assert len({item["participant"] for item in retained(results)}) == 2
    assert all(len(item["participant"]) == 12 for item in retained(results))


def test_surrogate_text_is_encoded_safely(roots):
    scratch, results = roots
    report(scratch, {"status": "error", "error": "bad \ud800 text"})
    summary = collect_worker_reports(scratch, results)
    assert not summary["collection_failed"]
    assert retained(results)[0]["error"] == "bad \ud800 text"


def test_deeply_nested_json_is_a_collection_failure(roots):
    scratch, results = roots
    (output_dir(scratch) / "result.json").write_text("[" * 2000 + "]" * 2000)
    summary = collect_worker_reports(scratch, results)
    assert summary["collection_failed"]
    assert summary["errors"][0]["reason"] in {
        "malformed-result", "invalid-result-schema",
    }


def test_oversized_report_is_not_read_or_retained(roots):
    scratch, results = roots
    report(scratch, {"status": "error", "error": "A" * 1000})
    summary = collect_worker_reports(scratch, results, max_file_bytes=64)
    assert summary["errors"][0]["reason"] == "report-size-limit"
    assert summary["input_bytes"] == summary["retained_bytes"] == 0
    assert summary["omitted"] == 1


def test_text_is_bounded_and_truncation_marked(roots):
    scratch, results = roots
    report(scratch, {"status": "error", "error": "A" * 100,
                     "traceback": "B" * 100})
    summary = collect_worker_reports(scratch, results, max_text_chars=12)
    assert not summary["collection_failed"]
    item, = retained(results)
    assert item["error"] == "A" * 12
    assert item["traceback"] == "B" * 12
    assert item["error_truncated"] and item["traceback_truncated"]


def test_report_count_limit_stops_scan_and_reports_omission(roots):
    scratch, results = roots
    for number in range(4):
        report(scratch, {"status": "ok"}, job=f"client_lms_gi_{number}")
    summary = collect_worker_reports(scratch, results, max_reports=2)
    assert summary["reports_collected"] == 2
    assert summary["collection_failed"]
    assert summary["omitted"] == 1
    assert "report-count-limit" in {item["reason"] for item in summary["errors"]}


def test_input_and_serialized_output_have_aggregate_limits(roots):
    scratch, results = roots
    for number in range(5):
        report(scratch, {"status": "error", "error": "A" * 80},
               job=f"client_lms_gi_{number}")
    summary = collect_worker_reports(scratch, results, max_total_bytes=300)
    assert summary["collection_failed"]
    assert summary["input_bytes"] <= 300
    assert summary["retained_bytes"] <= 300
    assert sum(path.stat().st_size for path in (results / "worker-reports").glob("report-*.json")) <= 300


@pytest.mark.parametrize("component", [
    "scratch", "cache", "dincli", "local", "model_0", "jobs", "clients",
    ADDRESS, "client_lms_gi_1_output", "result.json",
])
def test_each_source_component_symlink_is_rejected(roots, tmp_path, component):
    scratch, results = roots
    path = report(scratch, {"status": "error", "error": "OUTSIDE_CANARY"})
    target = next(part for part in [*path.parents, path] if part.name == component)
    moved = tmp_path / "outside"
    target.rename(moved)
    target.symlink_to(moved, target_is_directory=moved.is_dir())
    summary = collect_worker_reports(scratch, results)
    assert summary["collection_failed"]
    assert summary["reports_collected"] == 0
    assert "OUTSIDE_CANARY" not in json.dumps(summary)
    assert not results.exists() or retained(results) == []


def test_nonregular_and_hardlinked_reports_are_rejected(roots, tmp_path):
    scratch, results = roots
    os.mkfifo(output_dir(scratch) / "result.json")
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text('{"status":"error","error":"HARDLINK_CANARY"}')
    os.link(unrelated, output_dir(scratch, role="auditors") / "result.json")
    summary = collect_worker_reports(scratch, results)
    assert {item["reason"] for item in summary["errors"]} == {
        "nonregular-result", "hardlinked-result",
    }
    assert retained(results) == []


@pytest.mark.parametrize("component", ["results", "worker-reports", "ancestor"])
def test_destination_symlinks_are_never_followed(roots, tmp_path, component):
    scratch, results = roots
    report(scratch, {"status": "ok"})
    outside = tmp_path / "outside"
    outside.mkdir()
    if component == "results":
        results.symlink_to(outside, target_is_directory=True)
    elif component == "worker-reports":
        results.mkdir()
        (results / "worker-reports").symlink_to(outside, target_is_directory=True)
    else:
        link = tmp_path / "link"
        link.symlink_to(outside, target_is_directory=True)
        results = link / "results"
    summary = collect_worker_reports(scratch, results)
    assert summary["collection_failed"]
    assert list(outside.iterdir()) == []


def test_existing_evidence_cannot_be_overwritten(roots):
    scratch, results = roots
    report(scratch, {"status": "ok"})
    assert not collect_worker_reports(scratch, results)["collection_failed"]
    before = list((results / "worker-reports").glob("report-*.json"))[0].read_bytes()
    report(scratch, {"status": "error", "error": "NEW"})
    assert collect_worker_reports(scratch, results)["collection_failed"]
    assert list((results / "worker-reports").glob("report-*.json"))[0].read_bytes() == before


def test_scan_and_error_summaries_are_bounded(roots):
    scratch, results = roots
    for number in range(20):
        output_dir(scratch, job=f"client_lms_gi_{number}")
    summary = collect_worker_reports(scratch, results, max_errors=2, max_entries=10)
    assert summary["collection_failed"]
    assert len(summary["errors"]) <= 2
    assert summary["errors_omitted"] > 0
    assert summary["reports_seen"] < 20


def test_write_failure_is_a_summary_error_and_leaves_no_partial_file(roots, monkeypatch):
    scratch, results = roots
    report(scratch, {"status": "ok"})

    def fail(*args, **kwargs):
        raise OSError(28, "simulated full disk")

    monkeypatch.setattr(os, "link", fail)
    summary = collect_worker_reports(scratch, results)
    assert summary["errors"][0]["reason"] == "result-write-failed"
    assert list((results / "worker-reports").iterdir()) == []


def test_results_inside_scratch_are_refused(roots):
    scratch, _ = roots
    summary = collect_worker_reports(scratch, scratch / "results")
    assert summary["collection_failed"]
    assert not (scratch / "results").exists()
