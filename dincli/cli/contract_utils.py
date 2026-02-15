import json
import os

# Minimal ABIs
erc20_abi = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # --- Added: transfer ---
    {
        "constant": False,
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # --- Added: transferFrom ---
    {
        "constant": False,
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "transferFrom",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    }

]
router_abi = [
    # For estimating input ETH needed
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsIn",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    # For executing the swap (ETH -> exact USDT)
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapETHForExactTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
        "type": "function"
    }
]


def get_contract_instance(
    artifact_path: str,
    network: str,
    address: str | None = None
) :
    """
    Load a contract instance from an artifact (Hardhat format).
    
    Args:
        artifact_path: Path to JSON artifact (must have "abi")
        network: Target network (e.g., "local", "sepolia")
        address: If provided, returns deployed contract. If None, returns deployable contract (requires "bytecode").
    
    Returns:
        web3.contract.Contract
    """

    from dincli.cli.utils import get_w3
    w3 = get_w3(network)
    
    if not os.path.isfile(artifact_path):
        raise FileNotFoundError(
            f"Contract artifact not found at: {artifact_path}\n"
            "Tip: Ensure the contract is compiled and the path is correct."
        )
    
    try:
        with open(artifact_path) as f:
            data = json.load(f)
    except JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse JSON in artifact: {artifact_path}\n"
            f"Reason: {str(e)}\n"
            "Tip: This may indicate a corrupted or incomplete build. Try recompiling the contract."
        ) from e
    
    if "abi" not in data:
        raise ValueError(f"Artifact {artifact_path} missing 'abi' field")
    abi = data["abi"]
    
    if address:
        # Interaction mode: only ABI needed
        return w3.eth.contract(address=address, abi=abi)
    else:
        # Deployment mode: bytecode required
        bytecode = data.get("bytecode")
        if not bytecode:
            raise ValueError(
                f"Artifact {artifact_path} missing 'bytecode' — required for deployment.\n"
                "Tip: Use `dincli dindao dump-abi --bytecode` to include it."
            )
        return w3.eth.contract(abi=abi, bytecode=bytecode)
