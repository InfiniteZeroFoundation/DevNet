# dincli/networks.py
NETWORKS = {
    "local": {
        "rpc_url": "http://127.0.0.1:8545",
        "chain_id": 31337,
        "explorer": "http://127.0.0.1:8545",

    },
    "sepolia": {
        "rpc_url": "https://sepolia.infura.io/v3/YOUR_INFURA_KEY",
        # OR use a free Alchemy/QuickNode endpoint
        "chain_id": 11155111,
        "explorer": "https://sepolia.etherscan.io",
    },
    "mainnet": {
        "rpc_url": "https://mainnet.infura.io/v3/YOUR_INFURA_KEY",
        "chain_id": 1,
        "explorer": "https://etherscan.io",
    }
}