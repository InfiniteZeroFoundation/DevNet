"""`model-owner model add-default-test-data --default-test-data` takes its CID
from din_info's `default_test_dataset` when set, else the published default."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from dincli.cli.modelownerd import model


class _Console:
    def print(self, *a, **k):
        pass


@pytest.fixture
def fetched(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(model, "resolve_task_coordinator_address", lambda net, addr, console: "0xC")
    monkeypatch.setattr(model, "retrieve_from_ipfs", lambda cid, path: calls.append((cid, Path(path))))
    return calls


def _ctx(tmp_path):
    return SimpleNamespace(obj=SimpleNamespace(
        get_en_w3_account_console=lambda: ("local", None, None, _Console()),
        get_model_base_dir=lambda model_id: tmp_path / f"model_{model_id}",
    ))


def test_uses_din_info_override(monkeypatch, tmp_path, fetched):
    monkeypatch.setattr(model, "load_din_info", lambda: {"local": {"default_test_dataset": "bafyOverride"}})
    model.add_default_test_data(_ctx(tmp_path), task_coordinator_address=None, model_id=0, default_test_data=True)
    assert fetched == [("bafyOverride", tmp_path / "model_0" / "dataset" / "test" / "test_dataset.pt")]


def test_falls_back_to_published_default(monkeypatch, tmp_path, fetched):
    monkeypatch.setattr(model, "load_din_info", lambda: {"local": {}})
    model.add_default_test_data(_ctx(tmp_path), task_coordinator_address=None, model_id=0, default_test_data=True)
    assert fetched[0][0] == model.DEFAULT_TEST_DATASET_CID
