from fastapi import APIRouter, HTTPException, Body
from web3 import Web3
import os, shutil
from dotenv import load_dotenv, set_key, unset_key, dotenv_values
import requests
import json
from collections import OrderedDict
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import pickle
from pydantic import BaseModel
from typing import Optional

from services.blockchain_services import get_w3
from services.dataset_service import load_mnist_dataset, save_datasets
from services.partition_service import partition_dataset, save_partitioned_data
from services.model_architect import getGenesisModelIpfs, get_DINTaskCoordinator_Instance


from services.client_services import train_client_model_and_upload_to_ipfs
from services.DAO_services import get_DINCoordinator_Instance, get_DINtokenContract_Instance

load_dotenv()

router = APIRouter()

RPC_URL = os.getenv("RPC_URL")           # e.g. "http://127.0.0.1:8545"


@router.get("/distribute/dataset")
def distribute_dataset():
    num_clients = 9
    try:
        
        # Step 1: Load the dataset
        train_dataset, test_dataset = load_mnist_dataset()

        # Step 2: Save the datasets to disk
        save_datasets(train_dataset, test_dataset, output_dir="./Dataset")
        
        # Step 3: Partition the dataset
        partitioned_data = partition_dataset(train_dataset, num_clients)
        
        # Step 4: Save the partitioned data
        save_partitioned_data(partitioned_data, output_dir="./Dataset/clients")
        
        return {"message": "Dataset distributed successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}


@router.get("/modelowner/getGIState")
def get_GIState():
    try:
        env_config = dotenv_values(".env")
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        if DINTaskCoordinator_Contract_Address is None:
            return {"message": "DINTaskCoordinator_Contract_Address not found",
                    "status": "error",
                    "GI": 0,
                    "GIstate": "contract not deployed"}
        else:
            
            deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
            
            GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
            GIstate = env_config.get("GIstate")
            
            return {"message": "GI state fetched successfully",
                    "status": "success",
                    "GI": GI,
                    "GIstate": GIstate}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "GI": None,
                "GIstate": None}


@router.post("/modelowner/getModelOwnerState")
def get_modelowner_state():
    
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        model_owner_address = env_config.get("ModelOwner_Address")
        
        if model_owner_address is None:
            model_owner_address = w3.eth.accounts[1] 
            set_key(".env", "ModelOwner_Address", model_owner_address)
        
        DinCoordinator_Contract_Address = env_config.get("DINCoordinator_Contract_Address")
        
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        if DINTaskCoordinator_Contract_Address is None:
            dintaskcoordinator_dintoken_balance = 0
        else:
            deployed_DINTokenContract = get_DINtokenContract_Instance(dintoken_address=DINToken_Contract_Address)
            dintaskcoordinator_dintoken_balance = deployed_DINTokenContract.functions.balanceOf(DINTaskCoordinator_Contract_Address).call()
        
        
        if DINToken_Contract_Address is None:
            model_owner_dintoken_balance = 0
            
        else:
            deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DINToken_Contract_Address)
            model_owner_dintoken_balance = deployed_DINtokenContract.functions.balanceOf(model_owner_address).call()
            
            
        return {
            "message": "Model owner state fetched successfully",
            "status": "success",
            "model_owner_address": model_owner_address,
            "model_owner_eth_balance": w3.from_wei(w3.eth.get_balance(model_owner_address), 'ether'),
            "model_owner_dintoken_balance": model_owner_dintoken_balance,
            "dintaskcoordinator_address": DINTaskCoordinator_Contract_Address,
            "dintaskcoordinator_dintoken_balance": dintaskcoordinator_dintoken_balance,
            }
            
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "model_owner_address": None,
                "model_owner_eth_balance": None,
                "model_owner_dintoken_balance": None,
                "dintaskcoordinator_address": None,
                "dintaskcoordinator_dintoken_balance": None,
                "IS_GenesisModelCreated": False,
                "model_ipfs_hash": None,}
    

@router.post("/modelowner/depositAndMintDINTokens")
def deposit_and_mint_dintokens():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        model_owner_address = env_config.get("ModelOwner_Address")
        dincoordinator_address = env_config.get("DINCoordinator_Contract_Address")
        deploy_dincoordinator_contract = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_address)
        
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        tx_hash = deploy_dincoordinator_contract.functions.depositAndMint().transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
            "value": w3.to_wei("1", "ether"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if DINToken_Contract_Address is None:
            model_owner_dintoken_balance = 0
        else:
            deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DINToken_Contract_Address)
            model_owner_dintoken_balance = deployed_DINtokenContract.functions.balanceOf(model_owner_address).call()
            
        return {"message": "DIN tokens deposited and minted successfully",
                "status": "success",
                "model_owner_dintoken_balance": model_owner_dintoken_balance,
                "model_owner_eth_balance": w3.from_wei(w3.eth.get_balance(model_owner_address), 'ether')}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.post("/modelowner/depositRewardInDINTaskCoordinator")
def deposit_reward_in_dintaskcoordinator():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        dintoken_contract_address = env_config.get("DINToken_Contract_Address")
        dintaskcoordinator_contract_address = env_config.get("DINTaskCoordinator_Contract_Address")
        deployed_dintoken_contract = get_DINtokenContract_Instance(dintoken_address=dintoken_contract_address)
        
        amount = 1000000
        
        
        print(" in fn deposit_reward_in_dintaskcoordinator")
        print("dintoken_contract_address:", dintoken_contract_address)
        print("dintaskcoordinator_contract_address:", dintaskcoordinator_contract_address)
        print("model_owner_address:", model_owner_address)
        print("Approving DINTaskCoordinator contract...")
        
        
        tx_hash = deployed_dintoken_contract.functions.approve(dintaskcoordinator_contract_address, amount).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei")
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        deployed_dintaskcoordinator_contract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=dintaskcoordinator_contract_address)
        
        deployed_dintaskcoordinator_contract.functions.depositReward(amount).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei")
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        
        
        if dintoken_contract_address is None:
            model_owner_dintoken_balance = 0
        else:
            deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=dintoken_contract_address)
            model_owner_dintoken_balance = deployed_DINtokenContract.functions.balanceOf(model_owner_address).call()
            
            dintaskcoordinator_dintoken_balance = deployed_DINtokenContract.functions.balanceOf(dintaskcoordinator_contract_address).call()
            
        return {"message": "DIN reward deposited successfully",
                "status": "success",
                "model_owner_dintoken_balance": model_owner_dintoken_balance,
                "dintaskcoordinator_dintoken_balance": dintaskcoordinator_dintoken_balance,
                "model_owner_eth_balance": w3.from_wei(w3.eth.get_balance(model_owner_address), 'ether')}
    except Exception as e:
        print("Error depositing reward:", e)
        return {"message": str(e),
                "status": "error"}
        
@router.post("/modelowner/deployDINTaskCoordinator")
def deploy_dintaskcoordinator():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        model_owner_address = env_config.get("ModelOwner_Address")
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        DINTaskCoordinator_contract = get_DINTaskCoordinator_Instance()
        constructor_tx_hash  = DINTaskCoordinator_contract.constructor(DINToken_Contract_Address).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        constructor_receipt = w3.eth.wait_for_transaction_receipt(constructor_tx_hash)
        dintaskcoordinator_contract_address = constructor_receipt.contractAddress
        
        print("DINTaskCoordinator contract deployed at:", dintaskcoordinator_contract_address)
        
        set_key(".env", "DINTaskCoordinator_Contract_Address", dintaskcoordinator_contract_address)
        set_key(".env", "GIstate", "Awaiting Genesis Model")
        
        DINToken_contract = get_DINtokenContract_Instance(dintoken_address=DINToken_Contract_Address)
        
        dintaskcoordinatorDintokenBalance = DINToken_contract.functions.balanceOf(dintaskcoordinator_contract_address).call()
        
        return {"message": "DINTaskCoordinator contract deployed successfully",
                "status": "success",
                "dintaskcoordinator_contract_address": dintaskcoordinator_contract_address,
                "dintaskcoordinator_dintoken_balance": dintaskcoordinatorDintokenBalance}
        
    except Exception as e:
        print("Error deploying DINTaskCoordinator:", e)
        return {"message": str(e),
                "status": "error"}

@router.post("/modelowner/getGenesisModelsetF")
def get_genesis_modelsetF():
    try:
        env_config = dotenv_values(".env")
        IS_GenesisModelCreated = env_config.get("IS_GenesisModelCreated")
        model_hash = env_config.get("GenesisModelIpfsHash")
        dincoordinator_address = env_config.get("DINCoordinator_Contract_Address")
        return {"message": "Genesis model state fetched successfully",
                "status": "success",
                "IS_GenesisModelCreated": IS_GenesisModelCreated,
                "model_ipfs_hash": model_hash,
                "dincordinator_address": dincoordinator_address}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "IS_GenesisModelCreated": False, 
                "model_ipfs_hash": None,
                "dincordinator_address": None}


@router.post("/modelowner/createGenesisModel")
def create_genesis_model():
    try:
        
        w3 = get_w3()
        model_hash = getGenesisModelIpfs()
        
        model_owner_account = w3.eth.accounts[1] # = w3.eth.account.from_key(private_keys[0])
        print("Model owner account:", model_owner_account)
        
        
        # Create contract instance
        deployed_DINCoordinatorContract = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_contract_address)
        
        tx_hash = deployed_DINCoordinatorContract.functions.setGenesisModelIpfsHash(model_hash).transact({
            "from": model_owner_account,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
        print("GenesisModelIpfsHash set in DINCoordinator contract with hash: ", model_hash)
        
        set_key(".env", "DINCoordinator_Contract_Address", dincoordinator_contract_address)
        set_key(".env", "IS_GenesisModelCreated", "True")
        set_key(".env", "GenesisModelIpfsHash", model_hash)
        
        env_config = dotenv_values(".env")
        dincoordinator_address = env_config.get("DINCoordinator_Contract_Address")
        
        
        return {"message": "Genesis model created & uploaded to IPFS successfully, logged in smart contract",
                "status": "success",
                "IS_GenesisModelCreated": True,
                "model_ipfs_hash": model_hash,
                "dincordinator_address": dincoordinator_address}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "IS_GenesisModelCreated": False,
                "model_ipfs_hash": None,
                "dincordinator_address": None}


@router.post("/clients/getClientModelsCreatedF")
def get_client_models_created_f():
    try:
        env_config = dotenv_values(".env")
        client_models_created_f = env_config.get("ClientModelsCreatedF")=="True"
        
        print("Client models created state:", client_models_created_f)
        w3 = get_w3()
        
        env_config = dotenv_values(".env")
        DINCoordinator_Contract_Address = env_config.get("DINCoordinator_Contract_Address")
        
        client_model_ipfs_hashes = []
        ClientAddresses = None
        
        if client_models_created_f:
            deployed_DINCoordinatorContract = get_DINCoordinator_Instance(dincoordinator_address=DINCoordinator_Contract_Address)
            
            current_GI = deployed_DINCoordinatorContract.functions.getGI().call()
            
            ClientAddresses = deployed_DINCoordinatorContract.functions.getClientAddresses(current_GI).call()
            
            
            
            for i, client_address in enumerate(ClientAddresses):
                client_model_ipfs_hash = deployed_DINCoordinatorContract.functions.getClientModel(current_GI, client_address).call()
                client_model_ipfs_hashes.append(client_model_ipfs_hash)
                
            
            
        return {"message": "Client models state fetched successfully",
                "status": "success",
                "client_models_created_f": client_models_created_f,
                "client_model_ipfs_hashes": client_model_ipfs_hashes,
                "client_addresses": ClientAddresses}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "client_models_created_f": False,
                "client_model_ipfs_hashes": None,
                "client_addresses": None}


class ClientModelCreateRequest(BaseModel):
    DPMode: str  # Must be one of: "disabled", "beforeTraining", or "afterTraining"

@router.post("/clients/createClientModels")
def create_client_models(request: ClientModelCreateRequest):
    try:
        
        dp_mode = request.DPMode
        print("DPMode: ", dp_mode)
        

        # Optional: Validate the value
        valid_modes = ["disabled", "afterTraining"]
        if dp_mode not in valid_modes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid DPMode. Must be one of {valid_modes}."
            )
        
        w3 = get_w3()
        
        env_config = dotenv_values(".env")
        DINCoordinator_Contract_Address = env_config.get("DINCoordinator_Contract_Address")
        
        deployed_DINCoordinatorContract = get_DINCoordinator_Instance(dincoordinator_address=DINCoordinator_Contract_Address)
        
        current_GI = deployed_DINCoordinatorContract.functions.getGI().call()
        
        
        genesis_model_ipfs_hash = deployed_DINCoordinatorContract.functions.getGenesisModelIpfsHash().call()
            
        client_model_ipfs_hashes = train_client_model_and_upload_to_ipfs(genesis_model_ipfs_hash, initial_model_ipfs_hash=None, dp_mode=dp_mode)
            
        for i, ipfs_model_hash in enumerate(client_model_ipfs_hashes):
            deployed_DINCoordinatorContract.functions.submitLocalModel(ipfs_model_hash, current_GI).transact({
                "from": w3.eth.accounts[i+2],
                "gas": 3000000,
                "gasPrice": w3.to_wei("5", "gwei"),
            })
            
        set_key(".env", "ClientModelsCreatedF", "True")
        
        return {"message": "Client models created successfully",
                "status": "success",
                "client_models_created_f": True,
                "client_model_ipfs_hashes": client_model_ipfs_hashes,
                "client_addresses": w3.eth.accounts[2:2+len(client_model_ipfs_hashes)]}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "client_models_created_f": False}
        
        
@router.post("/dindao/deployDINCoordinator")
def deploy_dincoordinator():
    try:
        
        w3 = get_w3()
        DINCoordinator_contract = get_DINCoordinator_Instance()
        
        constructor_tx_hash  = DINCoordinator_contract.constructor().transact({
            "from": w3.eth.accounts[0],
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        constructor_receipt = w3.eth.wait_for_transaction_receipt(constructor_tx_hash)
        dincoordinator_contract_address = constructor_receipt.contractAddress
        
        print("DINCoordinator contract deployed at:", dincoordinator_contract_address)
        
        
        set_key(".env", "DINCoordinator_Contract_Address", dincoordinator_contract_address)
        # Create contract instance
        deployed_DINCoordinatorContract = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_contract_address)
        
        DINCoordinator_Eth_balance = w3.from_wei(w3.eth.get_balance(dincoordinator_contract_address), 'ether')  
        
        env_config = dotenv_values(".env")
        dincoordinator_address = env_config.get("DINCoordinator_Contract_Address")
        
        
        dintoken_address = deployed_DINCoordinatorContract.functions.dintoken().call()
        
        set_key(".env", "DINToken_Contract_Address", dintoken_address)
        
        env_config = dotenv_values(".env")
        dintoken_address = env_config.get("DINToken_Contract_Address")
        
        
        w3.eth.accounts[0]
        
        return {"message": "DINCoordinator contract deployed successfully",
                "status": "success",
                "dincordinator_address": dincoordinator_address,
                "dintoken_address": dintoken_address,
                "DINDAORepresentative_address": w3.eth.accounts[0],
                "DINDAORepresentative_Eth_balance": w3.from_wei(w3.eth.get_balance(w3.eth.accounts[0]), 'ether'),
                "DINCoordinator_Eth_balance": DINCoordinator_Eth_balance}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "dincordinator_address": None,
                "dintoken_address": None,
                "DINDAORepresentative_address": w3.eth.accounts[0],
                "DINDAORepresentative_Eth_balance": w3.from_wei(w3.eth.get_balance(w3.eth.accounts[0]), 'ether'),
                "DINCoordinator_Eth_balance": None}


@router.post("/dindao/getDINDAOState")
def get_dindao_state():
    try:
        env_config = dotenv_values(".env")
        DINCoordinator_Contract_Address = env_config.get("DINCoordinator_Contract_Address")
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        w3 = get_w3()
        DINDAORepresentative_address = w3.eth.accounts[0]
        
        if DINCoordinator_Contract_Address is None:
            DINCoordinator_Eth_balance = 0
        else:
            DINCoordinator_Eth_balance = w3.from_wei(w3.eth.get_balance(DINCoordinator_Contract_Address), 'ether')    
            
        
        return {"message": "DINDAO state fetched successfully",
                "status": "success",
                "dincordinator_address": DINCoordinator_Contract_Address,
                "dintoken_address": DINToken_Contract_Address,
                "DINDAORepresentative_address": DINDAORepresentative_address,
                "DINDAORepresentative_Eth_balance": w3.from_wei(w3.eth.get_balance(DINDAORepresentative_address), 'ether'),
                "DINCoordinator_Eth_balance": DINCoordinator_Eth_balance}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
    

@router.get("/reset/resetall")
def resetall():
    try:
        unset_key(".env", "DINCoordinator_Contract_Address")
        unset_key(".env", "DINToken_Contract_Address")
        unset_key(".env", "TaskCoordinator_Contract_Address")
        unset_key(".env", "IS_GenesisModelCreated")
        unset_key(".env", "GenesisModelIpfsHash")
        unset_key(".env", "ClientModelsCreatedF")
        unset_key(".env", "DINTaskCoordinator_Contract_Address")
        unset_key(".env", "ModelOwner_Address")
        
        
        return {"message": "ALL Reset successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.get("/test")
def test():
    return {"message": "Router is working!"}