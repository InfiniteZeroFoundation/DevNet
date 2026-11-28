import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from dincli.dind import cohort_monitor as monitor


def log(topic, address, block, index, amount):
    return SimpleNamespace(topics=[topic], address=address, blockNumber=block, logIndex=index,
                           transactionHash=block.to_bytes(32, "big"), data=amount.to_bytes(32, "big"))


def test_finalized_polls_spike_edges_and_delivery_retry(tmp_path, monkeypatch):
    args = SimpleNamespace(chain_id=7, batch_blocks=2, token="token", stake="stake",
                           mint_wei=100, window_blocks=2, slash_count=2)
    mint = log(monitor.MINT, "token", 1, 0, 100)
    logs = [mint, mint, log(monitor.MINT, "token", 1, 1, 99),
            log(monitor.MINT, "stake", 1, 2, 200)]
    logs += [log(monitor.SLASH, "stake", b, 3, 10) for b in (1, 2, 3, 6, 7)]
    logs.append(logs[-1])
    eth = Mock()
    eth.get_block.return_value.number = 7
    eth.get_logs.side_effect = lambda q: [
        row for row in reversed(logs) if q["fromBlock"] <= row.blockNumber <= q["toBlock"]]
    path = tmp_path / "alerts.db"
    db = sqlite3.connect(path)
    monitor.initialize(db, {}, 1)
    for _ in range(5):
        monitor.scan(db, eth, args)
    assert eth.get_logs.call_count == 4
    eth.get_block.assert_called_with("finalized")

    detector = Mock()
    detector.models = {"addr": SimpleNamespace(observed_since=datetime.now(timezone.utc))}
    monkeypatch.setattr(monitor, "poll", lambda *_: [
        {"event": kind, "gi": 5, "state": "GIstarted", "coordinator": "addr"}
        for kind in ("stalled", "recovered")])
    for _ in range(2):
        monitor.route_gi(db, detector, 8787, 7)

    post = Mock(side_effect=[requests.Timeout(), SimpleNamespace(status_code=503)])
    for error in (requests.Timeout, ValueError):
        with pytest.raises(error):
            monitor.deliver(db, "https://fake.invalid", post)
    first_key = post.call_args.kwargs["headers"]["Idempotency-Key"]
    db.close()
    db = sqlite3.connect(path)
    monitor.initialize(db, {}, 1)
    monitor.scan(db, eth, args)
    post = Mock(return_value=SimpleNamespace(status_code=204))
    monitor.deliver(db, "https://fake.invalid", post)
    monitor.deliver(db, "https://fake.invalid", post)
    sent = [call.kwargs["json"] for call in post.call_args_list]
    assert sent[0]["id"] == first_key
    assert [e["event"] for e in sent] == ["large_mint", "slashing_spike", "slashing_spike",
                                           "stalled", "recovered"]
    assert [e["block"] for e in sent[1:3]] == [2, 7]
    assert all(c.args == ("https://fake.invalid",) for c in post.call_args_list)
