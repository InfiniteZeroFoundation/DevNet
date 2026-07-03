import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest
import requests

from dincli.services.ipfs_lighthouse import (
    LIGHTHOUSE_GATEWAY_URL,
    LIGHTHOUSE_UPLOAD_URL,
    upload_via_lighthouse,
    retrieve_via_lighthouse,
)


@dataclass(frozen=True)
class FakeIPFSConfig:
    provider: str = "lighthouse"
    api_key: Optional[str] = None
    api_url_add: Optional[str] = None
    api_url_retrieve: Optional[str] = None
    api_secret: Optional[str] = None
    service_path: Optional[Path] = None


class DummyResponse:
    status_code = 200
    text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": {"Name": "test.bin", "Hash": "QmTest123", "Size": "42"}}

    def iter_content(self, chunk_size=8192):
        yield b"lighthouse-content"


class DummyErrorResponse:
    status_code = 403
    text = "Forbidden"

    def raise_for_status(self):
        raise requests.HTTPError("403 Forbidden", response=self)


class DummyMalformedResponse:
    status_code = 200
    text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return {"unexpected": "shape"}


def test_upload_extracts_nested_hash(monkeypatch, tmp_path):
    config = FakeIPFSConfig(api_key="test-key")
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"payload")

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return DummyResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    cid = upload_via_lighthouse(config, payload)

    assert cid == "QmTest123"
    assert len(calls) == 1
    assert calls[0][0] == LIGHTHOUSE_UPLOAD_URL
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-key"


def test_upload_malformed_response_raises_runtime_error(monkeypatch, tmp_path):
    config = FakeIPFSConfig(api_key="test-key")
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"payload")

    def fake_post(url, **kwargs):
        return DummyMalformedResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(RuntimeError, match="unexpected response shape"):
        upload_via_lighthouse(config, payload)


def test_upload_missing_api_key_raises_value_error_before_http(tmp_path):
    config = FakeIPFSConfig(api_key=None)
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"payload")

    with pytest.raises(ValueError, match="requires an API key"):
        upload_via_lighthouse(config, payload)


def test_upload_http_error_wraps(monkeypatch, tmp_path):
    config = FakeIPFSConfig(api_key="test-key")
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"payload")

    def fake_post(url, **kwargs):
        return DummyErrorResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(RuntimeError, match="Lighthouse upload failed.*403"):
        upload_via_lighthouse(config, payload)


def test_retrieve_uses_gateway_url(monkeypatch, tmp_path):
    config = FakeIPFSConfig(api_key="test-key")

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return DummyResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    response = retrieve_via_lighthouse(config, "QmTest123")

    assert response is not None
    assert len(calls) == 1
    assert calls[0][0] == f"{LIGHTHOUSE_GATEWAY_URL}/QmTest123"
    assert "headers" not in calls[0][1] or "Authorization" not in (calls[0][1].get("headers") or {})


def test_retrieve_http_error_wraps(monkeypatch):
    config = FakeIPFSConfig(api_key="test-key")

    def fake_get(url, **kwargs):
        return DummyErrorResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="Lighthouse download failed.*403"):
        retrieve_via_lighthouse(config, "QmTest123")
