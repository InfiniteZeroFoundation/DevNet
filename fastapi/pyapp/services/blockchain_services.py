from web3 import Web3
from dotenv import dotenv_values
import os

RPC_URL = os.getenv("RPC_URL")           # e.g. "http://127.0.0.1:8545"

def get_w3():
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(status_code=400, detail="Could not connect to Ethereum node.")
        return w3
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not connect to Ethereum node: {e}")