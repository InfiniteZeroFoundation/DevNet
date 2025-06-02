from web3 import Web3
from dotenv import dotenv_values
import json   
from services.blockchain_services import get_w3
   
def get_DINCoordinator_Instance(dincoordinator_address=None):
    w3 = get_w3()
    if dincoordinator_address is None:
        dincoordinator_address = dotenv_values(".env").get("DINCoordinator_Contract_Address")
    
    with open("../../hardhat/artifacts/contracts/DinCoordinator.sol/DinCoordinator.json") as f:
        dincoordinator_data = json.load(f)
        dincoordinator_abi = dincoordinator_data["abi"]
        dincoordinator_bytecode = dincoordinator_data["bytecode"]
    
    if dincoordinator_address:
        deployed_DINCoordinatorContract = w3.eth.contract(address=dincoordinator_address, abi=dincoordinator_abi)
        return deployed_DINCoordinatorContract
    else:
        return w3.eth.contract(abi=dincoordinator_abi, bytecode=dincoordinator_bytecode)
    
def get_DINtokenContract_Instance(dintoken_address=None):
    w3 = get_w3()
    if dintoken_address is None:
        dintoken_address = dotenv_values(".env").get("DINToken_Contract_Address")
    
    with open("../../hardhat/artifacts/contracts/DinToken.sol/DinToken.json") as f:
        dintoken_data = json.load(f)
        dintoken_abi = dintoken_data["abi"]
        dintoken_bytecode = dintoken_data["bytecode"]
    
    if dintoken_address:
        deployed_DINtokenContract = w3.eth.contract(address=dintoken_address, abi=dintoken_abi)
        return deployed_DINtokenContract
    else:
        return w3.eth.contract(abi=dintoken_abi, bytecode=dintoken_bytecode)
    