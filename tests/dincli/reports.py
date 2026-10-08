"""Collect bounded, sanitized worker evidence from isolated scratch state.

There is no harness job inventory yet. We therefore recognize only the current
local model cache and role-specific job names, and can detect missing results
only for discovered output directories. This is diagnostics, not proof that all
expected jobs ran. Inputs, wallets, salts and success payloads are never copied.
Error/traceback text is untrusted application output, not generally redactable.
"""

import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path


_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
_MODEL = re.compile(r"model_([0-9]{1,10})\Z")
_JOBS = {
    "clients": re.compile(r"client_lms_gi_[0-9]{1,10}_output\Z"),
    "auditors": re.compile(
        r"auditor_score_gi_[0-9]{1,10}_batch_[0-9]{1,10}"
        r"_lm_[0-9]{1,10}_output\Z"
    ),
    "aggregators": re.compile(
        r"aggregator_t[12]_gi_[0-9]{1,10}_batch_[0-9]{1,10}_output\Z"
    ),
}


def _absolute(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("diagnostic paths must be absolute without parent traversal")
    return path


def _open_directory(path, *, create=False):
    """Walk from / using directory descriptors; never follow a component link."""
    fd = os.open("/", _DIRECTORY)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, _DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _atomic_json(directory_fd, name, payload):
    temporary = f".report-{uuid.uuid4().hex}.tmp"
    fd = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600, dir_fd=directory_fd,
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
        # link is atomic and refuses a preexisting target (including symlinks).
        os.link(
            temporary, name, src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd, follow_symlinks=False,
        )
    finally:
        os.unlink(temporary, dir_fd=directory_fd)


class _ScanLimit(Exception):
    pass


def collect_worker_reports(
    scratch: Path, results_dir: Path, *, max_file_bytes=1024 * 1024,
    max_reports=200, max_total_bytes=20 * 1024 * 1024,
    max_text_chars=16 * 1024, max_errors=50, max_entries=10000,
) -> dict:
    """Return a bounded summary, retaining sanitized JSON under worker-reports.

    All errors (including destination failures and budget omissions) set
    ``collection_failed``. The caller must still clean up and preserve any
    primary execution failure. Existing worker-reports directories are refused
    so repeated collection cannot overwrite earlier evidence. Source reads and
    destination writes use no-follow directory descriptors, including ancestors.
    Budgets count raw input bytes, bounding both parsing and retained payloads.
    """
    summary = {
        "collection_failed": False, "reports_seen": 0, "reports_collected": 0,
        "ok": 0, "error": 0, "input_bytes": 0, "retained_bytes": 0,
        "omitted": 0, "errors": [], "errors_omitted": 0,
        "inventory": "discovered-local-output-directories-only",
    }

    def problem(reason, identity=None):
        summary["collection_failed"] = True
        if len(summary["errors"]) < max_errors:
            summary["errors"].append({"reason": reason, **(identity or {})})
        else:
            summary["errors_omitted"] += 1

    descriptors = []
    scanned = 0
    destination = None

    def entries(fd):
        nonlocal scanned
        with os.scandir(fd) as iterator:
            for entry in iterator:
                scanned += 1
                if scanned > max_entries:
                    raise _ScanLimit
                yield entry.name

    def descend(fd, name, visit, identity=None):
        try:
            child = os.open(name, _DIRECTORY, dir_fd=fd)
        except FileNotFoundError:
            return
        except OSError:
            problem("unsafe-or-unreadable-directory", identity)
            return
        try:
            visit(child)
        finally:
            os.close(child)

    def read_report(fd, identity):
        summary["reports_seen"] += 1
        if summary["reports_seen"] > max_reports:
            summary["omitted"] += 1
            problem("report-count-limit", identity)
            raise _ScanLimit
        try:
            report = os.open(
                "result.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=fd,
            )
        except FileNotFoundError:
            problem("missing-result", identity)
            return
        except OSError:
            problem("unsafe-or-unreadable-result", identity)
            return
        try:
            metadata = os.fstat(report)
            if not stat.S_ISREG(metadata.st_mode):
                problem("nonregular-result", identity)
                return
            # Hardlinks could alias unrelated sensitive regular files.
            if metadata.st_nlink != 1:
                problem("hardlinked-result", identity)
                return
            remaining = max_total_bytes - summary["input_bytes"]
            budget = min(max_file_bytes, remaining)
            if metadata.st_size > budget:
                summary["omitted"] += 1
                problem(
                    "report-size-limit" if metadata.st_size > max_file_bytes
                    else "report-total-limit", identity,
                )
                return
            with os.fdopen(report, "rb", closefd=False) as stream:
                raw = stream.read(budget + 1)
            summary["input_bytes"] += min(len(raw), budget)
            if len(raw) > budget:
                summary["omitted"] += 1
                problem("report-read-limit", identity)
                return
        except OSError:
            problem("result-read-failed", identity)
            return
        finally:
            os.close(report)
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            problem("malformed-result", identity)
            return
        if not isinstance(data, dict) or data.get("status") not in ("ok", "error"):
            problem("invalid-result-schema", identity)
            return
        sanitized = {**identity, "status": data["status"]}
        if data["status"] == "error":
            for field in ("error", "traceback"):
                value = data.get(field)
                if value is not None and not isinstance(value, str):
                    problem("invalid-result-schema", identity)
                    return
                if value is not None:
                    sanitized[field] = value[:max_text_chars]
                    if len(value) > max_text_chars:
                        sanitized[f"{field}_truncated"] = True
        payload = (json.dumps(sanitized, ensure_ascii=True) + "\n").encode("utf-8")
        # JSON escaping can expand text; also bound actual retained bytes.
        if summary["retained_bytes"] + len(payload) > max_total_bytes:
            summary["omitted"] += 1
            problem("retained-report-total-limit", identity)
            return
        try:
            _atomic_json(
                destination, f"report-{summary['reports_collected'] + 1:04d}.json",
                payload,
            )
        except OSError:
            problem("result-write-failed", identity)
            return
        summary["reports_collected"] += 1
        summary[data["status"]] += 1
        summary["retained_bytes"] += len(payload)

    def visit_model(fd, model):
        def visit_jobs(jobs_fd):
            for role, pattern in _JOBS.items():
                def visit_role(role_fd, role=role, pattern=pattern):
                    for address in entries(role_fd):
                        if not _ADDRESS.fullmatch(address):
                            continue

                        def visit_address(address_fd):
                            for name in entries(address_fd):
                                if pattern.fullmatch(name):
                                    participant = hashlib.sha256(
                                        address.lower().encode("ascii"),
                                    ).hexdigest()[:12]
                                    identity = {
                                        "model": model, "role": role,
                                        "job": name[:-7], "participant": participant,
                                    }
                                    descend(
                                        address_fd, name,
                                        lambda output_fd: read_report(output_fd, identity),
                                        identity,
                                    )
                        descend(role_fd, address, visit_address)
                descend(jobs_fd, role, visit_role)
        descend(fd, "jobs", visit_jobs)

    try:
        budgets = (max_file_bytes, max_reports, max_total_bytes,
                   max_text_chars, max_errors, max_entries)
        if any(not isinstance(value, int) or value <= 0 for value in budgets):
            raise ValueError("budgets must be positive integers")
        max_errors = min(max_errors, 50)
        scratch = _absolute(scratch)
        results_dir = _absolute(results_dir)
        if results_dir == scratch or scratch in results_dir.parents:
            raise ValueError("results must be outside scratch")
        source = _open_directory(scratch)
        descriptors.append(source)
        result_root = _open_directory(results_dir, create=True)
        descriptors.append(result_root)
        os.mkdir("worker-reports", mode=0o700, dir_fd=result_root)
        destination = os.open("worker-reports", _DIRECTORY, dir_fd=result_root)
        descriptors.append(destination)

        def visit_network(network_fd):
            for model in entries(network_fd):
                if _MODEL.fullmatch(model):
                    descend(network_fd, model, lambda fd: visit_model(fd, model))

        descend(source, "cache", lambda cache: descend(
            cache, "dincli", lambda dincli: descend(dincli, "local", visit_network),
        ))
    except _ScanLimit:
        problem("scan-stopped-at-limit")
    except (OSError, ValueError):
        problem("collection-path-or-destination-failed")
    finally:
        if destination is not None:
            payload = (json.dumps(summary, ensure_ascii=True) + "\n").encode("utf-8")
            while len(payload) > 64 * 1024 and summary["errors"]:
                summary["errors"].pop()
                summary["errors_omitted"] += 1
                payload = (json.dumps(summary, ensure_ascii=True) + "\n").encode("utf-8")
            try:
                _atomic_json(destination, "summary.json", payload)
            except OSError:
                problem("summary-write-failed")
        for fd in reversed(descriptors):
            os.close(fd)
    return summary
