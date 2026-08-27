"""SDK layer contract tests (issue #20).

- Import-boundary: ``dincli.sdk`` (and every submodule) must import without
  pulling in ``typer``, ``rich``, or any ``dincli.cli.*`` module. Run in a fresh
  subprocess so an earlier test that imported those doesn't mask a violation.
- Error taxonomy + allowlist detail sanitization (proposal §4/§4a).
"""
import subprocess
import sys
import textwrap

from dincli.sdk import errors
from dincli.sdk.errors import DinError, TransactionError, TX_REVERTED, sanitize_details


def test_sdk_imports_no_cli_or_ui():
    """import dincli.sdk.* pulls in no typer / rich / dincli.cli — enforces the
    'CLI depends on SDK, never the reverse' rule. Fresh subprocess required."""
    script = textwrap.dedent(
        """
        import importlib, pkgutil, sys
        import dincli.sdk
        for m in pkgutil.walk_packages(dincli.sdk.__path__, dincli.sdk.__name__ + "."):
            importlib.import_module(m.name)
        loaded = set(sys.modules)
        bad_ui = {"typer", "rich"} & loaded
        bad_cli = sorted(m for m in loaded if m == "dincli.cli" or m.startswith("dincli.cli."))
        assert not bad_ui, f"SDK pulled in UI libs: {sorted(bad_ui)}"
        assert not bad_cli, f"SDK imported dincli.cli modules: {bad_cli}"
        assert {"dincli.sdk.state", "dincli.sdk.serialize",
                "dincli.sdk.wallet", "dincli.sdk.session", "dincli.sdk.tx"} <= loaded, \
            f"Missing SDK modules: {loaded}"
        print("ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_error_carries_stable_code_and_message():
    err = DinError("boom")
    assert err.code == "din_error"
    assert err.message == "boom"
    assert err.to_error() == {"code": "din_error", "message": "boom", "details": {}}


def test_subcode_override():
    err = TransactionError("reverted", code=TX_REVERTED, details={"tx_hash": "abc", "nonce": 7})
    assert err.code == "tx_reverted"
    assert err.details["tx_hash"] == "0xabc"  # hex-normalized
    assert err.details["nonce"] == 7


def test_sanitize_drops_secrets_and_unlisted_keys():
    dirty = {
        "tx_hash": "0xdead",
        "password": "hunter2",        # never allowed
        "private_key": "0xbeef",      # never allowed
        "unexpected": "whatever",     # not in allowlist for this code
        "nonce": "12",                # coerced to int
    }
    clean = sanitize_details(TX_REVERTED, dirty)
    assert clean == {"tx_hash": "0xdead", "nonce": 12}


def test_sanitize_strips_url_credentials():
    """Userinfo, query string AND path are all dropped — only scheme://host[:port]
    survives. Path-style API keys (the two largest RPC providers) mean the path
    can carry a secret just as easily as userinfo or a query string."""
    clean = sanitize_details(
        errors.RPC_UNREACHABLE,
        {"endpoint_host": "https://user:key@rpc.example.com:8545/v1?token=abc"},
    )
    assert clean["endpoint_host"] == "https://rpc.example.com:8545"


def test_sanitize_host_strips_query_string_key():
    clean = sanitize_details(
        errors.RPC_UNREACHABLE,
        {"endpoint_host": "https://rpc.example.com/rpc?apikey=SECRET_KEY"},
    )
    assert clean["endpoint_host"] == "https://rpc.example.com"
    assert "SECRET_KEY" not in clean["endpoint_host"]


def test_sanitize_host_strips_path_key_infura_shape():
    clean = sanitize_details(
        errors.RPC_UNREACHABLE,
        {"endpoint_host": "https://mainnet.infura.io/v3/SECRET_KEY"},
    )
    assert clean["endpoint_host"] == "https://mainnet.infura.io"
    assert "SECRET_KEY" not in clean["endpoint_host"]


def test_sanitize_host_strips_path_key_alchemy_shape():
    clean = sanitize_details(
        errors.RPC_UNREACHABLE,
        {"endpoint_host": "https://eth.alchemy.com/v2/SECRET_KEY"},
    )
    assert clean["endpoint_host"] == "https://eth.alchemy.com"
    assert "SECRET_KEY" not in clean["endpoint_host"]


def test_sanitize_host_strips_fragment():
    clean = sanitize_details(
        errors.RPC_UNREACHABLE,
        {"endpoint_host": "https://rpc.example.com/rpc#SECRET_FRAGMENT"},
    )
    assert clean["endpoint_host"] == "https://rpc.example.com"
    assert "SECRET_FRAGMENT" not in clean["endpoint_host"]


def test_sanitize_host_unparsable_input_returns_placeholder_not_raw_value():
    clean = sanitize_details(
        errors.RPC_UNREACHABLE,
        {"endpoint_host": "not a url at all SECRET_TOKEN"},
    )
    assert clean["endpoint_host"] == "<unparsable-endpoint>"
    assert "SECRET_TOKEN" not in clean["endpoint_host"]


def test_unknown_code_yields_empty_details():
    assert sanitize_details("no_such_code", {"anything": "x"}) == {}
