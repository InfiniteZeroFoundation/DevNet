"""Bounded subprocess evidence using generic Python children, never services."""

import errno
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.dincli import diagnostics
from tests.dincli.diagnostics import (
    Diagnostics, DiagnosticsLimitError, DiagnosticsWriteError,
)


def run(diag, tmp_path, script, **kwargs):
    return diag.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=dict(os.environ),
        timeout=kwargs.pop("timeout", 3), **kwargs,
    )


def logs(path):
    return b"".join(file.read_bytes() for file in sorted(path.glob("*.log")))


def dead(pid):
    # A grandchild can briefly remain a zombie until the host init reaps it.
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return True
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def assert_dead(pid):
    deadline = time.monotonic() + 2
    while not dead(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert dead(pid), f"Owned process {pid} remains alive"


def test_completed_process_stdin_streams_and_nonzero_are_preserved(tmp_path):
    diag = Diagnostics(tmp_path / "results")
    result = run(
        diag, tmp_path,
        'import sys; print(sys.stdin.read()); print("problem", file=sys.stderr); sys.exit(7)',
        input_text="input text", label="command",
    )
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.stdout == "input text\n"
    assert result.stderr == "problem\n"
    assert result.returncode == 7
    assert b"input text" in logs(diag.results_dir)
    entry = json.loads(diag.manifest_path.read_text())
    assert entry["outcome"] == "nonzero"
    assert entry["returncode"] == 7
    diag.close()


def test_large_stdin_and_empty_input_do_not_deadlock(tmp_path):
    diag = Diagnostics(tmp_path / "results")
    for value in ("", "a" * 500_000):
        result = run(
            diag, tmp_path,
            'import sys; print("ready", flush=True); print(len(sys.stdin.read()))',
            input_text=value,
        )
        assert result.stdout == f"ready\n{len(value)}\n"
    diag.close()


def test_timeout_keeps_partial_streams_and_kills_owned_descendant_only(tmp_path):
    diag = Diagnostics(tmp_path / "results")
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        script = (
            "import subprocess, sys, time, os; "
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
            "print(os.getpid(), p.pid, flush=True); "
            "print('partial error',file=sys.stderr,flush=True); time.sleep(30)"
        )
        with pytest.raises(subprocess.TimeoutExpired) as caught:
            run(diag, tmp_path, script, timeout=0.3)
        exc = caught.value
        child, descendant = map(int, exc.stdout.split())
        assert exc.stderr == b"partial error\n"
        assert_dead(child)
        assert_dead(descendant)
        assert unrelated.poll() is None
        assert exc.stdout in logs(diag.results_dir)
        assert '"outcome": "timeout"' in diag.manifest_path.read_text()
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=2)
        diag.close()


def test_real_sigint_retains_partial_output_and_cleans_up(tmp_path):
    results = tmp_path / "results"
    supervisor = r'''
import os, signal, sys, threading
from pathlib import Path
from tests.dincli.diagnostics import Diagnostics
root = Path(sys.argv[1])
diag = Diagnostics(root / "results")
script = "import os,time; print(os.getpid(),flush=True); time.sleep(30)"
timer = threading.Timer(.3, lambda: os.kill(os.getpid(), signal.SIGINT))
timer.start()
try:
    diag.run([sys.executable,"-c",script],cwd=root,env=dict(os.environ),timeout=10)
except KeyboardInterrupt:
    print("interrupted")
finally:
    timer.cancel()
    diag.close()
'''
    completed = subprocess.run(
        [sys.executable, "-c", supervisor, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=5,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "interrupted\n"
    assert_dead(int(logs(results).strip()))
    assert '"outcome": "interrupted"' in next(results.glob("*.jsonl")).read_text()


@pytest.mark.parametrize("stream_limit,total_limit", [(64, 1000), (1000, 64)])
def test_continuous_output_limits_fail_and_stop_the_process(tmp_path, stream_limit, total_limit):
    diag = Diagnostics(
        tmp_path / "results", stream_limit=stream_limit, total_limit=total_limit,
    )
    pid_path = tmp_path / "pid"
    script = (
        "import os,sys,time; from pathlib import Path; "
        f"Path({str(pid_path)!r}).write_text(str(os.getpid())); "
        "sys.stdout.write('x'*100000); sys.stdout.flush(); time.sleep(30)"
    )
    with pytest.raises(DiagnosticsLimitError):
        run(diag, tmp_path, script)
    assert_dead(int(pid_path.read_text()))
    assert len(logs(diag.results_dir)) <= min(stream_limit, total_limit)
    entry = json.loads(diag.manifest_path.read_text())
    assert entry["outcome"] == "diagnostics_limit"
    assert entry["truncated"] is True
    diag.close()


def test_aggregate_budget_is_shared_across_commands(tmp_path):
    diag = Diagnostics(tmp_path / "results", stream_limit=100, total_limit=12)
    assert run(diag, tmp_path, "print('12345')").returncode == 0
    with pytest.raises(DiagnosticsLimitError):
        run(diag, tmp_path, "print('123456789')")
    assert len(logs(diag.results_dir)) == 12
    diag.close()


def test_service_sink_keeps_draining_after_limit_and_surfaces_failure(tmp_path):
    diag = Diagnostics(tmp_path / "results", stream_limit=64)
    sink = diag.open_stream("noisy-service")
    process = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdout.write('x'*2000000); sys.stdout.flush()"],
        stdout=sink, stderr=subprocess.STDOUT, start_new_session=True,
    )
    try:
        assert process.wait(timeout=3) == 0  # A full capped pipe must not block.
        with pytest.raises(DiagnosticsLimitError):
            sink.close()
        with pytest.raises(DiagnosticsLimitError):
            diag.check()
        assert sink.path.stat().st_size == 64
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        with pytest.raises(DiagnosticsLimitError):
            diag.close()


def test_write_failure_stops_owned_process(tmp_path, monkeypatch):
    original_open = Diagnostics._open_file

    class FullDisk:
        def __init__(self, file):
            self.file = file

        def tell(self):
            return self.file.tell()

        def write(self, data):
            raise OSError(errno.ENOSPC, "simulated disk full")

        def close(self):
            self.file.close()

    def patched_open(owner, name):
        file = original_open(owner, name)
        return FullDisk(file) if name.endswith(".log") else file

    diag = Diagnostics(tmp_path / "results")
    monkeypatch.setattr(Diagnostics, "_open_file", patched_open)
    pid_path = tmp_path / "pid"
    script = (
        "import os,time; from pathlib import Path; "
        f"Path({str(pid_path)!r}).write_text(str(os.getpid())); "
        "print('output',flush=True); time.sleep(30)"
    )
    with pytest.raises(DiagnosticsWriteError):
        run(diag, tmp_path, script)
    assert_dead(int(pid_path.read_text()))
    diag.close()


def test_manifest_failure_does_not_replace_timeout(tmp_path, monkeypatch, capsys):
    diag = Diagnostics(tmp_path / "results")

    def fail(*args, **kwargs):
        raise DiagnosticsWriteError("simulated recording failure")

    monkeypatch.setattr(diag, "record", fail)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        run(diag, tmp_path, "import time; print('partial',flush=True); time.sleep(30)", timeout=0.2)
    assert caught.value.stdout == b"partial\n"
    assert "DiagnosticsWriteError" in capsys.readouterr().err
    assert any("DiagnosticsWriteError" in note for note in caught.value.__notes__)
    diag.close()


def test_manifest_is_reserved_and_bounded_and_does_not_dump_secrets(tmp_path):
    diag = Diagnostics(tmp_path / "results", manifest_limit=256)
    result = diag.run(
        [sys.executable, "-c", "pass", "argument-canary"],
        cwd=tmp_path, env={**os.environ, "SECRET": "environment-canary"},
        input_text="stdin-canary", timeout=3, label="../../unsafe label",
    )
    assert result.returncode == 0
    for _ in range(100):
        diag.record("bounded", "ok", count=1)
    manifest = diag.manifest_path.read_text()
    assert "argument-canary" not in manifest
    assert "environment-canary" not in manifest
    assert "stdin-canary" not in manifest
    assert '"omitted":true' in manifest
    assert diag.manifest_path.stat().st_size <= 256
    assert all(file.parent == diag.results_dir for file in diag.results_dir.iterdir())
    diag.close()


def test_spawn_failure_is_recorded_and_closes_created_logs(tmp_path):
    diag = Diagnostics(tmp_path / "results")
    with pytest.raises(FileNotFoundError):
        diag.run([str(tmp_path / "absent")], cwd=tmp_path, env={}, timeout=1)
    assert json.loads(diag.manifest_path.read_text())["outcome"] == "error"
    diag.close()


@pytest.mark.parametrize("ancestor", [False, True])
def test_results_symlink_or_symlink_ancestor_is_rejected(tmp_path, ancestor):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(outside, target_is_directory=True)
    target = link / "results" if ancestor else link
    with pytest.raises(DiagnosticsWriteError):
        Diagnostics(target)
    assert list(outside.iterdir()) == []


def test_preexisting_log_symlink_is_never_followed(tmp_path):
    diag = Diagnostics(tmp_path / "results")
    outside = tmp_path / "canary"
    outside.write_text("preserve")
    # The manifest consumes sequence 1; first command stdout is sequence 2.
    (diag.results_dir / "0002_command_stdout.log").symlink_to(outside)
    with pytest.raises(DiagnosticsWriteError):
        run(diag, tmp_path, "print('must not execute')")
    assert outside.read_text() == "preserve"
    diag.close()


@pytest.mark.parametrize("failure", ["pipe", "thread"])
def test_service_stream_initialization_failure_closes_open_resources(tmp_path, monkeypatch, failure):
    diag = Diagnostics(tmp_path / "results")
    before = len(list(Path("/proc/self/fd").iterdir()))

    def fail(*args, **kwargs):
        raise OSError("simulated stream setup failure")

    if failure == "pipe":
        monkeypatch.setattr(diagnostics.os, "pipe", fail)
    else:
        monkeypatch.setattr(diagnostics.threading.Thread, "start", fail)
    with pytest.raises(OSError, match="simulated"):
        diag.open_stream("service")
    assert len(list(Path("/proc/self/fd").iterdir())) == before
    diag.close()


def test_invalid_text_encoding_raises_but_retains_original_bytes(tmp_path):
    diag = Diagnostics(tmp_path / "results")
    with pytest.raises(UnicodeDecodeError):
        run(diag, tmp_path, "import os; os.write(1,b'\\xff')")
    assert logs(diag.results_dir) == b"\xff"
    diag.close()


@pytest.mark.parametrize("exit_code", [0, 7])
def test_manifest_failure_is_fatal_even_after_command_exit(tmp_path, monkeypatch, exit_code):
    with Diagnostics(tmp_path / "results") as diag:
        def fail(*args, **kwargs):
            raise DiagnosticsWriteError("simulated manifest failure")

        monkeypatch.setattr(diag, "record", fail)
        with pytest.raises(DiagnosticsWriteError) as caught:
            run(diag, tmp_path, f"import sys; print('retained'); sys.exit({exit_code})")
        assert logs(diag.results_dir) == b"retained\n"
        if exit_code:
            assert f"Command exited with status {exit_code}" in caught.value.__notes__


def test_short_write_counts_retained_bytes_before_failing(tmp_path, monkeypatch):
    with Diagnostics(tmp_path / "results", total_limit=10) as diag:
        original_open = diag._open_file

        class ShortWriter:
            def __init__(self, file):
                self.file = file

            def write(self, data):
                return self.file.write(data[:3])

            def close(self):
                self.file.close()

        monkeypatch.setattr(diag, "_open_file", lambda name: ShortWriter(original_open(name)))
        with pytest.raises(DiagnosticsWriteError, match="Short"):
            run(diag, tmp_path, "print('abcdefghij')")
        assert len(logs(diag.results_dir)) == diag._retained == 3


def test_final_cleanup_summary_survives_scratch_and_diagnostics_removal(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    results = tmp_path / "results"
    diag = Diagnostics(results)
    diag.close()
    scratch.rmdir()
    summary = diagnostics.write_cleanup_summary(
        results, scratch_removed=True, errors=["diagnostics_close:DiagnosticsWriteError"],
    )
    assert summary.name == "cleanup.json"
    assert json.loads(summary.read_text()) == {
        "scratch_removed": True,
        "errors": ["diagnostics_close:DiagnosticsWriteError"],
        "errors_omitted": 0,
    }


def test_cleanup_summary_budget_and_metadata_allowlist(tmp_path):
    summary = diagnostics.write_cleanup_summary(
        tmp_path / "results", scratch_removed=False,
        errors=["/private/canary", "ENV=secret-canary"] + ["stage:OSError"] * 300,
    )
    body = summary.read_text()
    assert "canary" not in body
    assert summary.stat().st_size <= 64 * 1024
    record = json.loads(body)
    assert len(record["errors"]) == 200
    assert record["errors"][:2] == ["invalid_error_metadata"] * 2
    assert record["errors_omitted"] == 102


@pytest.mark.parametrize("symlink_kind", ["ancestor", "leaf"])
def test_cleanup_summary_refuses_symlinks(tmp_path, symlink_kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("preserve")
    results = tmp_path / "results"
    if symlink_kind == "ancestor":
        results.symlink_to(outside, target_is_directory=True)
    else:
        results.mkdir()
        (results / "cleanup.json").symlink_to(sentinel)
    with pytest.raises(DiagnosticsWriteError):
        diagnostics.write_cleanup_summary(results, scratch_removed=False, errors=[])
    assert sentinel.read_text() == "preserve"
    assert list(outside.iterdir()) == [sentinel]


def test_cleanup_summary_write_failure_closes_descriptors(tmp_path, monkeypatch):
    before = len(list(Path("/proc/self/fd").iterdir()))

    def fail(*args, **kwargs):
        raise OSError(errno.ENOSPC, "simulated")

    monkeypatch.setattr(diagnostics.os, "write", fail)
    with pytest.raises(DiagnosticsWriteError):
        diagnostics.write_cleanup_summary(tmp_path / "results", scratch_removed=False, errors=[])
    assert len(list(Path("/proc/self/fd").iterdir())) == before


@pytest.mark.parametrize("failure", ["writer", "join"])
def test_service_close_failure_still_stops_reader_closes_capture_and_records(tmp_path, monkeypatch, failure):
    diag = Diagnostics(tmp_path / "results")
    sink = diag.open_stream("service")
    if failure == "writer":
        original_close = diagnostics.os.close
        writer = sink.fileno()
        calls = 0

        def close(fd):
            nonlocal calls
            if fd == writer and calls == 0:
                calls += 1
                raise OSError(errno.EPERM, "simulated writer close failure")
            return original_close(fd)

        monkeypatch.setattr(diagnostics.os, "close", close)
        expected = PermissionError
    else:
        original_join = sink._thread.join
        calls = 0

        def join(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise KeyboardInterrupt()
            return original_join(*args, **kwargs)

        monkeypatch.setattr(sink._thread, "join", join)
        expected = KeyboardInterrupt
    with pytest.raises(expected):
        sink.close()
    assert not sink._thread.is_alive()
    assert sink._capture.file.closed
    assert json.loads(diag.manifest_path.read_text())["outcome"] == expected.__name__
    # A failed writer close remains retryable when Diagnostics closes the sink.
    with pytest.raises(expected):
        diag.close()
    assert sink._writer is None


def test_persistent_cleanup_failure_is_recorded_and_survives_close(tmp_path):
    diag = Diagnostics(tmp_path / "results")
    primary = PermissionError("must not enter metadata")
    diag.note_failure("owned_service", primary)
    with pytest.raises(PermissionError) as caught:
        diag.check()
    assert caught.value is primary
    manifest = diag.manifest_path.read_text()
    assert "must not enter metadata" not in manifest
    assert json.loads(manifest)["error_type"] == "PermissionError"
    with pytest.raises(PermissionError) as caught:
        diag.close()
    assert caught.value is primary
    assert diag._manifest.closed
    assert diag._dir_fd is None


def test_persistent_failure_survives_manifest_recording_failure(tmp_path, monkeypatch):
    diag = Diagnostics(tmp_path / "results")
    primary = PermissionError("primary")

    def fail(*args, **kwargs):
        raise DiagnosticsWriteError("disk full")

    monkeypatch.setattr(diag, "record", fail)
    with pytest.raises(DiagnosticsWriteError):
        diag.note_failure("service", primary)
    with pytest.raises(PermissionError) as caught:
        diag.close()
    assert caught.value is primary


def test_failed_cleanup_summary_never_publishes_partial_json(tmp_path, monkeypatch):
    results = tmp_path / "results"
    original_write = diagnostics.os.write

    def short(fd, data):
        return original_write(fd, data[:3])

    monkeypatch.setattr(diagnostics.os, "write", short)
    with pytest.raises(DiagnosticsWriteError):
        diagnostics.write_cleanup_summary(results, scratch_removed=True, errors=[])
    assert list(results.iterdir()) == []


@pytest.mark.parametrize("exit_code", [0, 7])
def test_manifest_failure_inside_handled_exception(tmp_path, monkeypatch, exit_code):
    with Diagnostics(tmp_path / "results") as diag:
        def fail(*args, **kwargs):
            raise DiagnosticsWriteError("simulated manifest failure")

        monkeypatch.setattr(diag, "record", fail)
        try:
            raise ValueError("caller is handling this")
        except ValueError:
            with pytest.raises(DiagnosticsWriteError):
                run(diag, tmp_path, f"import sys; sys.exit({exit_code})")


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_cleanup_summary_finalization_inside_handled_exception(tmp_path, monkeypatch, failure):
    original_unlink = diagnostics.os.unlink

    def fail_unlink(*args, **kwargs):
        original_unlink(*args, **kwargs)
        raise failure("simulated unlink failure")

    monkeypatch.setattr(diagnostics.os, "unlink", fail_unlink)
    try:
        raise ValueError("caller is handling this")
    except ValueError:
        with pytest.raises(DiagnosticsWriteError, match="Cannot close") as caught:
            diagnostics.write_cleanup_summary(
                tmp_path / "results", scratch_removed=True, errors=[],
            )
    assert isinstance(caught.value.__cause__, failure)
    assert json.loads((tmp_path / "results" / "cleanup.json").read_text())["scratch_removed"]


@pytest.mark.parametrize("resource", ["stdout", "stderr", "stdin", "selector"])
@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_finalization_failure_preserves_timeout_and_finishes_evidence(
    tmp_path, monkeypatch, resource, failure,
):
    original_popen = diagnostics.subprocess.Popen
    original_selector = diagnostics.selectors.DefaultSelector
    original_capture_close = diagnostics._Capture.close
    processes, selectors_created, closed_captures = [], [], []

    class FailingClose:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def close(self):
            self.wrapped.close()
            raise failure("injected close failure")

    def popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        if resource != "selector":
            setattr(process, resource, FailingClose(getattr(process, resource)))
        processes.append(process)
        return process

    def selector():
        instance = original_selector()
        selectors_created.append(instance)
        return FailingClose(instance) if resource == "selector" else instance

    def close_capture(capture):
        original_capture_close(capture)
        closed_captures.append(capture)

    monkeypatch.setattr(diagnostics.subprocess, "Popen", popen)
    monkeypatch.setattr(diagnostics.selectors, "DefaultSelector", selector)
    monkeypatch.setattr(diagnostics._Capture, "close", close_capture)
    with Diagnostics(tmp_path / "results") as diag:
        with pytest.raises(subprocess.TimeoutExpired) as caught:
            run(diag, tmp_path, "import time; time.sleep(30)", timeout=0.2,
                input_text="x" * 1_000_000)
        assert any(failure.__name__ in note for note in caught.value.__notes__)
        assert processes[0].poll() is not None
        assert all(getattr(processes[0], name).closed for name in ("stdin", "stdout", "stderr"))
        assert selectors_created[0].get_map() is None
        assert len(closed_captures) == 2
        assert all(capture.file.closed for capture in closed_captures)
        assert json.loads(diag.manifest_path.read_text())["outcome"] == "timeout"
