import json
from unittest.mock import Mock

import pytest

from dincli.dind import gi_monitor
from dincli.sdk.state import GIState

A = "0x" + "ab" * 20
B = "0x" + "cd" * 20


def model(phase="LMSstarted", age=60, gi=1, address=A):
    return dict(coordinator=address, gi=gi, state=phase,
                state_code=int(GIState[phase]), observed_for_s=age)


def snapshot(tick, *rows):
    return {"checked_at": f"2026-01-01T00:00:{tick:02}+00:00",
            "checks": {"config": {"ok": True}, "rpc": {"ok": True}},
            "models": list(rows)}


def kinds(detector, tick, *rows):
    return [e["event"] for e in detector.observe(snapshot(tick, *rows))]


@pytest.mark.parametrize(("next_phase", "gi"), [("LMSclosed", 1), ("GIended", 1), ("GIstarted", 2)])
def test_alert_until_progress(next_phase, gi):
    detector = gi_monitor.Detector(60)
    assert kinds(detector, 0, model(age=59)) == []
    assert kinds(detector, 1, model()) == ["stalled"]
    assert kinds(detector, 1, model()) == []
    assert kinds(detector, 2, model(age=90)) == []
    assert kinds(detector, 3, model(age=0)) == ["observation_reset"]
    assert kinds(detector, 4, model()) == []
    assert kinds(detector, 2, model("GIended")) == []
    assert kinds(detector, 5, model("GIstarted")) == ["regressed_observation"]
    assert kinds(detector, 6, model(next_phase, age=0, gi=gi)) == ["recovered"]


@pytest.mark.parametrize(("phase", "gi"), [("AwaitingGenesisModel", 0), ("GenesisModelCreated", 0), ("GIended", 1)])
def test_inactive(phase, gi):
    assert kinds(gi_monitor.Detector(1), 1, model(phase, gi=gi)) == []


@pytest.mark.parametrize("bad", [
    {"error": "secret"}, {"observed_for_s": True}, {"gi": -1}, {"state": []},
    {"state": "unknown"}, {"state_code": 0}, {"observed_for_s": None},
])
def test_models_survive_partial_failure(bad):
    detector = gi_monitor.Detector(60)
    assert kinds(detector, 0, model(), model(address=B)) == ["stalled", "stalled"]
    result = detector.observe(snapshot(1, model() | bad, model("GIended", address=B)))
    assert [(e["event"], e["coordinator"]) for e in result] == [
        ("model_unavailable", A), ("recovered", B)]
    assert "secret" not in str(result)
    assert kinds(detector, 2) == ["model_missing", "model_missing"]
    assert kinds(detector, 3, model("LMSclosed"), model("GIended", address=B)) == ["recovered", "stalled"]


def test_poll_failures_and_partial_503(monkeypatch):
    detector = gi_monitor.Detector(60)
    connection = Mock()
    factory = Mock(return_value=connection)
    monkeypatch.setattr(gi_monitor, "HTTPConnection", factory)
    response = connection.getresponse.return_value
    response.status = 503
    first = snapshot(0, model())
    first["checks"]["signer"] = {"ok": False}
    failure = snapshot(1, model("GIended"))
    failure["checks"]["rpc"] = {"ok": False, "error": "secret"}
    response.read.side_effect = [
        json.dumps(first), TimeoutError("secret"), b"secret", b"[]",
        json.dumps(failure), json.dumps(snapshot(2, model("GIended")))]
    for expected in ("stalled", "poll_failed", "invalid_snapshot", "invalid_snapshot",
                     "check_unavailable", "recovered"):
        [event] = gi_monitor.poll(detector, 8787)
        assert event["event"] == expected
        assert "secret" not in str(event)
    factory.assert_called_with("127.0.0.1", 8787, timeout=5)
    connection.request.assert_called_with("GET", "/health")
    assert connection.close.call_count == 6
