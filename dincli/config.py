import os, json
from dotenv import load_dotenv

def load_config():
    # Main selector
    load_dotenv(".env")
    NETWORK = os.getenv("NETWORK", "local")

    # Load network-specific env
    env_file = f".env.{NETWORK}"
    if os.path.exists(env_file):
        load_dotenv(env_file, override=True)

    # Load contract addresses
    with open("networks.json") as f:
        network_data = json.load(f)[NETWORK]

    return {
        "network": NETWORK,
        "rpc_url": os.getenv("RPC_URL"),
        "ipfs_url": os.getenv("IPFS_URL"),
        "private_key": os.getenv("PRIVATE_KEY"),
        "addresses": network_data,
    }
