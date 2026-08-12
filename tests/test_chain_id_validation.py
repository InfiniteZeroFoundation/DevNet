"""
Tests for RPC chain-id validation (PR 5).

§4.3 mocked unit tests — no network required.
"""
import io
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from dincli.cli.utils import ChainIdMismatchError, get_w3, load_din_info

SENTINEL = "sk_live_deadbeef1234secret"

VALID_CHAIN_ID = 11155420
WRONG_CHAIN_ID = 10

NETWORK = "sepolia_op_devnet"
UNPINNED = "mainnet"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_web3_mock(*, connected=True, chain_id=VALID_CHAIN_ID, chain_id_raises=None):
    """Build a mock Web3; attaches a PropertyMock for eth.chain_id so we can assert access."""
    w3 = MagicMock(name="Web3")
    w3.is_connected.return_value = connected
    if chain_id_raises is not None:
        prop = PropertyMock(side_effect=chain_id_raises)
    else:
        prop = PropertyMock(return_value=chain_id)
    type(w3.eth).chain_id = prop
    # Stash the PropertyMock for call assertions
    w3._chain_id_prop = prop
    return w3


# ---------------------------------------------------------------------------
# Direct get_w3() tests
# ---------------------------------------------------------------------------

class TestGetW3Direct:
    """Call get_w3() directly with mocked dependencies."""

    @patch("dincli.cli.utils.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.cli.utils.load_din_info")
    @patch("dincli.cli.utils.Web3")
    def test_match_returns_web3(self, mock_web3_cls, mock_load_info, mock_resolve):
        """Case: Match — returns the Web3 object."""
        mock_web3 = _make_web3_mock(chain_id=VALID_CHAIN_ID)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        result = get_w3(NETWORK)

        assert result is mock_web3
        assert str(result.eth.chain_id) == str(VALID_CHAIN_ID)

    @patch("dincli.cli.utils.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.cli.utils.load_din_info")
    @patch("dincli.cli.utils.Web3")
    def test_mismatch_raises_chain_error(self, mock_web3_cls, mock_load_info, mock_resolve):
        """Case: Mismatch — raises ChainIdMismatchError; message contains both ids and network name."""
        mock_web3 = _make_web3_mock(chain_id=WRONG_CHAIN_ID)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(ChainIdMismatchError) as exc_info:
            get_w3(NETWORK)

        msg = str(exc_info.value)
        assert str(WRONG_CHAIN_ID) in msg
        assert str(VALID_CHAIN_ID) in msg
        assert NETWORK in msg

    @patch("dincli.cli.utils.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.cli.utils.load_din_info")
    @patch("dincli.cli.utils.Web3")
    def test_unpinned_network_skips_chain_check(self, mock_web3_cls, mock_load_info, mock_resolve):
        """Case: Unpinned network — returns Web3; eth_chainId is never called."""
        mock_web3 = _make_web3_mock(chain_id=VALID_CHAIN_ID)
        mock_web3_cls.return_value = mock_web3
        # mainnet has no chain_id in din_info → expected is None → skip
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        result = get_w3(UNPINNED)

        assert result is mock_web3
        # eth_chainId must NOT have been accessed
        mock_web3._chain_id_prop.assert_not_called()

    @patch("dincli.cli.utils.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.cli.utils.load_din_info")
    @patch("dincli.cli.utils.Web3")
    def test_connection_failure_raises_connection_error(self, mock_web3_cls, mock_load_info, mock_resolve):
        """Case: is_connected() == False — raises ConnectionError, not a chain error."""
        mock_web3 = _make_web3_mock(connected=False)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(ConnectionError) as exc_info:
            get_w3(NETWORK)

        msg = str(exc_info.value)
        assert NETWORK in msg
        # Must NOT be a chain error
        assert not isinstance(exc_info.value, ChainIdMismatchError)
        # Must NOT contain the sentinel URL
        assert SENTINEL not in msg

    @patch("dincli.cli.utils.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.cli.utils.load_din_info")
    @patch("dincli.cli.utils.Web3")
    def test_chain_id_read_failure_raises_connection_error(self, mock_web3_cls, mock_load_info, mock_resolve):
        """Case: eth_chainId itself raises — stage-2 ConnectionError, not a mismatch."""
        mock_web3 = _make_web3_mock(
            chain_id_raises=Exception("RPC timeout"),
        )
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(ConnectionError) as exc_info:
            get_w3(NETWORK)

        msg = str(exc_info.value)
        assert "could not read its chain id" in msg.lower()
        assert not isinstance(exc_info.value, ChainIdMismatchError)
        # Stage 1 succeeded (connected), stage 2 failed
        assert "Connected to the RPC" in msg

    @patch("dincli.cli.utils.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.cli.utils.load_din_info")
    @patch("dincli.cli.utils.Web3")
    def test_load_din_info_raises_is_not_mismatch(self, mock_web3_cls, mock_load_info, mock_resolve):
        """Case: load_din_info raises — not mislabeled as a mismatch."""
        mock_web3 = _make_web3_mock(chain_id=VALID_CHAIN_ID)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.side_effect = FileNotFoundError("din_info.json missing")

        with pytest.raises(FileNotFoundError):
            get_w3(NETWORK)

        # Not caught — propagates as the original error, not a chain error

    @patch("dincli.cli.utils.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.cli.utils.load_din_info")
    @patch("dincli.cli.utils.Web3")
    def test_credential_not_leaked_in_error_messages(self, mock_web3_cls, mock_load_info, mock_resolve):
        """Case: Credential safety — sentinel never appears in exception messages."""
        # Test 1: Connection failure
        mock_web3 = _make_web3_mock(connected=False)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(ConnectionError) as exc_info:
            get_w3(NETWORK)
        assert SENTINEL not in str(exc_info.value)
        assert SENTINEL not in repr(exc_info.value)

        # Test 2: Mismatch
        mock_load_info.side_effect = None
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}
        mock_web3_2 = _make_web3_mock(chain_id=WRONG_CHAIN_ID)
        mock_web3_cls.return_value = mock_web3_2

        with pytest.raises(ChainIdMismatchError) as exc_info:
            get_w3(NETWORK)
        assert SENTINEL not in str(exc_info.value)

        # Test 3: Chain-id read failure
        mock_web3_3 = _make_web3_mock(chain_id_raises=Exception("boom"))
        mock_web3_cls.return_value = mock_web3_3

        with pytest.raises(ConnectionError) as exc_info:
            get_w3(NETWORK)
        assert SENTINEL not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Config value tests
# ---------------------------------------------------------------------------

class TestConfigValues:
    """Assert din_info.json has the correct chain_id values."""

    def test_local_chain_id_is_1337(self):
        info = load_din_info()
        assert info["local"]["chain_id"] == 1337

    def test_sepolia_op_devnet_chain_id_is_11155420(self):
        info = load_din_info()
        assert info["sepolia_op_devnet"]["chain_id"] == 11155420


# ---------------------------------------------------------------------------
# CLI boundary test — ChainIdMismatchError → exit 1, red stderr, no traceback
# ---------------------------------------------------------------------------

class TestCLIBoundary:
    """ChainIdMismatchError through GlobalOptionsGroup.invoke() → exit 1,
    one red stderr line, no traceback."""

    def test_connection_error_also_rendered_cleanly(self):
        """ConnectionError must render as one line too, not a traceback.

        Stage 2 ("connected but could not read chain id") is a new failure mode
        introduced by this change, and stage 1 connection errors reach the same
        boundary. Neither should reach the user as a stack trace, since
        pretty_exceptions_enable=False leaves anything uncaught here raw.
        """
        from dincli.cli.core import GlobalOptionsGroup

        group = GlobalOptionsGroup(name="test")
        ctx = MagicMock()

        error_msg = (
            f"Connected to the RPC for network '{NETWORK}', "
            "but could not read its chain id"
        )

        with patch("typer.core.TyperGroup.invoke", side_effect=ConnectionError(error_msg)):
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            try:
                with pytest.raises(SystemExit) as exc_info:
                    group.invoke(ctx)
            finally:
                captured = sys.stderr.getvalue()
                sys.stderr = old_stderr

        assert exc_info.value.code == 1
        assert NETWORK in captured
        assert "Traceback" not in captured
        assert "File " not in captured
        assert SENTINEL not in captured

    def test_invoke_prints_red_and_exits(self):
        """Simulate invoke() catching ChainIdMismatchError."""
        from dincli.cli.core import GlobalOptionsGroup

        group = GlobalOptionsGroup(name="test")
        ctx = MagicMock()

        error_msg = (
            f"RPC chain mismatch for network '{NETWORK}': "
            f"the endpoint reports chain id {WRONG_CHAIN_ID}, expected {VALID_CHAIN_ID}. "
            "Check SEPOLIA_OP_DEVNET_RPC_URL in your .env — it points at a different chain."
        )

        with patch.object(
            GlobalOptionsGroup, "invoke",
            wraps=group.invoke,
        ) as invoke_method:
            # Make super().invoke() raise the chain error
            with patch("typer.core.TyperGroup.invoke", side_effect=ChainIdMismatchError(error_msg)):
                old_stderr = sys.stderr
                sys.stderr = io.StringIO()
                try:
                    with pytest.raises(SystemExit) as exc_info:
                        invoke_method(ctx)
                finally:
                    captured = sys.stderr.getvalue()
                    sys.stderr = old_stderr

        assert exc_info.value.code == 1

        # Must contain the network and chain ids
        assert NETWORK in captured
        assert str(WRONG_CHAIN_ID) in captured
        assert str(VALID_CHAIN_ID) in captured

        # Must NOT be a traceback
        assert "Traceback" not in captured
        assert "File " not in captured

        # Must NOT leak the sentinel
        assert SENTINEL not in captured