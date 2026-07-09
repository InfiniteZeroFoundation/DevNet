import json
from pathlib import Path

from dincli.cli import utils
from dincli.services import ipfs


def _write_config(config_file: Path, data: dict):
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(data), encoding="utf-8")


def test_resolve_ipfs_config_defaults_to_env_provider(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(utils, "CONFIG_FILE", config_file)
    monkeypatch.chdir(tmp_path)

    _write_config(config_file, {"ipfs_provider": "ipfs node"})
    (tmp_path / ".env").write_text(
        "IPFS_API_URL_ADD=http://127.0.0.1:5001/api/v0\n"
        "IPFS_API_URL_RETRIEVE=http://127.0.0.1:5001/api/v0\n",
        encoding="utf-8",
    )

    resolved = utils.resolve_ipfs_config()

    assert resolved.provider == "env"
    assert resolved.api_url_add == "http://127.0.0.1:5001/api/v0"
    assert resolved.api_url_retrieve == "http://127.0.0.1:5001/api/v0"


def test_upload_to_ipfs_uses_env_provider_by_default(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"payload")

    monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(utils, "CONFIG_FILE", config_file)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ipfs, "get_cidv1base32_from_cid", lambda cid: f"normalized-{cid}")

    _write_config(config_file, {})
    (tmp_path / ".env").write_text(
        "IPFS_API_URL_ADD=http://127.0.0.1:5001/api/v0\n",
        encoding="utf-8",
    )

    calls = []

    class DummyResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"Hash": "cid123"}

    def fake_post(url, **kwargs):
        calls.append(url)
        return DummyResponse()

    monkeypatch.setattr(ipfs.requests, "post", fake_post)

    cid = ipfs.upload_to_ipfs(payload)

    assert cid == "normalized-cid123"
    assert calls == ["http://127.0.0.1:5001/api/v0/add"]


def test_custom_provider_delegates_upload_and_retrieve(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    custom_service = tmp_path / "custom_ipfs.py"
    payload = tmp_path / "payload.bin"
    output = tmp_path / "downloaded.bin"

    payload.write_bytes(b"payload")
    custom_service.write_text(
        "from pathlib import Path\n"
        "\n"
        "def upload_to_ipfs(file_path, msg=None):\n"
        "    return 'custom-cid'\n"
        "\n"
        "def retrieve_from_ipfs(cid, file_path):\n"
        "    Path(file_path).write_text(f'retrieved:{cid}', encoding='utf-8')\n"
        "    return 204\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(utils, "CONFIG_FILE", config_file)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ipfs, "get_cidv1base32_from_cid", lambda cid: f"normalized-{cid}")

    _write_config(
        config_file,
        {
            "ipfs_provider": "custom",
            "ipfs_service_path": str(custom_service),
        },
    )

    cid = ipfs.upload_to_ipfs(payload)
    status = ipfs.retrieve_from_ipfs("abc123", output)

    assert cid == "normalized-custom-cid"
    assert status == 204
    assert output.read_text(encoding="utf-8") == "retrieved:abc123"
