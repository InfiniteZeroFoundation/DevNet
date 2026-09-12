import json
from pathlib import Path

import pytest
from dincli.sdk import config as sdk_config


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestSaveLoadConfig:
    def test_round_trip(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(sdk_config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(sdk_config, "CONFIG_FILE", config_file)

        data = {"ipfs_provider": "filebase", "log_level": "DEBUG"}
        sdk_config.save_config(data)

        loaded = sdk_config.load_config()
        assert loaded == data

    def test_load_config_missing_file(self, monkeypatch, tmp_path):
        config_file = tmp_path / "nonexistent" / "config.json"
        monkeypatch.setattr(sdk_config, "CONFIG_DIR", config_file.parent)
        monkeypatch.setattr(sdk_config, "CONFIG_FILE", config_file)

        loaded = sdk_config.load_config()
        assert loaded == {}

    def test_load_config_invalid_json(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json", encoding="utf-8")
        monkeypatch.setattr(sdk_config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(sdk_config, "CONFIG_FILE", config_file)

        loaded = sdk_config.load_config()
        assert loaded == {}

    def test_get_config_existing_key(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        _write_json(config_file, {"log_level": "DEBUG"})
        monkeypatch.setattr(sdk_config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(sdk_config, "CONFIG_FILE", config_file)

        assert sdk_config.get_config("log_level") == "DEBUG"

    def test_get_config_missing_key_default(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        _write_json(config_file, {})
        monkeypatch.setattr(sdk_config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(sdk_config, "CONFIG_FILE", config_file)

        assert sdk_config.get_config("nonexistent", default=42) == 42


class TestResolveNetworkValue:
    def test_env_wins_over_config(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(sdk_config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(sdk_config, "CONFIG_FILE", config_file)
        monkeypatch.chdir(tmp_path)

        _write_json(config_file, {"networks": {"local": {"rpc_url": "http://config.local:8545"}}})
        (tmp_path / ".env").write_text("LOCAL_RPC_URL=http://env.local:8545\n", encoding="utf-8")

        result = sdk_config.resolve_network_value("local", "rpc_url")
        assert result == "http://env.local:8545"

    def test_config_used_when_env_missing(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(sdk_config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(sdk_config, "CONFIG_FILE", config_file)
        monkeypatch.chdir(tmp_path)

        _write_json(config_file, {"networks": {"local": {"rpc_url": "http://config.local:8545"}}})
        (tmp_path / ".env").write_text("", encoding="utf-8")

        result = sdk_config.resolve_network_value("local", "rpc_url")
        assert result == "http://config.local:8545"

    def test_default_falls_back(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(sdk_config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(sdk_config, "CONFIG_FILE", config_file)
        monkeypatch.chdir(tmp_path)

        _write_json(config_file, {})
        (tmp_path / ".env").write_text("", encoding="utf-8")

        result = sdk_config.resolve_network_value("local", "rpc_url", default="http://default:8545")
        assert result == "http://default:8545"

    def test_raises_key_error_when_nothing_found(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(sdk_config, "CONFIG_DIR", tmp_path)
        monkeypatch.setattr(sdk_config, "CONFIG_FILE", config_file)
        monkeypatch.chdir(tmp_path)

        _write_json(config_file, {})
        (tmp_path / ".env").write_text("", encoding="utf-8")

        with pytest.raises(KeyError, match="Could not resolve"):
            sdk_config.resolve_network_value("local", "nonexistent_key")


class TestNormalizeIpfsProvider:
    def test_none_returns_env(self):
        assert sdk_config.normalize_ipfs_provider(None) == "env"

    def test_empty_string_alias_to_env(self):
        assert sdk_config.normalize_ipfs_provider("") == "env"

    def test_default_alias_to_env(self):
        assert sdk_config.normalize_ipfs_provider("default") == "env"

    def test_ipfs_node_alias_to_env(self):
        assert sdk_config.normalize_ipfs_provider("ipfs node") == "env"
        assert sdk_config.normalize_ipfs_provider("ipfs-node") == "env"
        assert sdk_config.normalize_ipfs_provider("node") == "env"

    def test_env_passes_through(self):
        assert sdk_config.normalize_ipfs_provider("env") == "env"

    def test_filebase_passes_through(self):
        assert sdk_config.normalize_ipfs_provider("filebase") == "filebase"

    def test_custom_passes_through(self):
        assert sdk_config.normalize_ipfs_provider("custom") == "custom"

    def test_unknown_provider_passes_through(self):
        assert sdk_config.normalize_ipfs_provider("some-unknown-provider") == "some-unknown-provider"
