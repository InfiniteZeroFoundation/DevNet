"""Retrieval-path tests for dincli.services.ipfs.

Covers the four defects fixed alongside this file:

1. the env/gateway path issued POST for every endpoint, which no public
   gateway accepts;
2. `_build_retrieve_url` applied kubo's `cat?arg=` form to gateway bases;
3. a missing IPFS_API_URL_RETRIEVE raised outright, leaving a fresh install
   unable to read public content even with a gateway available;
4. downloads were written straight to the destination, so a mid-stream
   failure left a truncated file that callers treat as a cache hit.

Filebase is asserted to be unchanged: its POST to `cat?arg=` is the correct
kubo-RPC call and was never part of the bug.
"""

import json
from pathlib import Path

import pytest
import requests

from dincli.cli import utils
from dincli.services import ipfs

# A real CIDv1 — retrieval validates the CID before it reaches a URL.
CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"


def _write_config(config_file: Path, data: dict):
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(data), encoding="utf-8")


class _FakeResponse:
    """Minimal stand-in for a streamed requests.Response."""

    def __init__(self, chunks=(b"payload",), status_code=200, text=""):
        self._chunks = list(chunks)
        self.status_code = status_code
        self.text = text
        self.closed = False

    def iter_content(self, chunk_size=8192):
        for chunk in self._chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def close(self):
        self.closed = True


@pytest.fixture
def env_provider(monkeypatch, tmp_path):
    """Config + cwd wired for the 'env' provider, with no .env by default."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(utils, "CONFIG_FILE", config_file)
    monkeypatch.chdir(tmp_path)
    _write_config(config_file, {"ipfs_provider": "ipfs node"})

    # Module-level "warn once" flags leak across tests otherwise.
    monkeypatch.setattr(ipfs, "_warned_fallback", False)
    monkeypatch.setattr(ipfs, "_warned_no_provider", False)
    for key in ("IPFS_API_URL_RETRIEVE", "IPFS_PUBLIC_GATEWAY"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def _capture_requests(monkeypatch, response=None):
    """Patch requests.request and return the list it records calls into."""
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return response if response is not None else _FakeResponse()

    monkeypatch.setattr(ipfs.requests, "request", fake_request)
    return calls


# ── URL / method selection ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "base,expected_url,expected_method",
    [
        # kubo RPC — POST, cat?arg=
        (
            "http://127.0.0.1:5001/api/v0",
            f"http://127.0.0.1:5001/api/v0/cat?arg={CID}",
            "POST",
        ),
        (
            "http://127.0.0.1:5001/api/v0/cat",
            f"http://127.0.0.1:5001/api/v0/cat?arg={CID}",
            "POST",
        ),
        (
            "http://127.0.0.1:5001/api/v0/",
            f"http://127.0.0.1:5001/api/v0/cat?arg={CID}",
            "POST",
        ),
        # path-style gateway — GET, <base>/<cid>
        ("https://ipfs.io/ipfs", f"https://ipfs.io/ipfs/{CID}", "GET"),
        ("https://ipfs.io/ipfs/", f"https://ipfs.io/ipfs/{CID}", "GET"),
        ("https://dweb.link/ipfs", f"https://dweb.link/ipfs/{CID}", "GET"),
        # explicit {cid} template — method follows the resulting path
        ("https://ipfs.io/ipfs/{cid}", f"https://ipfs.io/ipfs/{CID}", "GET"),
        (
            "http://127.0.0.1:5001/api/v0/cat?arg={cid}",
            f"http://127.0.0.1:5001/api/v0/cat?arg={CID}",
            "POST",
        ),
    ],
)
def test_build_retrieve_url_picks_form_and_method(base, expected_url, expected_method):
    url, method = ipfs._build_retrieve_url(base, CID)
    assert (url, method) == (expected_url, expected_method)


def test_build_retrieve_url_preserves_existing_query_on_gateway():
    url, method = ipfs._build_retrieve_url("https://gw.example/ipfs?token=abc", CID)
    assert url == f"https://gw.example/ipfs/{CID}?token=abc"
    assert method == "GET"


def test_build_retrieve_url_escapes_cid_fully():
    """A slash must not survive into the URL as a path separator."""
    url, _ = ipfs._build_retrieve_url("https://ipfs.io/ipfs", "a/b")
    assert url == "https://ipfs.io/ipfs/a%2Fb"


# ── env provider dispatch ───────────────────────────────────────────────


def test_env_gateway_url_uses_get(env_provider, monkeypatch):
    (env_provider / ".env").write_text(
        "IPFS_API_URL_RETRIEVE=https://ipfs.io/ipfs\n", encoding="utf-8"
    )
    calls = _capture_requests(monkeypatch)

    status = ipfs.retrieve_from_ipfs(CID, env_provider / "out.bin")

    assert status == 200
    assert calls[0][0] == "GET"
    assert calls[0][1] == f"https://ipfs.io/ipfs/{CID}"
    assert (env_provider / "out.bin").read_bytes() == b"payload"


def test_env_kubo_url_still_uses_post(env_provider, monkeypatch):
    """The documented default endpoint must keep working unchanged."""
    (env_provider / ".env").write_text(
        "IPFS_API_URL_RETRIEVE=http://127.0.0.1:5001/api/v0\n", encoding="utf-8"
    )
    calls = _capture_requests(monkeypatch)

    ipfs.retrieve_from_ipfs(CID, env_provider / "out.bin")

    assert calls[0][0] == "POST"
    assert calls[0][1] == f"http://127.0.0.1:5001/api/v0/cat?arg={CID}"


def test_missing_endpoint_without_fallback_raises_actionable_message(
    env_provider, monkeypatch
):
    calls = _capture_requests(monkeypatch)

    with pytest.raises(ValueError) as excinfo:
        ipfs.retrieve_from_ipfs(CID, env_provider / "out.bin")

    # Names the three real options rather than blaming the CID.
    message = str(excinfo.value)
    assert "filebase" in message
    assert "IPFS_API_URL_RETRIEVE" in message
    assert "IPFS_PUBLIC_GATEWAY" in message
    assert calls == []


def test_missing_endpoint_with_fallback_reads_via_gateway(env_provider, monkeypatch):
    (env_provider / ".env").write_text("IPFS_PUBLIC_GATEWAY=1\n", encoding="utf-8")
    calls = _capture_requests(monkeypatch)

    status = ipfs.retrieve_from_ipfs(CID, env_provider / "out.bin")

    assert status == 200
    assert calls[0][0] == "GET"
    assert calls[0][1] == f"{ipfs.DEFAULT_PUBLIC_GATEWAY}/{CID}"


def test_configured_endpoint_wins_over_fallback(env_provider, monkeypatch):
    (env_provider / ".env").write_text(
        "IPFS_API_URL_RETRIEVE=http://127.0.0.1:5001/api/v0\n"
        "IPFS_PUBLIC_GATEWAY=1\n",
        encoding="utf-8",
    )
    calls = _capture_requests(monkeypatch)

    ipfs.retrieve_from_ipfs(CID, env_provider / "out.bin")

    assert calls[0][1].startswith("http://127.0.0.1:5001")


def test_filebase_protocol_unchanged(monkeypatch, tmp_path):
    """Filebase's POST to cat?arg= was correct and must not be touched."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(utils, "CONFIG_FILE", config_file)
    monkeypatch.chdir(tmp_path)
    _write_config(config_file, {"ipfs_provider": "filebase", "ipfs_api_key": "k"})

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse()

    monkeypatch.setattr(ipfs.requests, "post", fake_post)

    ipfs.retrieve_from_ipfs(CID, tmp_path / "out.bin")

    assert calls[0][0] == f"{utils.FILEBASE_IPFS_CAT_URL}?arg={CID}"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer k"


# ── IPFS_PUBLIC_GATEWAY parsing ─────────────────────────────────────────


@pytest.mark.parametrize("value", ["", "0", "false", "no", "FALSE"])
def test_fallback_disabled_values(env_provider, monkeypatch, value):
    monkeypatch.setenv("IPFS_PUBLIC_GATEWAY", value)
    assert ipfs._should_use_fallback() == (False, None)


@pytest.mark.parametrize("value", ["1", "true", "yes", "YES"])
def test_fallback_enabled_values_use_default_gateway(env_provider, monkeypatch, value):
    monkeypatch.setenv("IPFS_PUBLIC_GATEWAY", value)
    assert ipfs._should_use_fallback() == (True, ipfs.DEFAULT_PUBLIC_GATEWAY)


def test_fallback_unset_is_opt_in(env_provider):
    assert ipfs._should_use_fallback() == (False, None)


def test_fallback_custom_url_accepted(env_provider, monkeypatch):
    monkeypatch.setenv("IPFS_PUBLIC_GATEWAY", "https://dweb.link/ipfs")
    assert ipfs._should_use_fallback() == (True, "https://dweb.link/ipfs")


@pytest.mark.parametrize(
    "value,reason",
    [
        ("ftp://example.com/ipfs", "http or https"),
        ("https://user:pw@example.com/ipfs", "credentials"),
        ("https://example.com/ipfs#frag", "fragment"),
        ("https://", "no host"),
    ],
)
def test_fallback_rejects_unsafe_urls(env_provider, monkeypatch, value, reason):
    monkeypatch.setenv("IPFS_PUBLIC_GATEWAY", value)
    with pytest.raises(ValueError) as excinfo:
        ipfs._should_use_fallback()
    assert reason in str(excinfo.value)


# ── atomic write ────────────────────────────────────────────────────────


def test_partial_download_leaves_no_destination_file(env_provider, monkeypatch):
    """A mid-stream failure must not leave a truncated file behind."""
    (env_provider / ".env").write_text(
        "IPFS_API_URL_RETRIEVE=https://ipfs.io/ipfs\n", encoding="utf-8"
    )
    broken = _FakeResponse(chunks=[b"half", requests.ConnectionError("dropped")])
    _capture_requests(monkeypatch, response=broken)
    destination = env_provider / "out.bin"

    with pytest.raises(RuntimeError):
        ipfs.retrieve_from_ipfs(CID, destination)

    assert not destination.exists()
    assert list(env_provider.glob(".ipfs_*")) == []


def test_failed_download_does_not_clobber_existing_file(env_provider, monkeypatch):
    (env_provider / ".env").write_text(
        "IPFS_API_URL_RETRIEVE=https://ipfs.io/ipfs\n", encoding="utf-8"
    )
    destination = env_provider / "out.bin"
    destination.write_bytes(b"previous good content")

    broken = _FakeResponse(chunks=[b"half", requests.ConnectionError("dropped")])
    _capture_requests(monkeypatch, response=broken)

    with pytest.raises(RuntimeError):
        ipfs.retrieve_from_ipfs(CID, destination)

    assert destination.read_bytes() == b"previous good content"


def test_successful_download_is_complete_and_cleans_up(env_provider, monkeypatch):
    (env_provider / ".env").write_text(
        "IPFS_API_URL_RETRIEVE=https://ipfs.io/ipfs\n", encoding="utf-8"
    )
    _capture_requests(monkeypatch, response=_FakeResponse(chunks=[b"one", b"two"]))
    destination = env_provider / "nested" / "out.bin"

    ipfs.retrieve_from_ipfs(CID, destination)

    assert destination.read_bytes() == b"onetwo"
    assert list(destination.parent.glob(".ipfs_*")) == []


def test_response_is_closed(env_provider, monkeypatch):
    (env_provider / ".env").write_text(
        "IPFS_API_URL_RETRIEVE=https://ipfs.io/ipfs\n", encoding="utf-8"
    )
    response = _FakeResponse()
    _capture_requests(monkeypatch, response=response)

    ipfs.retrieve_from_ipfs(CID, env_provider / "out.bin")

    assert response.closed


# ── CID validation ──────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["", "not-a-cid", "../../etc/passwd", "abc123"])
def test_invalid_cid_rejected_before_any_request(env_provider, monkeypatch, bad):
    (env_provider / ".env").write_text(
        "IPFS_API_URL_RETRIEVE=https://ipfs.io/ipfs\n", encoding="utf-8"
    )
    calls = _capture_requests(monkeypatch)

    with pytest.raises(Exception):
        ipfs.retrieve_from_ipfs(bad, env_provider / "out.bin")

    assert calls == []
