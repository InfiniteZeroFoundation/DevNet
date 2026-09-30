import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import typer

from dincli.sdk import manifest as sdk_manifest
from dincli.sdk.errors import ValidationError


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestGetManifestPath:
    def test_model_id_path(self):
        path = sdk_manifest.get_manifest_path("local", model_id=42)
        assert "model_42" in str(path)
        assert path.name == "manifest.json"

    def test_task_coordinator_address_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_manifest.os, "getcwd", lambda: str(tmp_path))
        addr = "0x1234567890123456789012345678901234567890"
        path = sdk_manifest.get_manifest_path("local", task_coordinator_address=addr)
        expected = tmp_path / "tasks" / "local" / addr / "manifest.json"
        assert path == expected

    def test_neither_raises_value_error(self):
        with pytest.raises(ValueError, match="Either model_id or task_coordinator_address must be provided"):
            sdk_manifest.get_manifest_path("local")

    def test_both_raises_value_error(self):
        with pytest.raises(ValueError, match="Only one of model_id or task_coordinator_address can be provided"):
            sdk_manifest.get_manifest_path(
                "local", model_id=1, task_coordinator_address="0x1234567890123456789012345678901234567890"
            )

    def test_none_model_id_and_coordinator_address_raises(self):
        with pytest.raises(ValueError, match="Either model_id or task_coordinator_address must be provided"):
            sdk_manifest.get_manifest_path("local", model_id=None, task_coordinator_address=None)


class TestIsEthereumAddress:
    def test_valid_address(self):
        assert sdk_manifest.is_ethereum_address("0x" + "a" * 40)

    def test_invalid_too_short(self):
        assert not sdk_manifest.is_ethereum_address("0x123")

    def test_invalid_no_0x(self):
        assert not sdk_manifest.is_ethereum_address("a" * 42)

    def test_invalid_non_hex(self):
        assert not sdk_manifest.is_ethereum_address("0x" + "g" * 40)


class TestDinInfoIO:
    def test_load_save_din_info_round_trip(self, monkeypatch, tmp_path):
        info_path = tmp_path / "din_info.json"
        monkeypatch.setattr(sdk_manifest, "DIN_INFO_PATH", info_path)

        data = {"local": {"registry": "0x1234", "explorer": "https://explorer.local"}}
        sdk_manifest.save_din_info(data)

        loaded = sdk_manifest.load_din_info()
        assert loaded == data

    def test_load_cid_services(self, monkeypatch, tmp_path):
        cid_path = tmp_path / "cid_services.json"
        monkeypatch.setattr(sdk_manifest, "CID_SERVICES_PATH", cid_path)
        write_json(cid_path, {"services": {"model.py": "bafyCID1"}})

        loaded = sdk_manifest.load_cid_services()
        assert loaded == {"services": {"model.py": "bafyCID1"}}


class TestDownloadManifest:
    def test_negative_model_id_raises_validation_error(self):
        with pytest.raises(ValidationError, match="Model ID must be non-negative"):
            sdk_manifest.download_manifest("local", -1)

    def test_skip_when_exists_and_not_force(self, monkeypatch, tmp_path):
        model_dir = tmp_path / "local" / "model_5"
        manifest_file = model_dir / "manifest.json"
        monkeypatch.setattr(sdk_manifest, "CACHE_DIR", tmp_path)
        write_json(manifest_file, {"type": "custom"})

        load_called = False

        def fake_load():
            nonlocal load_called
            load_called = True
            return {"local": {"registry": "0x0"}}

        monkeypatch.setattr(sdk_manifest, "load_din_info", fake_load)

        sdk_manifest.download_manifest("local", 5)
        assert not load_called

    def test_force_always_fetches(self, monkeypatch, tmp_path):
        model_dir = tmp_path / "local" / "model_5"
        manifest_file = model_dir / "manifest.json"
        cid_file = model_dir / "manifest.json.cid"
        monkeypatch.setattr(sdk_manifest, "CACHE_DIR", tmp_path)
        write_json(manifest_file, {"type": "custom"})

        monkeypatch.setattr(
            sdk_manifest,
            "load_din_info",
            lambda: {"local": {"registry": "0xRegistry"}},
        )

        mock_contract = MagicMock()
        mock_contract.functions.getModel(5).call.return_value = [
            "0xOwner",
            True,
            b"\x00" * 32,
            0,
            "0xTaskCoordinator",
            "0xTaskAuditor",
        ]

        def fake_get_contract_instance(artifact, network, address):
            return mock_contract

        monkeypatch.setattr(sdk_manifest, "get_contract_instance", fake_get_contract_instance)

        retrieve_cid = []

        def fake_retrieve(cid, path):
            retrieve_cid.append(cid)

        monkeypatch.setattr(sdk_manifest, "retrieve_from_ipfs", fake_retrieve)

        sdk_manifest.download_manifest("local", 5, force=True)

        assert retrieve_cid

    def test_fetch_when_manifest_does_not_exist(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_manifest, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(
            sdk_manifest,
            "load_din_info",
            lambda: {"local": {"registry": "0xRegistry"}},
        )

        mock_contract = MagicMock()
        mock_contract.functions.getModel(5).call.return_value = [
            "0xOwner", True, b"\x00" * 32, 0, "0xTC", "0xTA",
        ]

        retrieve_cid = []

        def fake_get_contract_instance(artifact, network, address):
            return mock_contract

        def fake_retrieve(cid, path):
            retrieve_cid.append(cid)

        monkeypatch.setattr(sdk_manifest, "get_contract_instance", fake_get_contract_instance)
        monkeypatch.setattr(sdk_manifest, "retrieve_from_ipfs", fake_retrieve)

        sdk_manifest.download_manifest("local", 5)

        assert retrieve_cid


class TestGetModelInfo:
    def test_returns_model_data_as_dict(self, monkeypatch):
        monkeypatch.setattr(
            sdk_manifest,
            "load_din_info",
            lambda: {"local": {"registry": "0xRegistry"}},
        )

        mock_contract = MagicMock()
        mock_contract.functions.getModel(5).call.return_value = [
            "0xOwner",
            True,
            b"\x12\x20" + b"\x00" * 30,
            1234567890,
            "0xTaskCoordinator",
            "0xTaskAuditor",
        ]

        monkeypatch.setattr(sdk_manifest, "get_contract_instance", lambda *a, **kw: mock_contract)

        result = sdk_manifest.get_model_info("local", 5)
        assert result["model_owner"] == "0xOwner"
        assert result["is_open_source"] is True
        assert "manifest_cid" in result
        assert result["created_at"] == 1234567890
        assert result["task_coordinator_address"] == "0xTaskCoordinator"
        assert result["task_auditor_address"] == "0xTaskAuditor"
        assert "genesis_model_ipfs_hash" not in result

    def test_include_genesis_queries_task_coordinator(self, monkeypatch):
        monkeypatch.setattr(
            sdk_manifest,
            "load_din_info",
            lambda: {"local": {"registry": "0xRegistry"}},
        )

        registry_contract = MagicMock()
        registry_contract.functions.getModel(5).call.return_value = [
            "0xOwner", True, b"\x12\x20" + b"\x00" * 30, 0, "0xTC", "0xTA",
        ]

        task_coordinator_contract = MagicMock()
        task_coordinator_contract.functions.genesisModelIpfsHash().call.return_value = b"\x12\x20" + b"\x00" * 30

        contract_calls = []

        def fake_get_contract_instance(artifact, network, address=None):
            contract_calls.append(address)
            if "DINTaskCoordinator" in str(artifact):
                return task_coordinator_contract
            return registry_contract

        monkeypatch.setattr(sdk_manifest, "get_contract_instance", fake_get_contract_instance)

        result = sdk_manifest.get_model_info("local", 5, include_genesis=True)
        assert "genesis_model_ipfs_hash" in result


class TestCacheManifestCLIWrapper:
    def test_negative_model_id_raises_typer_exit(self, monkeypatch):
        from dincli.cli.utils import cache_manifest

        called_download = False

        def fake_download(network, model_id, force=False):
            nonlocal called_download
            called_download = True
            raise ValidationError("Model ID must be non-negative")

        monkeypatch.setattr("dincli.cli.utils.download_manifest", fake_download)

        with pytest.raises(typer.Exit):
            cache_manifest(-1, "local")

        assert called_download

    def test_info_flag_calls_get_model_info_and_prints(self, monkeypatch):
        from dincli.cli.utils import cache_manifest

        download_calls = []

        def fake_download(network, model_id, force=False):
            download_calls.append(model_id)

        monkeypatch.setattr("dincli.cli.utils.download_manifest", fake_download)

        get_model_info_calls = []

        def fake_get_model_info(network, model_id, include_genesis=False):
            get_model_info_calls.append((model_id, include_genesis))
            return {
                "model_owner": "0xOwner",
                "is_open_source": True,
                "manifest_cid": "bafyCID",
                "created_at": 1234567890,
                "task_coordinator_address": "0xTC",
                "task_auditor_address": "0xTA",
                "genesis_model_ipfs_hash": "genesisCID",
            }

        monkeypatch.setattr("dincli.cli.utils.get_model_info", fake_get_model_info)

        cache_manifest(5, "local", info=True, genesis_model_info=True)

        assert download_calls == [5]
        assert get_model_info_calls == [(5, True)]


class TestGetManifestFreshness:
    def test_fresh_manifest_skips_update(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_manifest, "CACHE_DIR", tmp_path)

        model_dir = tmp_path / "local" / "model_5"
        manifest_file = model_dir / "manifest.json"
        cid_file = model_dir / "manifest.json.cid"
        model_dir.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text('{"type": "custom"}', encoding="utf-8")
        cid_file.write_text("bafyFresh", encoding="utf-8")

        monkeypatch.setattr(
            sdk_manifest,
            "load_din_info",
            lambda: {"local": {"registry": "0xRegistry"}},
        )

        mock_contract = MagicMock()
        mock_contract.functions.getModel(5).call.return_value = [
            "0xOwner", True, b"\x00" * 32, 0, "0xTC", "0xTA",
        ]

        monkeypatch.setattr(sdk_manifest, "get_contract_instance", lambda *a, **kw: mock_contract)

        monkeypatch.setattr(sdk_manifest, "get_cid_from_bytes32", lambda hex_str: "bafyFresh")

        download_calls = []

        def fake_download(network, model_id, force=False):
            download_calls.append(1)

        monkeypatch.setattr(sdk_manifest, "download_manifest", fake_download)

        result = sdk_manifest.get_manifest("local", model_id=5)
        assert result == {"type": "custom"}
        assert download_calls == []

    def test_stale_manifest_triggers_download(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_manifest, "CACHE_DIR", tmp_path)

        model_dir = tmp_path / "local" / "model_5"
        manifest_file = model_dir / "manifest.json"
        cid_file = model_dir / "manifest.json.cid"
        model_dir.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text('{"type": "custom"}', encoding="utf-8")
        cid_file.write_text("bafyStale", encoding="utf-8")

        monkeypatch.setattr(
            sdk_manifest,
            "load_din_info",
            lambda: {"local": {"registry": "0xRegistry"}},
        )

        mock_contract = MagicMock()
        mock_contract.functions.getModel(5).call.return_value = [
            "0xOwner", True, b"\x00" * 32, 0, "0xTC", "0xTA",
        ]

        monkeypatch.setattr(sdk_manifest, "get_contract_instance", lambda *a, **kw: mock_contract)

        monkeypatch.setattr(sdk_manifest, "get_cid_from_bytes32", lambda hex_str: "bafyFresh")

        download_calls = []

        def fake_download(network, model_id, force=False):
            download_calls.append(1)

        monkeypatch.setattr(sdk_manifest, "download_manifest", fake_download)

        sdk_manifest.get_manifest("local", model_id=5)
        assert download_calls == [1]

    def test_missing_manifest_for_coordinator_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_manifest.os, "getcwd", lambda: str(tmp_path))
        addr = "0x1234567890123456789012345678901234567890"

        with pytest.raises(FileNotFoundError, match="Manifest not found"):
            sdk_manifest.get_manifest("local", task_coordinator_address=addr)
