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
import time
from pydantic import BaseModel
from typing import Optional

from services.blockchain_services import get_w3
from services.dataset_service import load_mnist_dataset, save_datasets
from services.partition_service import partition_dataset, save_partitioned_data
from services.model_architect import getGenesisModelIpfs, get_DINTaskCoordinator_Instance


from services.client_services import train_client_model_and_upload_to_ipfs
from services.DAO_services import get_DINCoordinator_Instance, get_DINtokenContract_Instance, get_DINValidatorStake_Instance

load_dotenv()

router = APIRouter()

RPC_URL = os.getenv("RPC_URL")           # e.g. "http://127.0.0.1:8545"

MIN_STAKE = 1000000 
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
        print("getting GI state")
        if DINTaskCoordinator_Contract_Address is None:
            return {"message": "DINTaskCoordinator_Contract_Address not found",
                    "status": "error",
                    "GI": 0,
                    "GIstatedes": "DINTaskCoordinator contract not deployed"}
        else:
            
            deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
            
            GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
            
            GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
            
            if GIstate == 0:
                GIstatedes = "Awaiting Genesis Model"
            elif GIstate == 1:
                GIstatedes = "Genesis Model Created"
            elif GIstate == 2:
                GIstatedes = "GI started"
            elif GIstate == 3:
                GIstatedes = "LM submissions started"
            elif GIstate == 4:
                GIstatedes = "LM submissions closed"
            elif GIstate == 5:
                GIstatedes = "LM submissions evaluation closed"
            elif GIstate == 6:
                GIstatedes = "T1nT2B created"
            elif GIstate == 7:
                GIstatedes = "T1B aggregation started"
            elif GIstate == 8:
                GIstatedes = "T1B aggregation done"
            elif GIstate == 9:
                GIstatedes = "T2B aggregation started"
            elif GIstate == 10:
                GIstatedes = "T2B aggregation done"
            elif GIstate == 11:
                GIstatedes = "GI ended"
            
            
            return {"message": "GI state fetched successfully",
                    "status": "success",
                    "GI": GI,
                    "GIstate": GIstate,
                    "GIstatedes": GIstatedes}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "GI": None,
                "GIstate": None,
                "GIstatedes": None}

@router.post("/modelowner/startGI")
def start_GI():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        tx_hash = deployed_DINTaskCoordinatorContract.functions.startGI(curr_GI+1).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return {"message": "GI started successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.post("/modelowner/getModelOwnerState")
def get_modelowner_state():
    
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        model_owner_address = env_config.get("ModelOwner_Address")
        
        client_models_created_f = env_config.get("ClientModelsCreatedF")
        
        if model_owner_address is None:
            model_owner_address = w3.eth.accounts[1] 
            set_key(".env", "ModelOwner_Address", model_owner_address)
        
        DinCoordinator_Contract_Address = env_config.get("DINCoordinator_Contract_Address")
        
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        IS_GenesisModelCreated = env_config.get("IS_GenesisModelCreated")
        model_hash = env_config.get("GenesisModelIpfsHash")
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
        
        registered_validators = []
            
        if DINTaskCoordinator_Contract_Address is not None:
            deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
            
            curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
            
            curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
            
            if curr_GIstate >= 2 and curr_GIstate < 4:
                registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
            
        return {
            "message": "Model owner state fetched successfully",
            "status": "success",
            "model_owner_address": model_owner_address,
            "model_owner_eth_balance": w3.from_wei(w3.eth.get_balance(model_owner_address), 'ether'),
            "model_owner_dintoken_balance": model_owner_dintoken_balance,
            "dintaskcoordinator_address": DINTaskCoordinator_Contract_Address,
            "dintaskcoordinator_dintoken_balance": dintaskcoordinator_dintoken_balance,
            "IS_GenesisModelCreated": IS_GenesisModelCreated,
            "model_ipfs_hash": model_hash,
            "registered_validators": registered_validators,
            "client_models_created_f": client_models_created_f
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
                "model_ipfs_hash": None,
                "IS_GenesisModelCreated": False,
                "model_ipfs_hash": None
                }
    

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
        
        DinValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        DINTaskCoordinator_contract = get_DINTaskCoordinator_Instance()
        constructor_tx_hash  = DINTaskCoordinator_contract.constructor(DINToken_Contract_Address, DinValidatorStake_Contract_Address).transact({
            "from": model_owner_address,
            "gas": 2*3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        constructor_receipt = w3.eth.wait_for_transaction_receipt(constructor_tx_hash)
        dintaskcoordinator_contract_address = constructor_receipt.contractAddress
        
        print("DINTaskCoordinator contract deployed at:", dintaskcoordinator_contract_address)
        
        set_key(".env", "DINTaskCoordinator_Contract_Address", dintaskcoordinator_contract_address)
        
        DINToken_contract = get_DINtokenContract_Instance(dintoken_address=DINToken_Contract_Address)
        
        dintaskcoordinatorDintokenBalance = DINToken_contract.functions.balanceOf(dintaskcoordinator_contract_address).call()
        
        return {"message": "DINTaskCoordinator contract deployed successfully",
                "status": "success",
                "dintaskcoordinator_contract_address": dintaskcoordinator_contract_address,
                "dintaskcoordinator_dintoken_balance": dintaskcoordinatorDintokenBalance, 
                }
        
    except Exception as e:
        print("Error deploying DINTaskCoordinator:", e)
        return {"message": str(e),
                "status": "error"}


@router.post("/modelowner/createGenesisModel")
def create_genesis_model():
    try:
        
        w3 = get_w3()
        model_hash = getGenesisModelIpfs()
        
        
        
        env_config = dotenv_values(".env")
        
        model_owner_account = env_config.get("ModelOwner_Address")
        print("Model owner account:", model_owner_account)
        
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.setGenesisModelIpfsHash(model_hash).transact({
            "from": model_owner_account,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
        print("GenesisModelIpfsHash set in DINTaskCoordinator contract with hash: ", model_hash)
        

        set_key(".env", "IS_GenesisModelCreated", "True")
        set_key(".env", "GenesisModelIpfsHash", model_hash)
    

        
        return {"message": "Genesis model created & uploaded to IPFS successfully, logged in smart contract",
                "status": "success",
                "IS_GenesisModelCreated": True,
                "model_ipfs_hash": model_hash,}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "IS_GenesisModelCreated": False,
                "model_ipfs_hash": None}


@router.post("/modelowner/startGI")
def start_GI():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.startGI().transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return {"message": "GI started successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.post("/modelowner/startLMsubmissions")
def start_LMsubmissions():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        tx_hash = deployed_DINTaskCoordinatorContract.functions.startLMsubmissions(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return {"message": "LM submissions started successfully",
                "status": "success"}
    except Exception as e:
        print("Error starting LM submissions:", e)
        return {"message": str(e),
                "status": "error"}

@router.post("/modelowner/closeLMsubmissions")
def close_LMsubmissions():
    try:
        print("in closeLMsubmissions")
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        GI_state = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GI < 1 or GI_state != 3:
            raise Exception("Can not close LM submissions at this time")
        tx_hash = deployed_DINTaskCoordinatorContract.functions.closeLMsubmissions(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return {"message": "LM submissions closed successfully",
                "status": "success"}
    except Exception as e:
        print("Error closing LM submissions:", e)
        return {"message": str(e),
                "status": "error"}


@router.post("/modelowner/getClientModels")
def get_modelowner_client_models():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate < 4:
            raise Exception("Can not get client models at this time")
        
        lm_submissions = deployed_DINTaskCoordinatorContract.functions.getClientModels(curr_GI).call()
        
        print("lm_submissions: ", lm_submissions)
        
        
        
        return {"message": "LM submissions collected successfully",
                "status": "success",
                "lm_submissions": lm_submissions}
    except Exception as e:
        print("Error collecting LM submissions:", e)
        return {"message": str(e),
                "status": "error"}
        
class ClientModelRequest(BaseModel):
    client_address: str
    approved: bool

@router.post("/modelowner/approveClientModel")
def approve_client_model(request: ClientModelRequest):
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 4:
            raise Exception("Can not approve client model at this time")
        
        deployed_DINTaskCoordinatorContract.functions.evaluateLM(curr_GI, request.client_address, request.approved).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "Client model approved successfully",
                "status": "success"}
    except Exception as e:
        print("Error approving client model:", e)
        return {"message": str(e),
                "status": "error"}
    
@router.post("/modelowner/rejectClientModel")
def reject_client_model(request: ClientModelRequest):
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 4:
            raise Exception("Can not reject client model at this time")
        
        deployed_DINTaskCoordinatorContract.functions.evaluateLM(curr_GI, request.client_address, False).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "Client model rejected successfully",
                "status": "success"}
    except Exception as e:
        print("Error rejecting client model:", e)
        return {"message": str(e),
                "status": "error"}
    
@router.post("/modelowner/closeLMsubmissionsEvaluation")
def closeLMsubmissionsEvaluation():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 4:
            raise Exception("Can not close LM submissions evaluation at this time")
        
        deployed_DINTaskCoordinatorContract.functions.finalizeEvaluation(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "LM submissions evaluation closed successfully",
                "status": "success"}
    except Exception as e:
        print("Error closing LM submissions evaluation:", e)
        return {"message": str(e),
                "status": "error"}

@router.post("/modelowner/createTier1n2Batches")
def createTier1Batches():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 5:
            raise Exception("Can not create Tier 1 n 2 batches at this time")
        
        deployed_DINTaskCoordinatorContract.functions.autoCreateTier1AndTier2(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "Tier 1 n 2 batches created successfully",
                "status": "success"}
    except Exception as e:
        print("Error creating Tier 1 n 2 batches:", e)
        return {"message": str(e),
                "status": "error"}
        
        
class Tier1Batch(BaseModel):
    batch_id: int
    validators: list[str]
    model_indexes: list[int]
    finalized: bool
    final_cid: str

class Tier2Batch(BaseModel):
    batch_id: int
    validators: list[str]
    finalized: bool
    final_cid: str

class BatchPayload(BaseModel):
    tier1_batches: list[Tier1Batch]
    tier2_batches: list[Tier2Batch]
    message: str
    status: str
    
@router.post("/modelowner/getTier1n2Batches")
def getTier1n2Batches():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate < 6:
            raise Exception("Can not get Tier 1 n 2 batches at this time")
        
        t1_batches_count  = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()
        
        t1_list = []
        
        for i in range(t1_batches_count):
            (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
            t1_list.append(Tier1Batch(batch_id=bid, validators=val, model_indexes=idxs, finalized=fin, final_cid=cid))
        
        t2_list = []
        t2_batches_count = 1
        
        for i in range(t2_batches_count):
            (bid, val, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, i).call()
            t2_list.append(Tier2Batch(batch_id=bid, validators=val, finalized=fin, final_cid=cid))
            
        return BatchPayload(tier1_batches=t1_list,
                            tier2_batches=t2_list,
                            message="Tier 1 n 2 batches retrieved successfully",
                            status="success")
    except Exception as e:
        print("Error getting Tier 1 n 2 batches:", e)
        return BatchPayload(tier1_batches=[],
                            tier2_batches=[],
                            message=str(e),
                            status="error")
  
@router.post("/modelowner/startT1Aggregation")
def start_T1Aggregation():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 6:
            raise Exception("Can not start Tier 1 Aggregation at this time")
        
        deployed_DINTaskCoordinatorContract.functions.startT1Aggregation(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "Tier 1 Aggregation started successfully",
                "status": "success"}
    except Exception as e:
        print("Error starting Tier 1 Aggregation:", e)
        return {"message": str(e),
                "status": "error"}
    
@router.post("/validators/getValidatorsState")
def get_validators_state():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        Validator_Adresses = w3.eth.accounts[2+9:2+9+12]
        
        print("in getValidatorsState")
        
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        DinValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        print("DINValidatorStake_Contract_Address: ", DinValidatorStake_Contract_Address)
        
        Dintaskcoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        print("Dintaskcoordinator_Contract_Address: ", Dintaskcoordinator_Contract_Address)
        
        registered_validators = []
        all_reg_val_assigned_t1_batches = []
        all_reg_val_assigned_t2_batches = []
        all_res_val_t1 = []
        all_res_val_t2 = []
        
        
        if Dintaskcoordinator_Contract_Address is not None:
        
            deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=Dintaskcoordinator_Contract_Address)
            
            curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
            
            print("curr_GI: ", curr_GI)
            
            GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
            
            print("GIstate: ", GIstate)
            
            
            if curr_GI > 0 and GIstate >= 2:
                registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
                print("registered_validators: ", registered_validators)
                
            if curr_GI > 0 and GIstate >= 7:
                t1_batches_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()
                print("t1_batches_count: ", t1_batches_count)
                
                t2_batches_count = 1
                
                for validator_address in registered_validators:
                    val_assigned_t1_batches = []
                    for i in range(t1_batches_count):
                        (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
                        if validator_address in val:
                            val_assigned_t1_batches.append(Tier1Batch(batch_id=bid, validators=val, model_indexes=idxs, finalized=fin, final_cid=cid))
                            
                    val_assigned_t2_batches = []  
                    for i in range(t2_batches_count):
                        (bid, val, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, i).call()
                        if validator_address in val:
                            val_assigned_t2_batches.append(Tier2Batch(batch_id=bid, validators=val, finalized=fin, final_cid=cid))    
                            
                    all_reg_val_assigned_t1_batches.append(val_assigned_t1_batches)
                    all_reg_val_assigned_t2_batches.append(val_assigned_t2_batches)
        
        if DinToken_Contract_Address is  not None:
            deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
        
        ValidatoDintokenBalances = []
        ValidatoETHBalances = []
        ValidatorDinStakedTokens = []
        
        for validator_address in Validator_Adresses:
            
            if DinToken_Contract_Address is  not None:
                validator_dintoken_balance = deployed_DINtokenContract.functions.balanceOf(validator_address).call()
                ValidatoDintokenBalances.append(validator_dintoken_balance)
            else:
                ValidatoDintokenBalances.append(0)
            
            validator_eth_balance = w3.from_wei(w3.eth.get_balance(validator_address), 'ether')
            ValidatoETHBalances.append(validator_eth_balance)
            
            if DinValidatorStake_Contract_Address is not None:
                deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DinValidatorStake_Contract_Address)
                validator_din_staked_tokens = deployed_DINValidatorStakeContract.functions.getStake(validator_address).call()
                print(validator_address, " --- validator_din_staked_tokens: ", validator_din_staked_tokens)
                ValidatorDinStakedTokens.append(validator_din_staked_tokens)
            else:
                ValidatorDinStakedTokens.append(0)
                
        
        
        
        return {"message": "Validators state fetched successfully",
                "status": "success",
                "validator_addresses": Validator_Adresses,
                "validator_dintoken_balances": ValidatoDintokenBalances,
                "validator_eth_balances": ValidatoETHBalances,
                "DINValidatorStakeAddress": DinValidatorStake_Contract_Address,
                "validator_din_staked_tokens": ValidatorDinStakedTokens, 
                "dintoken_address": DinToken_Contract_Address,
                "registered_validators": registered_validators,
                "all_reg_val_assigned_t1_batches": all_reg_val_assigned_t1_batches,
                "all_reg_val_assigned_t2_batches": all_reg_val_assigned_t2_batches,
                "all_res_val_t1": all_res_val_t1,
                "all_res_val_t2": all_res_val_t2}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
        
@router.post("/validators/buyDINTokens")
def buy_dintokens():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        
        Validator_Adresses = w3.eth.accounts[2+9:2+9+12]
        
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
        
        dincoordinator_contract_address = env_config.get("DINCoordinator_Contract_Address")
        
        deployed_dincoordinator = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_contract_address) 
        
        for validator_address in Validator_Adresses:
            tx_hash = deployed_dincoordinator.functions.depositAndMint().transact({
                "from": validator_address,
                "gas": 3000000,
                "gasPrice": w3.to_wei("5", "gwei"),
                "value": w3.to_wei("1", "ether"),
            })
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            
            time.sleep(0.1)
        
        
        ValidatoDintokenBalances = []
        ValidatoETHBalances = []
        
        for validator_address in Validator_Adresses:
            validator_dintoken_balance = deployed_DINtokenContract.functions.balanceOf(validator_address).call()
            ValidatoDintokenBalances.append(validator_dintoken_balance)
            
            validator_eth_balance = w3.from_wei(w3.eth.get_balance(validator_address), 'ether')
            ValidatoETHBalances.append(validator_eth_balance)
        
        
        
        return {"message": "DIN tokens bought successfully",
                "status": "success",
                "validator_addresses": Validator_Adresses,
                "validator_dintoken_balances": ValidatoDintokenBalances,
                "validator_eth_balances": ValidatoETHBalances}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
class ValidatorAddressRequest(BaseModel):
    validator_address: str

@router.post("/validators/buyDINTokensSingle")
def buy_dintokens_single(request: ValidatorAddressRequest):
    try:
        validator_address = request.validator_address
        env_config = dotenv_values(".env")
        w3 = get_w3()
        print("Validator address:", validator_address)
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
        
        dincoordinator_contract_address = env_config.get("DINCoordinator_Contract_Address")
        
        deployed_dincoordinator = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_contract_address) 
        
        tx_hash = deployed_dincoordinator.functions.depositAndMint().transact({
            "from": validator_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
            "value": w3.to_wei("1", "ether"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        time.sleep(0.1)
        
        return {"message": "DIN tokens bought successfully",
                "status": "success"}
        
        
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.post("/validators/stakeDINTokens")
def stake_dintokens():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        Validator_Adresses = w3.eth.accounts[2+9:2+9+12]
        
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
        
        DinValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DinValidatorStake_Contract_Address)
        
        MIN_STAKE = 1000000
        
        for validator_address in Validator_Adresses:
            
            validator_Din_token_balance = deployed_DINtokenContract.functions.balanceOf(validator_address).call()
            
            if validator_Din_token_balance >= MIN_STAKE:
                tx_approval_hash = deployed_DINtokenContract.functions.approve(DinValidatorStake_Contract_Address, MIN_STAKE).transact({"from": validator_address})
                
                receipt = w3.eth.wait_for_transaction_receipt(tx_approval_hash)
                
                tx_stake_hash = deployed_DINValidatorStakeContract.functions.stake(MIN_STAKE).transact({"from": validator_address})
                
                receipt = w3.eth.wait_for_transaction_receipt(tx_stake_hash)
      
        return {"message": "DIN tokens staked successfully",
                "status": "success"}          
                
    except Exception as e:
        return {"message": str(e),
                "status": "error"} 
            
        
@router.post("/validators/stakeDINTokensSingle")
def stake_dintokens_single(request: ValidatorAddressRequest):
    try:
        validator_address = request.validator_address
        env_config = dotenv_values(".env")
        w3 = get_w3()
        print("Validator address:", validator_address)
        
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
        
        DinValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DinValidatorStake_Contract_Address)
        
        
        
        validator_Din_token_balance = deployed_DINtokenContract.functions.balanceOf(validator_address).call()
        
        print("Validator Din token balance:", validator_Din_token_balance)
        
        if validator_Din_token_balance >= MIN_STAKE:
            tx_approval_hash = deployed_DINtokenContract.functions.approve(DinValidatorStake_Contract_Address, MIN_STAKE).transact({"from": validator_address})
            
            receipt = w3.eth.wait_for_transaction_receipt(tx_approval_hash)
            
            tx_stake_hash = deployed_DINValidatorStakeContract.functions.stake(MIN_STAKE).transact({"from": validator_address})
            
            receipt = w3.eth.wait_for_transaction_receipt(tx_stake_hash)
      
        return {"message": "DIN tokens staked successfully",
                "status": "success"}          
                
    except Exception as e:
        return {"message": str(e),
                "status": "error"}  
        
@router.post("/validators/registerTaskValidators")
def register_task_validators():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        DINValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DINValidatorStake_Contract_Address)
        
        
        
        Validator_Adresses = w3.eth.accounts[2+9:2+9+12]
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 2:
            raise Exception("Can not register validators at this time")
        
        registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
        
        for validator_address in Validator_Adresses:
            if validator_address not in registered_validators:
                
                validator_stake = deployed_DINValidatorStakeContract.functions.getStake(validator_address).call()
                
                if validator_stake >= MIN_STAKE:
                    tx_hash = deployed_DINTaskCoordinatorContract.functions.registerDINvalidator(curr_GI).transact({"from": validator_address})
                    
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                    
                    time.sleep(0.1)
        
        
        
        return {"message": "Task validators registered successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.post("/validators/registerTaskValidatorSingle")
def register_task_validator_single(request: ValidatorAddressRequest):
    try:
        validator_address = request.validator_address
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 2:
            raise Exception("Can not register validators at this time")
        
        registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
        
        if validator_address not in registered_validators:
            validator_stake = deployed_DINValidatorStakeContract.functions.getStake(validator_address).call()
            
            if validator_stake >= MIN_STAKE:
                tx_hash = deployed_DINTaskCoordinatorContract.functions.registerDINvalidator(curr_GI).transact({"from": validator_address})
                
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                
                time.sleep(0.1)
        
        
        return {"message": "Task validator registered successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.post("/clients/getClientModelsCreatedF")
def get_client_models_created_f():
    try:
        env_config = dotenv_values(".env")
        client_models_created_f = env_config.get("ClientModelsCreatedF")=="True"
        
        print("Client models created state:", client_models_created_f)
        w3 = get_w3()
        
        env_config = dotenv_values(".env")
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        client_model_ipfs_hashes = []
        ClientAddresses = []
        
        if client_models_created_f:
            deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
            
            current_GI = deployed_DINTaskCoordinatorContract.functions.getGI().call()
            
            lm_submissions = deployed_DINTaskCoordinatorContract.functions.getClientModels(current_GI).call()
            
            print("lm_submissions: ", lm_submissions)
            
            for i in range(len(lm_submissions)):
                client_model_ipfs_hash = lm_submissions[i][1]
                ClientAddresses.append(lm_submissions[i][0])
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
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        current_GI = deployed_DINTaskCoordinatorContract.functions.getGI().call()
        
        
        genesis_model_ipfs_hash = deployed_DINTaskCoordinatorContract.functions.getGenesisModelIpfsHash().call()
            
        client_model_ipfs_hashes = train_client_model_and_upload_to_ipfs(genesis_model_ipfs_hash, initial_model_ipfs_hash=None, dp_mode=dp_mode)
            
        for i, ipfs_model_hash in enumerate(client_model_ipfs_hashes):
            deployed_DINTaskCoordinatorContract.functions.submitLocalModel(ipfs_model_hash, current_GI).transact({
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

@router.post("/dindao/deployDinValidatorStake")
def deploy_dinvalidatorstake():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        DINValidatorStake_contract = get_DINValidatorStake_Instance()
        
        constructor_tx_hash  = DINValidatorStake_contract.constructor(env_config.get("DINToken_Contract_Address")).transact({
            "from": w3.eth.accounts[0],
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        constructor_receipt = w3.eth.wait_for_transaction_receipt(constructor_tx_hash)
        dinvalidatorstake_address = constructor_receipt.contractAddress
        
        set_key(".env", "DINValidatorStake_Contract_Address", dinvalidatorstake_address)
        
        print("DINValidatorStake contract deployed at:", dinvalidatorstake_address)
        
        return {"message": "DinValidatorStake contract deployed successfully",
                "status": "success",
                "dinvalidatorstake_address": dinvalidatorstake_address}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "dinvalidatorstake_address": None}

@router.post("/dindao/getDINDAOState")
def get_dindao_state():
    try:
        env_config = dotenv_values(".env")
        DINCoordinator_Contract_Address = env_config.get("DINCoordinator_Contract_Address")
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        w3 = get_w3()
        DINDAORepresentative_address = w3.eth.accounts[0]
        DINValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
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
                "DINCoordinator_Eth_balance": DINCoordinator_Eth_balance,
                "DINValidatorStake_address": DINValidatorStake_Contract_Address}
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
        unset_key(".env", "DINValidatorStake_Contract_Address")
        
        
        
        
        return {"message": "ALL Reset successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.get("/test")
def test():
    return {"message": "Router is working!"}