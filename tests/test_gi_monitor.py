import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from dincli.dind import gi_monitor
from dincli.sdk.state import GIState

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
A = "0x" + "ab" * 20
B = "0x" + "cd" * 20


def model(phase="LMSstarted", age=60, gi=1, address=A):
    return dict(coordinator=address, gi=gi, state=phase,
                state_code=int(GIState[phase]), observed_for_s=age)


def snapshot(tick, *rows):
    stamp = START + timedelta(seconds=tick)
    timed_rows = []
    for row in rows:
        row = row.copy()
        if isinstance(row.get("observed_for_s"), int):
            since = stamp - timedelta(seconds=row["observed_for_s"])
            row.setdefault("observed_since", since.isoformat())
        timed_rows.append(row)
    return {"checked_at": stamp.isoformat(), "instance_id": "a" * 32,
            "checks": {"config": {"ok": True, "network": "local"}, "rpc": {"ok": True, "block": 123}},
            "models": timed_rows}


def detector_at(tick=59):
    return gi_monitor.Detector(60, clock=lambda: START + timedelta(seconds=tick))



def kinds(detector, tick, *rows):
    return [e["event"] for e in detector.observe(snapshot(tick, *rows))]


@pytest.mark.parametrize(("next_phase", "gi"), [("LMSclosed", 1), ("GIended", 1), ("GIstarted", 2)])
def test_alert_until_progress(next_phase, gi):
    detector = detector_at()
    assert kinds(detector, 0, model(age=59)) == []
    assert kinds(detector, 1, model()) == ["stalled"]
    assert kinds(detector, 1, model()) == []
    assert kinds(detector, 2, model(age=61)) == []
    assert kinds(detector, 3, model(age=0)) == ["observation_reset"]
    assert kinds(detector, 4, model(age=1)) == []
    assert kinds(detector, 2, model("GIended")) == []
    assert kinds(detector, 5, model("GIstarted")) == ["regressed_observation"]
    assert kinds(detector, 6, model(next_phase, age=0, gi=gi)) == ["recovered"]


@pytest.mark.parametrize(("phase", "gi"), [("AwaitingGenesisModel", 0), ("GenesisModelCreated", 0), ("GIended", 1)])
def test_inactive(phase, gi):
    assert kinds(detector_at(), 1, model(phase, gi=gi)) == []


@pytest.mark.parametrize("bad", [
    {"error": "secret"}, {"observed_for_s": True}, {"gi": -1}, {"state": []},
    {"state": "unknown"}, {"state_code": 0}, {"observed_for_s": None},
])
def test_models_survive_partial_failure(bad):
    detector = detector_at()
    assert kinds(detector, 0, model(), model(address=B)) == ["stalled", "stalled"]
    result = detector.observe(snapshot(1, model() | bad, model("GIended", age=0, address=B)))
    assert [(e["event"], e["coordinator"]) for e in result] == [
        ("model_unavailable", A), ("recovered", B)]
    assert "secret" not in str(result)
    assert kinds(detector, 2) == ["model_missing", "model_missing"]
    assert kinds(detector, 3, model("LMSclosed", age=0), model("GIended", age=2, address=B)) == ["recovered"]


def test_poll_failures_and_partial_503(monkeypatch):
    detector = detector_at()
    connection = Mock()
    factory = Mock(return_value=connection)
    monkeypatch.setattr(gi_monitor, "HTTPConnection", factory)
    response = connection.getresponse.return_value
    response.length = 0
    response.status = 503
    first = snapshot(0, model())
    first["checks"]["signer"] = {"ok": False}
    failure = snapshot(1, model("GIended"))
    failure["checks"]["rpc"] = {"ok": False, "error": "secret"}
    response.read.side_effect = [
        json.dumps(first), TimeoutError("secret"), b"secret", b"[]",
        json.dumps(failure), json.dumps(snapshot(2, model("GIended", age=0)))]
    for expected in ("stalled", "poll_failed", "invalid_snapshot", "invalid_snapshot",
                     "check_unavailable", "recovered"):
        [event] = gi_monitor.poll(detector, 8787)
        assert event["event"] == expected
        assert "secret" not in str(event)
    factory.assert_called_with("127.0.0.1", 8787, timeout=5)
    connection.request.assert_called_with("GET", "/health")
    assert connection.close.call_count == 6


def test_failed_refresh_supersedes_older_progress():
    detector = detector_at()
    assert kinds(detector, 1, model()) == ["stalled"]
    failure = snapshot(3)
    failure["checks"]["rpc"] = {"ok": False}
    assert detector.observe(failure) == [{"event": "check_unavailable", "check": "rpc"}]
    assert kinds(detector, 2, model("GIended", age=0)) == []
    assert kinds(detector, 4, model("GIended", age=0)) == ["recovered"]


def test_other_network_cannot_clear_open_alert_or_leak_config():
    detector = detector_at()
    assert kinds(detector, 0, model()) == ["stalled"]
    other = snapshot(1, model("GIended", age=0))
    other["checks"]["config"]["network"] = "private-alias"
    assert detector.observe(other) == [{"event": "network_changed"}]
    assert kinds(detector, 2, model("GIended", age=0)) == ["recovered"]


def test_daemon_restart_preserves_alert_even_when_age_has_caught_up():
    now = [START]
    detector = gi_monitor.Detector(60, clock=lambda: now[0])
    assert kinds(detector, 0, model()) == ["stalled"]
    now[0] += timedelta(seconds=61)
    restarted = snapshot(61, model())
    restarted["instance_id"] = "b" * 32
    assert [e["event"] for e in detector.observe(restarted)] == ["daemon_restarted", "observation_reset"]


def test_invalid_freshness_cannot_poison_subsequent_snapshots():
    detector = detector_at()
    assert kinds(detector, -120, model()) == ["snapshot_out_of_date"]
    assert kinds(detector, 600, model()) == ["snapshot_out_of_date"]
    assert kinds(detector, 0, model()) == ["stalled"]


def test_contradictory_timing_and_impossible_gi_cannot_clear_alert():
    detector = detector_at()
    assert kinds(detector, 0, model()) == ["stalled"]
    assert kinds(detector, 1, model("LMSclosed")) == ["inconsistent_observation"]
    assert kinds(detector, 2, model(gi=2**256, age=0)) == ["model_unavailable"]
    assert kinds(detector, 3, model("GIended", age=0) | {"observed_since": "invalid"}) == ["model_unavailable"]
    assert kinds(detector, 4, model("GIended", age=0)) == ["recovered"]


def test_progress_into_an_already_stalled_phase():
    now = [START]
    detector = gi_monitor.Detector(60, clock=lambda: now[0])
    assert kinds(detector, 0, model()) == ["stalled"]
    now[0] += timedelta(seconds=90)
    assert kinds(detector, 90, model("LMSclosed", age=60)) == ["recovered", "stalled"]


def test_overlapping_same_phase_timer_cannot_trigger_stall():
    detector = detector_at()
    assert kinds(detector, 0, model(age=5)) == []
    assert kinds(detector, 1, model(age=60)) == ["inconsistent_observation"]
    assert kinds(detector, 55, model(age=60)) == ["stalled"]


def test_malformed_rpc_block_cannot_clear_alert():
    detector = detector_at()
    assert kinds(detector, 0, model()) == ["stalled"]
    malformed = snapshot(1, model("GIended", age=0))
    malformed["checks"]["rpc"]["block"] = True
    assert detector.observe(malformed) == [{"event": "check_unavailable", "check": "rpc"}]
    assert kinds(detector, 2, model("GIended", age=0)) == ["recovered"]


def test_request_deadline_discards_response_and_keeps_open_alert(monkeypatch):
    detector = detector_at()
    assert kinds(detector, 0, model()) == ["stalled"]
    connection = Mock()
    monkeypatch.setattr(gi_monitor, "HTTPConnection", Mock(return_value=connection))
    timer = Mock()
    monkeypatch.setattr(gi_monitor, "Timer", timer)
    monkeypatch.setattr(gi_monitor.time, "monotonic", Mock(side_effect=[100, 101, 105]))
    response = connection.getresponse.return_value
    response.status = 200
    response.length = 0
    response.read.return_value = json.dumps(snapshot(1, model("GIended", age=0)))
    assert gi_monitor.poll(detector, 8787) == [{"event": "poll_failed"}]
    seconds_remaining, interrupt = timer.call_args.args
    assert seconds_remaining == 4
    interrupt()
    connection.sock.shutdown.assert_called_once_with(gi_monitor.socket.SHUT_RDWR)
    assert kinds(detector, 2, model("GIended", age=0)) == ["recovered"]
