from web3 import Web3

from dincli.sdk.config import resolve_network_value
from dincli.sdk.errors import ChainIdMismatchError, NetworkError, RPC_UNREACHABLE
from dincli.sdk.log import logger
from dincli.sdk.manifest import load_din_info


def get_w3(effective_network):
    # Stage 0 — resolve. Deliberately outside stage 1's handler: an unresolvable
    # rpc_url is a configuration error, and resolve_network_value already raises
    # an actionable KeyError naming the env var and config path it checked.
    # Wrapping it would report a missing endpoint as an unreachable one, which is
    # the exact class of misleading error this function exists to remove. Its
    # message carries no URL value, so letting it propagate leaks nothing.
    rpc_url = resolve_network_value(effective_network, "rpc_url")

    # Stage 1 — connect. Message names the network, never the URL: RPC URLs
    # routinely embed API keys. A single `except Exception` re-raise, always
    # `from None`, keeps the provider's own exception text (which may contain
    # the URL) out of any traceback — regardless of whether the failure was a
    # raised-and-caught "did not respond" or an exception from the transport
    # itself, both end up going through this one boundary uniformly.
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise ConnectionError("endpoint did not respond")
    except Exception as e:
        logger.debug("connect failed for network '%s': %s", effective_network, type(e).__name__)
        raise NetworkError(
            f"Could not connect to the configured Ethereum node for network '{effective_network}'",
            code=RPC_UNREACHABLE,
            details={"endpoint_host": rpc_url},
        ) from None

    expected = load_din_info().get(effective_network, {}).get("chain_id")
    if expected is None:
        return w3

    # Stage 2 — read the chain id.
    try:
        actual = w3.eth.chain_id
    except Exception as e:
        logger.debug("chain id read failed for network '%s': %s", effective_network, type(e).__name__)
        raise NetworkError(
            f"Connected to the RPC for network '{effective_network}', but could not read its chain id",
            code=RPC_UNREACHABLE,
            details={"endpoint_host": rpc_url},
        ) from None

    # Stage 3 — compare, outside both boundaries above.
    if actual != expected:
        raise ChainIdMismatchError(
            f"RPC chain mismatch for network '{effective_network}': "
            f"the endpoint reports chain id {actual}, expected {expected}. "
            f"Check {effective_network.upper()}_RPC_URL in your .env, or this network's rpc_url "
            f"in your dincli config — it points at a different chain.",
            details={
                "network": effective_network,
                "expected_chain_id": expected,
                "actual_chain_id": actual,
            },
        )
    return w3
