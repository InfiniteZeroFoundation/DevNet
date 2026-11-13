from types import SimpleNamespace

import pytest
import typer
from nacl.public import PrivateKey

from dincli.cli import aggregator, auditor, dintoken
from dincli.cli.modelownerd import auditor_batches, disputes
from tests._cli_fakes import FakeContract, FakeCtxObj, record_txs

ZERO = "0x0000000000000000000000000000000000000000"
ZERO32 = b"\x00" * 32
CHALLENGER = "0x000000000000000000000000000000000000C4a1"
BOND = 100 * 10**18


@pytest.fixture
def sent(monkeypatch):
    return record_txs(monkeypatch, auditor, aggregator, disputes, dintoken)


# ── Test-data disputes ──────────────────────────────────────────────────────

def make_testdata_ctx(tmp_path, *, is_batch_auditor=True, settled=False, commitment=b"\x11" * 32,
                      dispute=(ZERO, 0, 0, False, False), block_number=100):
    task_auditor = FakeContract(
        "0xA0",
        isBatchAuditor=is_batch_auditor,
        giRewardSnapshot=(0, 0, 0, 0, settled),
        testDataCommitments=commitment,
        testDataDisputes=dispute,
        disputeBondAmount=BOND,
    )
    coordinator = FakeContract("0xC0", GI=2, GIstate=0)
    return SimpleNamespace(obj=FakeCtxObj(coordinator=coordinator, auditor=task_auditor,
                                          token=FakeContract("0xD1"), model_base_dir=tmp_path,
                                          block_number=block_number))


def test_dispute_test_data_approves_the_bond_then_opens(tmp_path, sent):
    auditor.dispute_test_data(make_testdata_ctx(tmp_path), model_id=0, gi=None, batch_id=1)

    assert sent == [("approve", ("0xA0", BOND)), ("openTestDataDispute", (2, 1))]


@pytest.mark.parametrize("kwargs", [
    {"is_batch_auditor": False},
    {"settled": True},
    {"commitment": ZERO32},
    {"dispute": (CHALLENGER, BOND, 200, True, False)},
    {"dispute": (CHALLENGER, BOND, 200, False, True)},
])
def test_dispute_test_data_fails_fast_without_approving(tmp_path, sent, kwargs):
    with pytest.raises(typer.Exit):
        auditor.dispute_test_data(make_testdata_ctx(tmp_path, **kwargs), model_id=0, gi=None, batch_id=1)

    assert sent == []


K_ONCHAIN, PLAINTEXT = b"\x22" * 32, b"\x33" * 32
COMMITMENT = auditor_batches._testdata_commitment(2, 1, K_ONCHAIN, PLAINTEXT)
OPEN_DISPUTE = (CHALLENGER, BOND, 200, True, False)


def test_resolve_test_data_reveals_the_saved_k(tmp_path, sent):
    auditor_batches._save_testdata_secret(tmp_path, 2, 1, K_ONCHAIN, PLAINTEXT)
    ctx = make_testdata_ctx(tmp_path, commitment=COMMITMENT, dispute=OPEN_DISPUTE)

    disputes.resolve_test_data(ctx, model_id=0, gi=2, batch_id=1)

    assert sent == [("resolveTestDataDispute", (2, 1, K_ONCHAIN, PLAINTEXT))]


def test_resolve_test_data_refuses_a_k_that_does_not_match_the_commitment(tmp_path, sent):
    # A replaced K would reveal a mismatch and uphold the dispute against the
    # owner; refuse before sending (task_061026_21 close-out, Discussion 231).
    auditor_batches._save_testdata_secret(tmp_path, 2, 1, b"\x44" * 32, PLAINTEXT)
    ctx = make_testdata_ctx(tmp_path, commitment=COMMITMENT, dispute=OPEN_DISPUTE)

    with pytest.raises(typer.Exit):
        disputes.resolve_test_data(ctx, model_id=0, gi=2, batch_id=1)

    assert sent == []
    assert "matches its on-chain commitment" in ctx.obj.console.text()


def test_resolve_test_data_prefers_the_matching_k_over_a_pending_one(tmp_path, sent):
    # A failed retry leaves an uncommitted K pending next to the confirmed one.
    auditor_batches._save_testdata_secret(tmp_path, 2, 1, K_ONCHAIN, PLAINTEXT)
    auditor_batches._stage_testdata_secret(tmp_path, 2, 1, b"\x55" * 32, PLAINTEXT)
    ctx = make_testdata_ctx(tmp_path, commitment=COMMITMENT, dispute=OPEN_DISPUTE)

    disputes.resolve_test_data(ctx, model_id=0, gi=2, batch_id=1)

    assert sent == [("resolveTestDataDispute", (2, 1, K_ONCHAIN, PLAINTEXT))]


def test_resolve_test_data_recovers_a_landed_but_unconfirmed_k(tmp_path, sent):
    # The assign tx landed but the process died before confirming: only the
    # pending file matches. It is used and promoted to confirmed.
    auditor_batches._save_testdata_secret(tmp_path, 2, 1, b"\x44" * 32, PLAINTEXT)
    auditor_batches._stage_testdata_secret(tmp_path, 2, 1, K_ONCHAIN, PLAINTEXT)
    ctx = make_testdata_ctx(tmp_path, commitment=COMMITMENT, dispute=OPEN_DISPUTE)

    disputes.resolve_test_data(ctx, model_id=0, gi=2, batch_id=1)

    assert sent == [("resolveTestDataDispute", (2, 1, K_ONCHAIN, PLAINTEXT))]
    assert not auditor_batches._pending_testdata_secret_path(tmp_path, 2, 1).exists()
    assert auditor_batches._load_testdata_secret(tmp_path, 2, 1, COMMITMENT) == (K_ONCHAIN, PLAINTEXT)


def test_resolve_test_data_without_a_saved_k_sends_nothing(tmp_path, sent):
    ctx = make_testdata_ctx(tmp_path, dispute=(CHALLENGER, BOND, 200, True, False))

    with pytest.raises(typer.Exit):
        disputes.resolve_test_data(ctx, model_id=0, gi=2, batch_id=1)

    assert sent == []


def test_resolve_test_data_after_the_window_points_to_close_expired(tmp_path, sent):
    auditor_batches._save_testdata_secret(tmp_path, 2, 1, K_ONCHAIN, PLAINTEXT)
    ctx = make_testdata_ctx(tmp_path, commitment=COMMITMENT, dispute=(CHALLENGER, BOND, 50, True, False), block_number=100)

    with pytest.raises(typer.Exit):
        disputes.resolve_test_data(ctx, model_id=0, gi=2, batch_id=1)

    assert sent == []
    assert "close-expired" in ctx.obj.console.text()


def test_close_expired_waits_for_the_window(tmp_path, sent):
    open_ctx = make_testdata_ctx(tmp_path, dispute=(CHALLENGER, BOND, 200, True, False), block_number=100)
    with pytest.raises(typer.Exit):
        disputes.close_expired(open_ctx, model_id=0, gi=2, batch_id=1)
    assert sent == []

    expired_ctx = make_testdata_ctx(tmp_path, dispute=(CHALLENGER, BOND, 50, True, False), block_number=100)
    disputes.close_expired(expired_ctx, model_id=0, gi=2, batch_id=1)
    assert sent == [("closeExpiredDispute", (2, 1))]


# ── Aggregation disputes ────────────────────────────────────────────────────

def _dispute(challenger=CHALLENGER, deadline=0, seed_block=90, resolved=False, upheld=False,
             finalized=False, seed=ZERO32):
    return (challenger, BOND, 0, deadline, seed_block, resolved, upheld, finalized, seed)


def make_agg_ctx(dispute, din_token="0xD1", block_number=100):
    coordinator = FakeContract("0xC0", GI=2, GIstate=0, disputes=dispute, dinToken=din_token, disputeBond=BOND)
    return SimpleNamespace(obj=FakeCtxObj(coordinator=coordinator, token=FakeContract("0xD1"),
                                          block_number=block_number))


def test_aggregator_dispute_approves_the_bond_then_opens(sent):
    aggregator.dispute(make_agg_ctx(_dispute(challenger=ZERO)), model_id=0, gi=None, tier="t2", batch_id=0)

    assert sent == [("approve", ("0xC0", BOND)), ("openDispute", (2, 1, 0))]


def test_aggregator_dispute_refuses_a_disputed_batch(sent):
    with pytest.raises(typer.Exit):
        aggregator.dispute(make_agg_ctx(_dispute()), model_id=0, gi=None, tier="t1", batch_id=0)

    assert sent == []


def test_aggregator_dispute_refuses_without_a_din_token(sent):
    with pytest.raises(typer.Exit):
        aggregator.dispute(make_agg_ctx(_dispute(challenger=ZERO), din_token=ZERO), model_id=0, gi=None, tier="t1", batch_id=0)

    assert sent == []


def test_aggregator_dispute_rejects_an_unknown_tier():
    with pytest.raises(typer.BadParameter):
        aggregator.dispute(make_agg_ctx(_dispute(challenger=ZERO)), model_id=0, gi=None, tier="t3", batch_id=0)


def test_resolve_aggregation_upheld_locks_the_seed_first(sent):
    ctx = make_agg_ctx(_dispute())
    # The seed reads as locked once lockDisputeSeed has been sent.
    ctx.obj.coordinator.views["disputes"] = lambda *a: _dispute(
        seed=b"\x01" * 32 if any(fn.name == "lockDisputeSeed" for fn in sent) else ZERO32
    )

    disputes.resolve_aggregation(ctx, model_id=0, gi=2, tier="t1", batch_id=0, upheld=True)

    assert sent == [("lockDisputeSeed", (2, 0, 0)), ("resolveDispute", (2, 0, 0, True))]


def test_resolve_aggregation_rejected_needs_no_seed(sent):
    disputes.resolve_aggregation(make_agg_ctx(_dispute()), model_id=0, gi=2, tier="t1", batch_id=0, upheld=False)

    assert sent == [("resolveDispute", (2, 0, 0, False))]


def test_settle_recomputation_requires_an_upheld_unfinalized_dispute(sent):
    with pytest.raises(typer.Exit):
        disputes.settle_recomputation(make_agg_ctx(_dispute(resolved=True)), model_id=0, gi=2, tier="t1", batch_id=0, confirmed=True)
    assert sent == []

    disputes.settle_recomputation(make_agg_ctx(_dispute(resolved=True, upheld=True)), model_id=0, gi=2, tier="t1", batch_id=0, confirmed=True)
    assert sent == [("settleRecomputation", (2, 0, 0, True))]


def test_expire_waits_for_the_resolution_deadline(sent):
    ctx = make_agg_ctx(_dispute(resolved=True, upheld=True, deadline=1_000))
    ctx.obj.w3.eth.get_block = lambda _: {"timestamp": 1_000}
    with pytest.raises(typer.Exit):
        disputes.expire(ctx, model_id=0, gi=2, tier="t1", batch_id=0)
    assert sent == []

    ctx.obj.w3.eth.get_block = lambda _: {"timestamp": 1_001}
    disputes.expire(ctx, model_id=0, gi=2, tier="t1", batch_id=0)
    assert sent == [("expireDispute", (2, 0, 0))]


def test_claim_dispute_bond(sent):
    ctx = make_agg_ctx(_dispute())
    ctx.obj.coordinator.views["disputeBondClaimable"] = 0
    with pytest.raises(typer.Exit):
        aggregator.claim_dispute_bond(ctx, model_id=0)
    assert sent == []

    ctx.obj.coordinator.views["disputeBondClaimable"] = BOND
    aggregator.claim_dispute_bond(ctx, model_id=0)
    assert sent == [("claimDisputeBond", ())]


# ── reassign-test-data keeps the confirmed K until the tx lands ─────────────

AUDITOR_KEY = bytes(PrivateKey.generate().public_key)


class _ReassignCtxObj(FakeCtxObj):
    def ensure_file_exists(self, *a, **kw):
        return None

    def load_custom_fn(self, *a, **kw):
        new_k = self.new_k

        def create_audit_testDataCIDs(batch_count, gi, base, test_data_path):
            return [{"raw_cid": f"cid-{i}", "K": new_k, "plaintext_keccak": PLAINTEXT} for i in range(batch_count)]

        return create_audit_testDataCIDs


def _reassign(monkeypatch, tmp_path, *, lands):
    monkeypatch.setattr(auditor_batches, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(auditor_batches, "get_bytes32_from_cid", lambda cid: "11" * 32)
    monkeypatch.setattr(disputes, "get_manifest_key", lambda *a, **kw: {"type": "custom", "path": "svc.py", "ipfs": "cid"})
    monkeypatch.setattr(disputes, "require_custom_manifest_service", lambda *a, **kw: None)
    monkeypatch.setattr(disputes, "resolve_manifest_path", lambda base, path, **kw: base / path)
    sent = []

    def fake_send(ctx, fn, *a, **kw):
        sent.append(fn)
        return SimpleNamespace(status=1) if lands else None

    monkeypatch.setattr(disputes, "build_and_send_tx", fake_send)
    (tmp_path / "dataset" / "test").mkdir(parents=True)
    (tmp_path / "dataset" / "test" / "test_dataset.pt").write_bytes(b"x")

    task_auditor = FakeContract("0xA0", testDataDisputes=(CHALLENGER, BOND, 0, False, True),
                                getAuditorsBatch=(1, ["0xAud"], [], b""), AuditorsBatchCount=2)
    ctx_obj = _ReassignCtxObj(coordinator=FakeContract("0xC0", GI=2, GIstate=0), auditor=task_auditor,
                              stake=FakeContract("0x5A", getEncryptionKey=AUDITOR_KEY), model_base_dir=tmp_path)
    ctx_obj.account.sign_message = lambda msg: SimpleNamespace(signature=b"\x01" * 65)
    ctx_obj.new_k = b"\x66" * 32
    ctx = SimpleNamespace(obj=ctx_obj)
    if lands:
        disputes.reassign_test_data(ctx, model_id=0, gi=None, batch_id=1, test_data_path=None)
    else:
        with pytest.raises(typer.Exit):
            disputes.reassign_test_data(ctx, model_id=0, gi=None, batch_id=1, test_data_path=None)
    return sent


def test_failed_reassign_keeps_the_confirmed_k(monkeypatch, tmp_path):
    auditor_batches._save_testdata_secret(tmp_path, 2, 1, K_ONCHAIN, PLAINTEXT)

    sent = _reassign(monkeypatch, tmp_path, lands=False)

    assert [fn.name for fn in sent] == ["reassignAuditTestDataset"]
    assert auditor_batches._load_testdata_secret(tmp_path, 2, 1, COMMITMENT) == (K_ONCHAIN, PLAINTEXT)


def test_landed_reassign_confirms_the_new_k(monkeypatch, tmp_path):
    auditor_batches._save_testdata_secret(tmp_path, 2, 1, K_ONCHAIN, PLAINTEXT)

    sent = _reassign(monkeypatch, tmp_path, lands=True)

    new_commitment = sent[0].args[4]
    assert new_commitment == auditor_batches._testdata_commitment(2, 1, b"\x66" * 32, PLAINTEXT)
    assert not auditor_batches._pending_testdata_secret_path(tmp_path, 2, 1).exists()
    assert auditor_batches._load_testdata_secret(tmp_path, 2, 1, new_commitment) == (b"\x66" * 32, PLAINTEXT)
