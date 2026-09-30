"""Tests for dind/jobs.py — JobContext, handler registry, and read_stake."""

from dincli.dind import jobs as jobs_mod
from dincli.dind.jobs import Job, JobContext, JOB_HANDLERS
from dincli.dind.state import StateStore
from dincli.sdk.operations.platform import StakeInfo
from dincli.sdk.session import DinSession


def test_job_context_holds_state_and_session(tmp_path):
    store = StateStore(tmp_path / "test.db")
    session = DinSession()
    ctx = JobContext(state=store, session=session)

    assert ctx.state is store
    assert ctx.session is session
    store.close()


def test_demo_handler_accepts_ctx(tmp_path):
    store = StateStore(tmp_path / "test.db")
    ctx = JobContext(state=store, session=DinSession())
    job = Job(type="demo", id=1)

    assert JOB_HANDLERS["demo"](job, ctx) is None
    store.close()


def test_read_stake_handler_registered():
    assert "read_stake" in JOB_HANDLERS
    assert JOB_HANDLERS["read_stake"] is jobs_mod.read_stake_handler


def test_read_stake_handler_returns_envelope_with_explicit_address(tmp_path, monkeypatch):
    address = "0x" + "ab" * 20
    stake = StakeInfo(
        network="local",
        address=address,
        stake_wei=42,
        stake_contract="0x" + "cd" * 20,
    )

    captured = {}

    def fake_get_stake(session, address=None):
        captured["session"] = session
        captured["address"] = address
        return stake

    monkeypatch.setattr(jobs_mod, "get_stake", fake_get_stake)

    class FakeSession:
        network = "local"

    store = StateStore(tmp_path / "test.db")
    ctx = JobContext(state=store, session=FakeSession())
    job = Job(type="read_stake", payload={"address": address}, id=1)

    envelope = jobs_mod.read_stake_handler(job, ctx)

    assert captured["address"] == address
    assert captured["session"] is ctx.session
    assert envelope["status"] == "ok"
    assert envelope["data"]["stake_wei"] == "42"
    assert envelope["meta"]["network"] == "local"
    store.close()


def test_read_stake_handler_no_address_passes_none(tmp_path, monkeypatch):
    """No 'address' key in payload -> get_stake(session, address=None), the
    fall-back-to-signer path (§3.3)."""
    captured = {}

    def fake_get_stake(session, address=None):
        captured["address"] = address
        return StakeInfo(network="local", address="0x" + "ab" * 20,
                          stake_wei=0, stake_contract="0x" + "cd" * 20)

    monkeypatch.setattr(jobs_mod, "get_stake", fake_get_stake)

    class FakeSession:
        network = "local"

    store = StateStore(tmp_path / "test.db")
    ctx = JobContext(state=store, session=FakeSession())
    job = Job(type="read_stake", payload={}, id=1)

    jobs_mod.read_stake_handler(job, ctx)

    assert captured["address"] is None
    store.close()
