"""Tests for IPFS retrieval: URL builder, CID validation, atomic write,
fallback policy, sentinel fix, and D3 smoke test."""

import os
import tempfile
import textwrap
from pathlib import Path
from unittest import mock
from urllib.parse import quote

import pytest

from dincli.services.cid_utils import validate_cid
from dincli.services.ipfs import (
    DEFAULT_PUBLIC_GATEWAY,
    _build_retrieval_url,
    _should_use_fallback,
)

# ── Constants ──────────────────────────────────────────────────────

VALID_V0 = "QmUNLLsPACCz1vLxQVkXqqLX5R1X345qqfHbsf67hvA3Nn"
VALID_V1 = "bafybeiczsscdsbs7ffqz55asqdf3smv6klcw3gofszvwlyarci47bgf354"
ENCODED_V0 = quote(VALID_V0, safe="")
ENCODED_V1 = quote(VALID_V1, safe="")


# ── URL builder (plan §2.2) ──────────────────────────────────────

@pytest.mark.parametrize(
    "base,expected_url,expected_method",
    [
        # kubo — no trailing slash (the CLI-recommended value)
        (
            "http://localhost:5001/api/v0",
            f"http://localhost:5001/api/v0/cat?arg={ENCODED_V0}",
            "POST",
        ),
        # kubo — trailing slash
        (
            "http://localhost:5001/api/v0/",
            f"http://localhost:5001/api/v0/cat?arg={ENCODED_V0}",
            "POST",
        ),
        # kubo /cat endpoint
        (
            "http://localhost:5001/api/v0/cat",
            f"http://localhost:5001/api/v0/cat?arg={ENCODED_V0}",
            "POST",
        ),
        # kubo /cat/ with trailing slash
        (
            "http://localhost:5001/api/v0/cat/",
            f"http://localhost:5001/api/v0/cat?arg={ENCODED_V0}",
            "POST",
        ),
        # kubo with existing empty arg= — fill it
        (
            "http://localhost:5001/api/v0/cat?arg=",
            f"http://localhost:5001/api/v0/cat?arg={ENCODED_V0}",
            "POST",
        ),
        # kubo with existing populated arg= — replace, don't duplicate
        (
            "http://localhost:5001/api/v0/cat?arg=oldcid",
            f"http://localhost:5001/api/v0/cat?arg={ENCODED_V0}",
            "POST",
        ),
        # gateway /ipfs
        (
            "https://ipfs.io/ipfs",
            f"https://ipfs.io/ipfs/{ENCODED_V0}",
            "GET",
        ),
        # gateway /ipfs/ trailing slash
        (
            "https://ipfs.io/ipfs/",
            f"https://ipfs.io/ipfs/{ENCODED_V0}",
            "GET",
        ),
        # gateway explicit template → GET
        (
            "https://gateway.example/ipfs/{cid}",
            f"https://gateway.example/ipfs/{ENCODED_V0}",
            "GET",
        ),
        # kubo template → POST
        (
            "http://localhost:5001/api/v0/cat?arg={cid}",
            f"http://localhost:5001/api/v0/cat?arg={ENCODED_V0}",
            "POST",
        ),
        # arbitrary host/path → GET
        (
            "https://example.com/data",
            f"https://example.com/data/{ENCODED_V0}",
            "GET",
        ),
    ],
)
def test_build_retrieval_url(base, expected_url, expected_method):
    url, method = _build_retrieval_url(base, VALID_V0)
    assert url == expected_url
    assert method == expected_method


@pytest.mark.parametrize(
    "base,expected_url,expected_method",
    [
        (
            "http://localhost:5001/api/v0",
            f"http://localhost:5001/api/v0/cat?arg={ENCODED_V1}",
            "POST",
        ),
        (
            "http://localhost:5001/api/v0/",
            f"http://localhost:5001/api/v0/cat?arg={ENCODED_V1}",
            "POST",
        ),
    ],
)
def test_build_retrieval_url_v1(base, expected_url, expected_method):
    url, method = _build_retrieval_url(base, VALID_V1)
    assert url == expected_url
    assert method == expected_method


# ── IPFS_PUBLIC_GATEWAY contract (plan §2.1a) ────────────────────


class TestFallbackContract:

    def test_unset(self):
        with mock.patch("dincli.cli.utils.get_env_key",
                        return_value=None):
            enabled, url = _should_use_fallback()
        assert enabled is False
        assert url is None

    @pytest.mark.parametrize("val", ["", "0", "false", "no", "  false  "])
    def test_disabled(self, val):
        with mock.patch("dincli.cli.utils.get_env_key",
                        return_value=val):
            enabled, url = _should_use_fallback()
        assert enabled is False
        assert url is None

    @pytest.mark.parametrize("val", ["1", "true", "yes", "  true  "])
    def test_truthy_uses_builtin(self, val):
        with mock.patch("dincli.cli.utils.get_env_key",
                        return_value=val):
            enabled, url = _should_use_fallback()
        assert enabled is True
        assert url == DEFAULT_PUBLIC_GATEWAY

    def test_explicit_gateway(self):
        with mock.patch(
            "dincli.cli.utils.get_env_key",
            return_value="https://gateway.example/ipfs",
        ):
            enabled, url = _should_use_fallback()
        assert enabled is True
        assert url == "https://gateway.example/ipfs"

    @pytest.mark.parametrize(
        "bad_val,msg_part",
        [
            ("ftp://bad.example", "http or https"),
            ("https://user:pass@host.example/ipfs", "credentials"),
            ("https://host.example/ipfs#frag", "fragment"),
            ("https://", "no host"),
            ("/ipfs", "http or https"),
        ],
    )
    def test_malformed_raises(self, bad_val, msg_part):
        with mock.patch("dincli.cli.utils.get_env_key",
                        return_value=bad_val):
            with pytest.raises(ValueError, match=msg_part):
                _should_use_fallback()

    def test_precedence_retrieve_wins(self):
        """IPFS_API_URL_RETRIEVE always wins over fallback — the URL
        builder test case covers the actual URL, here we check the
        retrieve_from_ipfs flow doesn't enter fallback at all."""
        from dincli.services import ipfs as ipfs_mod

        with mock.patch(
            "dincli.services.ipfs._get_ipfs_urls",
            return_value=(None, "http://localhost:5001/api/v0"),
        ), mock.patch(
            "dincli.services.ipfs._get_config", return_value={}
        ), mock.patch(
            "dincli.services.ipfs._should_use_fallback",
            return_value=(True, DEFAULT_PUBLIC_GATEWAY),
        ) as mock_fb, mock.patch(
            "dincli.services.ipfs.requests.request"
        ) as mock_req:

            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_content.return_value = [b"hello"]
            mock_req.return_value = mock_resp

            ipfs_mod._warned_fallback = False
            ipfs_mod._warned_no_provider = False

            with tempfile.TemporaryDirectory() as td:
                dest = Path(td) / "out.bin"
                ipfs_mod.retrieve_from_ipfs(VALID_V0, str(dest))

            mock_fb.assert_not_called()


# ── CID validation (plan §2.5) ────────────────────────────────────


class TestCIDValidation:

    def test_valid_v0(self):
        assert validate_cid(VALID_V0) == VALID_V0

    def test_valid_v1(self):
        assert validate_cid(VALID_V1) == VALID_V1

    @pytest.mark.parametrize(
        "bad_input",
        [
            "not-a-cid",
            "",
            "QmUNLLsPACCz1vLxQVkXqqLX5R1X345qqfHbsf67hvA3Nn/../../etc/passwd",
            "/etc/passwd",
            "?query=1",
            "#fragment",
            "%20injection",
            " ",
            123,
            None,
        ],
    )
    def test_invalid_rejected(self, bad_input):
        with pytest.raises(ValueError):
            validate_cid(bad_input)


# ── Sentinel fix (plan §2.3) ─────────────────────────────────────


class TestResolveIPFSConfigSentinel:

    def test_returns_none_not_string_none(self):
        """resolve_ipfs_config returns None, not the string 'None'."""
        from dincli.cli.utils import resolve_ipfs_config

        with mock.patch(
            "dincli.cli.utils.get_env_key", return_value=None
        ):
            add, ret = resolve_ipfs_config()
        assert add is None
        assert ret is None

    def test_unconfigured_upload_raises_correct_error(self):
        """An unconfigured upload raises the intended IPFS_API_URL_ADD
        error, not a wrapped MissingSchema."""
        from dincli.services import ipfs as ipfs_mod

        with mock.patch(
            "dincli.services.ipfs._get_ipfs_urls",
            return_value=(None, None),
        ), mock.patch(
            "dincli.services.ipfs._get_config", return_value={}
        ), tempfile.NamedTemporaryFile(suffix=".bin") as tf:
            with pytest.raises(
                ValueError, match="IPFS API URL missing"
            ):
                ipfs_mod.upload_to_ipfs(tf.name)


# ── Behaviour tests (plan §4) ────────────────────────────────────


class TestRetrieveBehaviour:

    @staticmethod
    def _mock_response(status_code=200, chunks=None):
        if chunks is None:
            chunks = [b"hello"]
        resp = mock.MagicMock()
        resp.status_code = status_code
        resp.iter_content.return_value = iter(chunks)
        resp.raise_for_status = mock.MagicMock()
        if status_code >= 400:
            resp.raise_for_status.side_effect = (
                __import__("requests").exceptions.HTTPError()
            )
        return resp

    def test_kubo_url_yields_post(self):
        """A kubo URL yields POST with ?arg=."""
        from dincli.services import ipfs as ipfs_mod

        resp = self._mock_response()
        with mock.patch(
            "dincli.services.ipfs._get_config", return_value={}
        ), mock.patch(
            "dincli.services.ipfs._get_ipfs_urls",
            return_value=(None, "http://localhost:5001/api/v0"),
        ), mock.patch(
            "dincli.services.ipfs.requests.request"
        ) as mock_req, tempfile.TemporaryDirectory() as td:
            mock_req.return_value = resp
            dest = Path(td) / "out.bin"
            ipfs_mod.retrieve_from_ipfs(VALID_V0, str(dest))

        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert "cat" in call_args[0][1]
        assert f"arg={ENCODED_V0}" in call_args[0][1]

    def test_gateway_url_yields_get(self):
        """A gateway URL yields GET."""
        from dincli.services import ipfs as ipfs_mod

        resp = self._mock_response()
        with mock.patch(
            "dincli.services.ipfs._get_config", return_value={}
        ), mock.patch(
            "dincli.services.ipfs._get_ipfs_urls",
            return_value=(None, "https://ipfs.io/ipfs"),
        ), mock.patch(
            "dincli.services.ipfs.requests.request"
        ) as mock_req, tempfile.TemporaryDirectory() as td:
            mock_req.return_value = resp
            dest = Path(td) / "out.bin"
            ipfs_mod.retrieve_from_ipfs(VALID_V0, str(dest))

        call_args = mock_req.call_args
        assert call_args[0][0] == "GET"
        assert f"/ipfs/{ENCODED_V0}" in call_args[0][1]

    def test_filebase_unchanged_protocol(self):
        """Filebase still POSTs to cat?arg=."""
        from dincli.services import ipfs as ipfs_mod

        resp = self._mock_response()
        with mock.patch(
            "dincli.services.ipfs._get_config",
            return_value={
                "ipfs_provider": "filebase",
                "ipfs_api_key": "test-key",
            },
        ), mock.patch(
            "dincli.services.ipfs.requests.post"
        ) as mock_post, tempfile.TemporaryDirectory() as td:
            mock_post.return_value = resp
            dest = Path(td) / "out.bin"
            ipfs_mod.retrieve_from_ipfs(VALID_V0, str(dest))

        assert mock_post.call_count == 1
        call_url = mock_post.call_args[0][0]
        assert "cat" in call_url
        assert f"arg={ENCODED_V0}" in call_url

    def test_nothing_configured_fallback_off_raises(self):
        """Nothing configured + fallback off → actionable error with no
        request attempted."""
        from dincli.services import ipfs as ipfs_mod

        with mock.patch(
            "dincli.services.ipfs._get_config", return_value={}
        ), mock.patch(
            "dincli.services.ipfs._get_ipfs_urls",
            return_value=(None, None),
        ), mock.patch(
            "dincli.services.ipfs._should_use_fallback",
            return_value=(False, None),
        ), mock.patch(
            "dincli.services.ipfs.requests.request"
        ) as mock_req, tempfile.TemporaryDirectory() as td:
            ipfs_mod._warned_fallback = False
            ipfs_mod._warned_no_provider = False

            dest = Path(td) / "out.bin"
            with pytest.raises(ValueError, match="No IPFS retrieval"):
                ipfs_mod.retrieve_from_ipfs(VALID_V0, str(dest))

        mock_req.assert_not_called()

    def test_fallback_on_issues_get_and_warns_once(self):
        """Fallback on → GET request + exactly one warning across
        repeated calls."""
        from dincli.services import ipfs as ipfs_mod

        resp = self._mock_response()
        with mock.patch(
            "dincli.services.ipfs._get_config", return_value={}
        ), mock.patch(
            "dincli.services.ipfs._get_ipfs_urls",
            return_value=(None, None),
        ), mock.patch(
            "dincli.services.ipfs._should_use_fallback",
            return_value=(True, DEFAULT_PUBLIC_GATEWAY),
        ), mock.patch(
            "dincli.services.ipfs.requests.request"
        ) as mock_req, mock.patch(
            "dincli.services.ipfs.logger.warning"
        ) as mock_warn, tempfile.TemporaryDirectory() as td:
            mock_req.return_value = resp
            ipfs_mod._warned_fallback = False

            dest_a = Path(td) / "a.bin"
            ipfs_mod.retrieve_from_ipfs(VALID_V0, str(dest_a))
            assert mock_warn.call_count == 1

            dest_b = Path(td) / "b.bin"
            ipfs_mod.retrieve_from_ipfs(VALID_V1, str(dest_b))
            assert mock_warn.call_count == 1  # no second warning


# ── Atomicity (plan §2.4) ────────────────────────────────────────


class TestAtomicity:

    @staticmethod
    def _mock_response(status_code=200, chunks=None,
                       raise_on_iter=False):
        if chunks is None:
            chunks = [b"hello"]
        resp = mock.MagicMock()
        resp.status_code = status_code
        if raise_on_iter:

            def _iter():
                yield b"part1"
                raise RuntimeError("mid-stream failure")

            resp.iter_content.return_value = _iter()
        else:
            resp.iter_content.return_value = iter(chunks)
        resp.raise_for_status = mock.MagicMock()
        if status_code >= 400:
            resp.raise_for_status.side_effect = (
                __import__("requests").exceptions.HTTPError()
            )
        resp.close = mock.MagicMock()
        return resp

    def test_mocked_multi_chunk_success(self):
        """A multi-chunk download writes the complete file and returns
        the status code."""
        from dincli.services import ipfs as ipfs_mod

        chunks = [b"chunk1", b"chunk2", b"chunk3"]
        resp = self._mock_response(status_code=200, chunks=chunks)

        with mock.patch(
            "dincli.services.ipfs._get_config", return_value={}
        ), mock.patch(
            "dincli.services.ipfs._get_ipfs_urls",
            return_value=(None, DEFAULT_PUBLIC_GATEWAY),
        ), mock.patch(
            "dincli.services.ipfs.requests.request",
            return_value=resp,
        ), tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "out.bin"
            status = ipfs_mod.retrieve_from_ipfs(VALID_V0, str(dest))

            assert dest.exists()
            assert dest.read_bytes() == b"chunk1chunk2chunk3"
            assert status == 200
            resp.close.assert_called_once()

    def test_mid_stream_failure_cleans_up(self):
        """A mid-stream exception leaves no destination file and no
        leftover temp file."""
        from dincli.services import ipfs as ipfs_mod

        resp = self._mock_response(status_code=200, raise_on_iter=True)

        with mock.patch(
            "dincli.services.ipfs._get_config", return_value={}
        ), mock.patch(
            "dincli.services.ipfs._get_ipfs_urls",
            return_value=(None, DEFAULT_PUBLIC_GATEWAY),
        ), mock.patch(
            "dincli.services.ipfs.requests.request",
            return_value=resp,
        ), tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "out.bin"
            with pytest.raises(RuntimeError, match="mid-stream"):
                ipfs_mod.retrieve_from_ipfs(VALID_V0, str(dest))

            # Destination must not exist
            assert not dest.exists()
            # No temp files left behind
            tmps = list(Path(td).glob(".ipfs_*"))
            assert len(tmps) == 0
            resp.close.assert_called_once()

    def test_existing_file_survives_failed_refetch(self):
        """An existing valid file survives a failed re-fetch."""
        from dincli.services import ipfs as ipfs_mod

        resp = self._mock_response(status_code=404)

        with mock.patch(
            "dincli.services.ipfs._get_config", return_value={}
        ), mock.patch(
            "dincli.services.ipfs._get_ipfs_urls",
            return_value=(None, DEFAULT_PUBLIC_GATEWAY),
        ), mock.patch(
            "dincli.services.ipfs.requests.request",
            return_value=resp,
        ), tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "out.bin"
            dest.write_bytes(b"existing data")

            with pytest.raises(
                RuntimeError, match="Failed to retrieve CID"
            ):
                ipfs_mod.retrieve_from_ipfs(VALID_V0, str(dest))

            assert dest.exists()
            assert dest.read_bytes() == b"existing data"
            resp.close.assert_called_once()


# ── D3: the import must name the submodule (plan §2.7) ───────────


def test_imports_importlib_util_not_just_importlib():
    """`import importlib` does not make `importlib.util` accessible.

    util is a submodule; the parent package does not load it. Verified in an
    isolated interpreter: `python -S -I -c "import importlib; importlib.util"`
    raises AttributeError. In a populated environment it appears to work only
    because some dependency imported it first — so a runtime test cannot catch
    the difference here. Assert on the source instead.
    """
    import inspect

    import dincli.services.ipfs as ipfs_module

    source = inspect.getsource(ipfs_module)
    assert "import importlib.util" in source, (
        "ipfs.py must `import importlib.util` explicitly; plain "
        "`import importlib` leaves _load_custom_fn dependent on another "
        "module having imported the submodule first."
    )


# ── D3 smoke test: _load_custom_fn (plan §2.7) ───────────────────


class TestD3Smoke:
    """Smoke test that _load_custom_fn can load a callable from a
    temporary module file."""

    def test_loads_callable_from_module(self):
        from dincli.services.ipfs import _load_custom_fn

        code = textwrap.dedent("""
            def my_retrieve(cid, dest):
                return 200
        """)
        with tempfile.TemporaryDirectory() as td:
            mod_path = Path(td) / "my_service.py"
            mod_path.write_text(code)
            fn = _load_custom_fn(mod_path, "my_retrieve")
            assert fn("anycid", "anydest") == 200