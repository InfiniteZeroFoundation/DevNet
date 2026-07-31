from web3 import Web3

from dincli.sdk.config import resolve_network_value
from dincli.sdk.errors import NetworkError, RPC_UNREACHABLE


def get_w3(effective_network):
    rpc_url = resolve_network_value(effective_network, "rpc_url")
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise NetworkError(
                f"Could not connect to Ethereum node at {rpc_url}",
                code=RPC_UNREACHABLE,
                details={"endpoint_host": rpc_url},
            )
        return w3
    except NetworkError:
        raise
    except Exception as e:
        raise NetworkError(
            f"Could not connect to Ethereum node for network '{effective_network}': {e}",
            code=RPC_UNREACHABLE,
            details={"endpoint_host": rpc_url},
        ) from e
