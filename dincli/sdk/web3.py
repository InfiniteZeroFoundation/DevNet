from web3 import Web3

from dincli.sdk.config import resolve_network_value


def get_w3(effective_network):
    rpc_url = resolve_network_value(effective_network, "rpc_url")
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise ConnectionError(f"Could not connect to Ethereum node at {rpc_url}")
        return w3
    except Exception as e:
        # TODO(sdk-keystones): NetworkError
        raise ConnectionError(f"Could not connect to Ethereum node for network '{effective_network}': {e}") from e
