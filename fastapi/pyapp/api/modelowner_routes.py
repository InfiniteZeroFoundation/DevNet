from fastapi import APIRouter, Depends
from pydantic import BaseModel
from dotenv import load_dotenv, set_key, unset_key, dotenv_values

import traceback; 
from services.blockchain_services import get_w3
from services.modelowner_services import create_audit_testDataCIDs, getscoreforGM
from services.model_architect import getGenesisModelIpfs, get_DINTaskCoordinator_Instance, get_DINTaskAuditor_Instance, GIstatestrToIndex, GIstateToStr
from services.DAO_services import get_DINCoordinator_Instance, get_DINtokenContract_Instance, get_DINValidatorStake_Instance
from services.tetherfoundation_services import get_TetherMock_Instance

from .schemas import Tier1Batch, Tier2Batch

router = APIRouter(prefix="/modelowner", tags=["Model Owner"])

MIN_STAKE = 1000000 
@router.post("/getModelOwnerState")
def get_modelowner_state():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        if model_owner_address is None:
            model_owner_address = w3.eth.accounts[1] 
            set_key(".env", "ModelOwner_Address", model_owner_address)
            
        TetherMock_Contract_Address = env_config.get("TetherMock_Contract_Address")  
        
        DinCoordinator_Contract_Address = env_config.get("DINCoordinator_Contract_Address")
        
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        IS_GenesisModelCreated = env_config.get("IS_GenesisModelCreated")
        
        model_hash = env_config.get("GenesisModelIpfsHash")
        
        client_models_created_f = env_config.get("ClientModelsCreatedF")
        
        model_owner_dintoken_balance = 0
        dintaskauditor_dintoken_balance = 0
        
        model_owner_usdt_balance = 0
        dintaskauditor_usdt_balance = 0
        
        registered_validators = []
        registered_auditors = []
        audiors_batch_test_cids = []
        TestDataCID_assigned_F = False
            
        
        if DINToken_Contract_Address is not None:
            deployed_DINTokenContract = get_DINtokenContract_Instance(dintoken_address=DINToken_Contract_Address)
            model_owner_dintoken_balance = deployed_DINTokenContract.functions.balanceOf(model_owner_address).call()
            
            if DINTaskAuditor_Contract_Address is not None:
                dintaskauditor_dintoken_balance = deployed_DINTokenContract.functions.balanceOf(DINTaskAuditor_Contract_Address).call()
            
        if TetherMock_Contract_Address is not None:
            deployed_TetherMockContract = get_TetherMock_Instance(tethermock_address=TetherMock_Contract_Address)
            
            tethermock_contract_decimals = deployed_TetherMockContract.functions.decimals().call()
            
            model_owner_usdt_balance = deployed_TetherMockContract.functions.balanceOf(model_owner_address).call() / (10 ** tethermock_contract_decimals)
            
            if DINTaskAuditor_Contract_Address is not None:
                dintaskauditor_usdt_balance = deployed_TetherMockContract.functions.balanceOf(DINTaskAuditor_Contract_Address).call() / (10 ** tethermock_contract_decimals)
            
                print("dintaskauditor_usdt_balance", dintaskauditor_usdt_balance)
        
        
        if DINTaskCoordinator_Contract_Address is not None and DINTaskAuditor_Contract_Address is not None:
            
            deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
            
            deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
            
            curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
            
            curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
            
            if curr_GIstate >= GIstatestrToIndex("DINauditorRegistrationStarted"):
                registered_auditors = deployed_DINTaskAuditorContract.functions.getDINtaskAuditors(curr_GI).call()
                
            if curr_GIstate >= GIstatestrToIndex("DINvalidatorRegistrationStarted"):
                registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
                
            TestDataCID_assigned_F = deployed_DINTaskAuditorContract.functions.Is_testdataCIDs_Assigned(curr_GI).call()
            
            if curr_GIstate >= GIstatestrToIndex("AuditorsBatchesCreated"):
    
                audtor_batch_count = deployed_DINTaskAuditorContract.functions.AuditorsBatchCount(curr_GI).call()
                
                
                for i in range(audtor_batch_count):
                    
                    batch_id, auditors, model_indexes, test_cid = deployed_DINTaskAuditorContract.functions.getAuditorsBatch(curr_GI, i).call()
                    if test_cid:
                        audiors_batch_test_cids.append(test_cid)
                
        
        
        return {"message": "Model Owner State fetched successfully",
                "status": "success",
                "model_owner_address": model_owner_address,
                "mock_tether_address": TetherMock_Contract_Address,
                "dintaskcoordinator_address": DINTaskCoordinator_Contract_Address,
                "dintaskauditor_address": DINTaskAuditor_Contract_Address,
                
                "model_owner_eth_balance": w3.from_wei(w3.eth.get_balance(model_owner_address), 'ether'),
                
                "model_owner_dintoken_balance": model_owner_dintoken_balance,
                
                "model_owner_usdt_balance": model_owner_usdt_balance,
                "dintaskauditor_usdt_balance": dintaskauditor_usdt_balance,
                
                
                "registered_validators": registered_validators,
                "registered_auditors": registered_auditors,
                
                "IS_GenesisModelCreated": IS_GenesisModelCreated,
                "model_ipfs_hash": model_hash,
                
                "client_models_created_f": client_models_created_f,
                "TestDataCID_assigned_F": TestDataCID_assigned_F,
                "audiors_batch_test_cids":audiors_batch_test_cids 
                
                }
    except Exception as e:
        
        return {"message": "Error fetching Model Owner State " + str(e),
                "status": "error"}

@router.post("/buyUSDT")
def buy_usdt():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        model_owner_address = env_config.get("ModelOwner_Address")

        print("model_owner_address", model_owner_address)
        TetherMock_Contract_Address = env_config.get("TetherMock_Contract_Address")    
        
        if TetherMock_Contract_Address is None:
            model_owner_usdt_balance = 0
        else:
            deployed_TetherMockContract = get_TetherMock_Instance(tethermock_address=TetherMock_Contract_Address)
            
            TetherFoundationAddress = w3.eth.accounts[2+9+12+1]
            
            
            # 1. Transfer 1 ETH from model owner to Tether Foundation
            tx_hash = w3.eth.send_transaction({
                "from": model_owner_address,
                "to": TetherFoundationAddress,
                "value": w3.to_wei(1, "ether"),
            })
            
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            # Build and send the USDT transfer transaction
            usdt_tx = deployed_TetherMockContract.functions.transfer(
                model_owner_address,
                3000 * (10 ** 6)  # Assuming USDT has 6 decimals
            ).transact({"from": TetherFoundationAddress})
            
            receipt = w3.eth.wait_for_transaction_receipt(usdt_tx)
            
            model_owner_usdt_balance = deployed_TetherMockContract.functions.balanceOf(model_owner_address).call()
        
            tethermock_contract_decimals = deployed_TetherMockContract.functions.decimals().call()
            
            model_owner_usdt_balance = model_owner_usdt_balance / (10 ** tethermock_contract_decimals)
           
           
            
        return {"message": "DIN tokens deposited and minted successfully",
                "status": "success",
                "model_owner_eth_balance": w3.from_wei(w3.eth.get_balance(model_owner_address), 'ether'),
                "model_owner_usdt_balance": model_owner_usdt_balance}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

     
@router.post("/deployDINTaskCoordinator")
def deploy_dintaskcoordinator():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        model_owner_address = env_config.get("ModelOwner_Address")
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        DinValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        
        DINTaskCoordinator_contract = get_DINTaskCoordinator_Instance()
        constructor_tx_hash  = DINTaskCoordinator_contract.constructor(DinValidatorStake_Contract_Address).transact({
            "from": model_owner_address,
            "gas": int(2.5*3000000),
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        constructor_receipt = w3.eth.wait_for_transaction_receipt(constructor_tx_hash)
        dintaskcoordinator_contract_address = constructor_receipt.contractAddress
        
        print("DINTaskCoordinator contract deployed at:", dintaskcoordinator_contract_address)
        
        set_key(".env", "DINTaskCoordinator_Contract_Address", dintaskcoordinator_contract_address)
        
        DINToken_contract = get_DINtokenContract_Instance(dintoken_address=DINToken_Contract_Address)
        
        
        
        
        return {"message": "DINTaskCoordinator contract deployed successfully",
                "status": "success",
                "dintaskcoordinator_contract_address": dintaskcoordinator_contract_address,

                }
        
    except Exception as e:
        print("Error deploying DINTaskCoordinator:", e)
        return {"message": str(e),
                "status": "error"}
        
@router.post("/deployDINtaskAuditor")
def deploy_dintaskauditor():
    try:
        
        env_config = dotenv_values(".env")
        w3 = get_w3()
        model_owner_address = env_config.get("ModelOwner_Address")
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        DinValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        TetherMock_Contract_Address = env_config.get("TetherMock_Contract_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        DINTaskAuditor_contract = get_DINTaskAuditor_Instance()
        
        constructor_tx_hash  = DINTaskAuditor_contract.constructor(TetherMock_Contract_Address, DinValidatorStake_Contract_Address, DINTaskCoordinator_Contract_Address).transact({
            "from": model_owner_address,
            "gas": int(2.5*3000000),
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        constructor_receipt = w3.eth.wait_for_transaction_receipt(constructor_tx_hash)
        dintaskauditor_contract_address = constructor_receipt.contractAddress
        
        print("DINTaskAuditor contract deployed at:", dintaskauditor_contract_address)
        
        set_key(".env", "DINTaskAuditor_Contract_Address", dintaskauditor_contract_address)
        
        dintaskcoordinator_contract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        dintaskcoordinator_contract.functions.setDINTaskAuditorContract(dintaskauditor_contract_address).transact({
            "from": model_owner_address,
            "gas": int(2.5*3000000),
            "gasPrice": w3.to_wei("5", "gwei"),
            })
        
        print("DINTaskAuditor contract set in DINTaskCoordinator")
        
        DINToken_contract = get_DINtokenContract_Instance(dintoken_address=DINToken_Contract_Address)
        
        dintaskauditorDintokenBalance = DINToken_contract.functions.balanceOf(dintaskauditor_contract_address).call()
        
        return {"message": "DINTaskAuditor contract deployed successfully",
                "status": "success",
                "dintaskauditor_contract_address": dintaskauditor_contract_address,
                "dintaskauditor_dintoken_balance": dintaskauditorDintokenBalance, 
                }
        
        
        
    except Exception as e:
        print("Error deploying DINTaskAuditor:", e)
        return {"message": str(e),
                "status": "error"}




@router.post("/depositRewardInDINtaskAuditor")
def deposit_reward_in_dintaskauditor():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        model_owner_address = env_config.get("ModelOwner_Address")
        dintoken_contract_address = env_config.get("DINToken_Contract_Address")
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        TetherMock_Contract_Address = env_config.get("TetherMock_Contract_Address")
        deployed_dintoken_contract = get_DINtokenContract_Instance(dintoken_address=dintoken_contract_address)
        
        
        amount = 1000
        
        deployed_TetherMockContract = get_TetherMock_Instance(tethermock_address=TetherMock_Contract_Address)
        
        DECIMALS = deployed_TetherMockContract.functions.decimals().call()
        
        amount = amount * (10 ** DECIMALS)
        
        
        tx_hash = deployed_TetherMockContract.functions.approve(DINTaskAuditor_Contract_Address, amount).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei")
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        tx_hash = deployed_DINTaskAuditorContract.functions.depositReward(amount).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        
        if TetherMock_Contract_Address is None:
            model_owner_usdt_balance = 0
            dintaskauditor_usdt_balance = 0
        else:
            deployed_TetherMockContract = get_TetherMock_Instance(tethermock_address=TetherMock_Contract_Address)
            model_owner_usdt_balance = deployed_TetherMockContract.functions.balanceOf(model_owner_address).call()
            
            tethermock_contract_decimals = deployed_TetherMockContract.functions.decimals().call()
            
            model_owner_usdt_balance = model_owner_usdt_balance / (10 ** tethermock_contract_decimals)
            
            if DINTaskAuditor_Contract_Address is not None:
                dintaskauditor_usdt_balance = deployed_TetherMockContract.functions.balanceOf(DINTaskAuditor_Contract_Address).call()
            else:
                dintaskauditor_usdt_balance = 0
            
            dintaskauditor_usdt_balance = dintaskauditor_usdt_balance / (10 ** tethermock_contract_decimals)
            
        return {"message": "DIN reward deposited successfully in DINtaskAuditor",
                "status": "success",
                "model_owner_usdt_balance": model_owner_usdt_balance,
                "dintaskauditor_usdt_balance": dintaskauditor_usdt_balance,
                "model_owner_eth_balance": w3.from_wei(w3.eth.get_balance(model_owner_address), 'ether')}
    except Exception as e:
        print("Error depositing reward:", e)
        return {"message": str(e),
                "status": "error"}
        

@router.post("/setDINTaskCoordinatorAsSlasher")
def set_dintaskcoordinator_as_slasher():
    try:
        env_config = dotenv_values(".env")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.setDINTaskCoordinatorAsSlasher().transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        set_key(".env", "DINTaskCoordinatorISslasher", "True")
        return {"message": "DINTaskCoordinator set as slasher successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.post("/setDINTaskAuditorAsSlasher")
def set_dintaskauditor_as_slasher():
    try:
        env_config = dotenv_values(".env")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.setDINTaskAuditorAsSlasher().transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        set_key(".env", "DINTaskAuditorISslasher", "True")
        return {"message": "DINTaskAuditor set as slasher successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.post("/createGenesisModel")
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
    
        
        accuracy = getscoreforGM(0, model_hash)
        
        print("Genesis model accuracy:", accuracy)
        
        tx = deployed_DINTaskCoordinatorContract.functions.setTier2Score(0, int(accuracy)).transact({
            "from": model_owner_account,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        w3.eth.wait_for_transaction_receipt(tx)
        
        
        return {"message": "Genesis model created & uploaded to IPFS successfully, logged in smart contract",
                "status": "success",
                "IS_GenesisModelCreated": True,
                "model_ipfs_hash": model_hash,
                "accuracy": accuracy}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "IS_GenesisModelCreated": False,
                "model_ipfs_hash": None}


@router.post("/startGI")
def start_GI():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        if curr_GI == 0:
            gmcid = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()
        else:
            batch_id, _, _, gmcid = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI,0).call()
        
        accuracy = getscoreforGM(curr_GI, gmcid)
        print("Current GI:", curr_GI, "GM Accuracy:", accuracy)
        tx_hash = deployed_DINTaskCoordinatorContract.functions.startGI(curr_GI+1, int(accuracy-5)).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        unset_key(".env", "ClientModelsCreatedF")
        
        return {"message": "GI started successfully",
                "status": "success",
                "passScore": int(accuracy)}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.post("/startDINvalidatorRegistration")
def start_DINvalidatorRegistration():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.startDINvalidatorRegistration(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print("DIN Validators Registration started successfully")
        return {"message": "DIN Validators Registration started successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.post("/closeDINvalidatorRegistration")
def close_DINvalidatorRegistration():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.closeDINvalidatorRegistration(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print("DIN Validators Registration closed successfully")
        return {"message": "DIN Validators Registration closed successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.post("/startDINauditorRegistration")
def start_DINauditorRegistration():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.startDINauditorRegistration(curr_GI).transact({
            "from": model_owner_address,
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print("DIN Auditors Registration started successfully")
        return {"message": "DIN Auditors Registration started successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.post("/closeDINauditorRegistration")
def close_DINauditorRegistration():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.closeDINauditorRegistration(curr_GI).transact({
            "from": model_owner_address,
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print("DIN Auditors Registration closed successfully")
        return {"message": "DIN Auditors Registration closed successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.post("/startLMsubmissions")
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

@router.post("/closeLMsubmissions")
def close_LMsubmissions():
    try:
        print("in closeLMsubmissions")
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GI < 1 or GIstate != GIstatestrToIndex("LMSstarted"):
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


@router.post("/getClientModels")
def get_modelowner_client_models():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate < GIstatestrToIndex("LMSclosed"): 
            raise Exception("Can not get client models at this time")
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        raw_lm_submissions = deployed_DINTaskAuditorContract.functions.getClientModels(curr_GI).call()
        
        
        lm_submissions = []
        
        if GIstatestrToIndex("LMSclosed") <= curr_GIstate:

            for idx, sub in enumerate(raw_lm_submissions):
                client, model_cid, submitted_at, eligible, evaluated, approved, final_avg = sub
                lm_submissions.append({
                    "index": idx,
                    "client": client,
                    "modelCID": model_cid or "None",
                    "submittedAt": submitted_at,
                    "eligible": eligible,
                    "evaluated": evaluated,
                    "approved": approved,
                    "finalAvgScore": int(final_avg)
                })
            
        if GIstatestrToIndex("AuditorsBatchesCreated") <= curr_GIstate:    
            raw_audit_batches = []
            processed_audit_batches = []
            model_to_batch = {}
            audtor_batch_count = deployed_DINTaskAuditorContract.functions.AuditorsBatchCount(curr_GI).call()
            
            for batch_id in range(audtor_batch_count):
                raw_audit_batches.append(deployed_DINTaskAuditorContract.functions.getAuditorsBatch(curr_GI, batch_id).call())
            
            for batch in raw_audit_batches:
                batch_id, auditors, model_indexes, test_cid = batch
                processed_audit_batches.append({"batch_id": batch_id, "auditors": auditors, "model_indexes": model_indexes, "test_cid": test_cid or "None"})
            
                for m_idx in model_indexes:
                    model_to_batch[m_idx] = {
                        "batch_id": batch_id,
                        "test_cid": test_cid or "None"
                    }
                    
            # Enrich submissions with vote data
            model_audit_data = []
            
            for submission in lm_submissions:
                m_idx = submission["index"]
                batch_info = model_to_batch.get(m_idx)

                votes = []
                if batch_info:
                    batch_id = batch_info["batch_id"]
                    auditors_in_batch = next(
                        (b["auditors"] for b in processed_audit_batches if b["batch_id"] == batch_id),
                        []
                    )

                    for auditor in auditors_in_batch:
                        try:
                            
                            score = deployed_DINTaskAuditorContract.functions.auditScores(curr_GI, batch_id, auditor, m_idx).call()
                            eligible = deployed_DINTaskAuditorContract.functions.LMeligibleVote(curr_GI, batch_id, auditor, m_idx).call()
                            has_voted = deployed_DINTaskAuditorContract.functions.hasAuditedLM(curr_GI, batch_id, auditor, m_idx).call()
                        except:
                            score, eligible, has_voted = 0, False, False

                        votes.append({
                            "auditor": auditor,
                            "auditorShort": f"{auditor[:6]}...{auditor[-4:]}",
                            "hasVoted": has_voted,
                            "score": int(score) if has_voted else None,
                            "eligible": eligible if has_voted else None
                        })

                model_audit_data.append({
                    "modelIndex": m_idx,
                    "batchInfo": batch_info,
                    "votes": votes
                })
                
                    
                
                
            
        
        return {"message": "LM submissions collected successfully",
                "status": "success",
                "lm_submissions": lm_submissions,
                "model_audit_data":model_audit_data}
    except Exception as e:
        print("Error collecting LM submissions:", e)
        return {"message": str(e),
                "status": "error",
                "lm_submissions":[],
                "model_audit_data":[]
                }
        
@router.post("/createAuditorsBatches")
def createAuditorsBatches():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        

        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        

                
        if curr_GI < 0 or GIstate!=GIstatestrToIndex("LMSclosed"):
            raise Exception("Can not create auditors batches at this time")
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.createAuditorsBatches(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
        
        return {"message": "Auditors batches created successfully",
                "status": "success"}
    except Exception as e:
        print("Error creating auditors batches:", e)
        return {"message": str(e),
                "status": "error"}
        
    
@router.post("/createTestSubDatasetsForAuditorsBatches")
def createTestSubDatasetsForAuditorsBatches():
    try:
       
        
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GI < 1 or GIstate!=GIstatestrToIndex("AuditorsBatchesCreated"):
            raise Exception("Can not create test sub datasets for auditors batches at this time")
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        audtor_batch_count = deployed_DINTaskAuditorContract.functions.AuditorsBatchCount(curr_GI).call()
        
        #*****----------- fixed for demo --------------***************
        
        #audit_testDataCIDs = create_audit_testDataCIDs(audtor_batch_count, curr_GI)
        
        audit_testDataCIDs = ['QmYHc4Y6pmMKFohYDJXkFCCrLAQBUhwGuD6ebGZUxi34ea', 'QmSvTuP4XmcNnaYAqYkv6ewUKU7v2PCAnnLB9DqE7MTrAg', 'QmSdiTciKYBTxHKntjY3Pko8szD5D1nXVLU2mVWrsZhWdE', 'QmcLCGEz9FDHti6c2PPUqAh8rzGpQSwFAZi4QifcYkQB49', 'QmRZydYdpcHTpSSNy7MsX2K29KuUwEsoRxDkT9NEHqu6CQ', 'QmfBeoeqxb3SecGj4qUWcYYZ5AtCsUPyBn8deUj4RQofxw']
        
        

        print("audit_testDataCIDs: ", audit_testDataCIDs[0:audtor_batch_count])
        
        #*****----------- fixed for demo --------------***************
        
        for batch_id in range(audtor_batch_count):
            tx_hash = deployed_DINTaskAuditorContract.functions.assignAuditTestDataset(curr_GI, batch_id, audit_testDataCIDs[batch_id]).transact({
                "from": model_owner_address,
                "gas": 3000000,
                "gasPrice": w3.to_wei("5", "gwei"),
            })
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        deployed_DINTaskCoordinatorContract.functions.setTestDataAssignedFlag(curr_GI, True).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        set_key(".env", "TestDataset_CIDs_Assigned", "True")
            
        return {"message": "Test sub datasets created successfully",
                "status": "success"}
    except Exception as e:
        traceback.print_exc();
        print("Error creating test sub datasets for auditors batches:", e)
        return {"message": str(e),
                "status": "error"}

@router.post("/fetchAuditBatches")
def fetchAuditBatches():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        
        if GIstate < GIstatestrToIndex("AuditorsBatchesCreated"):
            raise Exception("Can not fetch audit batches at this time")
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        audtor_batch_count = deployed_DINTaskAuditorContract.functions.AuditorsBatchCount(curr_GI).call()
        
        raw_audit_batches = []
        
        processed_audit_batches = []
        
        
        
        for batch_id in range(audtor_batch_count):
            raw_audit_batches.append(deployed_DINTaskAuditorContract.functions.getAuditorsBatch(curr_GI, batch_id).call())
            
        for batch in raw_audit_batches:
            batch_id, auditors, model_indexes, test_cid = batch
            processed_audit_batches.append({"batch_id": batch_id, "auditors": auditors, "model_indexes": model_indexes, "test_cid": test_cid or "None"})
        
        return {"message": "Audit batches fetched successfully",
                "status": "success",
                "processed_audit_batches": processed_audit_batches}
    
    except Exception as e:
        print("Error fetching audit batches:", e)
        return {"message": str(e),
                "status": "error"}
       
@router.post("/startLMsubmissionsEvaluation")
def startLMsubmissionsEvaluation():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != GIstatestrToIndex("AuditorsBatchesCreated"):
            raise Exception("Can not start LM submissions evaluation at this time")
        
        deployed_DINTaskCoordinatorContract.functions.startLMsubmissionsEvaluation(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "LM submissions evaluation started successfully",
                "status": "success"}
        
    except Exception as e:
        print("Error starting LM submissions evaluation:", e)
        return {"message": str(e),
                "status": "error"}
        
    
@router.post("/closeLMsubmissionsEvaluation")
def closeLMsubmissionsEvaluation():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != GIstatestrToIndex("LMSevaluationStarted"):
            raise Exception("Can not close LM submissions evaluation at this time")
        
        deployed_DINTaskCoordinatorContract.functions.closeLMsubmissionsEvaluation(curr_GI).transact({
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

@router.post("/createTier1n2Batches")
def createTier1Batches():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != GIstatestrToIndex("LMSevaluationClosed"):
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

class BatchPayload(BaseModel):
    tier1_batches: list[Tier1Batch]
    tier2_batches: list[Tier2Batch]
    message: str
    status: str
    
@router.post("/getTier1n2Batches")
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
  
@router.post("/startT1Aggregation")
def start_T1Aggregation():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate < GIstatestrToIndex("T1nT2Bcreated"):
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
        
       
@router.post("/finalizeT1Aggregation")
def finalize_t1_aggregation():
    try:
        w3 = get_w3()
        
        env_config = dotenv_values(".env")
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        current_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        deployed_DINTaskCoordinatorContract.functions.finalizeT1Aggregation(current_GI).transact({
            "from": w3.eth.accounts[1],
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "T1 Aggregation finalized successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
     
@router.post("/startT2Aggregation")
def start_T2Aggregation():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate < GIstatestrToIndex("T1AggregationDone"):
            raise Exception("Can not start Tier 2 Aggregation at this time")
        
        deployed_DINTaskCoordinatorContract.functions.startT2Aggregation(curr_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "Tier 2 Aggregation started successfully",
                "status": "success"}
    except Exception as e:
        print("Error starting Tier 2 Aggregation:", e)
        return {"message": str(e),
                "status": "error"}

@router.post("/finalizeT2Aggregation")
def finalize_t2_aggregation():
    try:
        w3 = get_w3()
        
        env_config = dotenv_values(".env")
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        current_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        tx = deployed_DINTaskCoordinatorContract.functions.finalizeT2Aggregation(current_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        w3.eth.wait_for_transaction_receipt(tx)
        
        tier2_batch = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(current_GI, 0).call()
        
        finalCID = tier2_batch[3]
        
        accuracy = getscoreforGM(current_GI, finalCID)
        
        tx = deployed_DINTaskCoordinatorContract.functions.setTier2Score(current_GI, int(accuracy)).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        w3.eth.wait_for_transaction_receipt(tx)
        
        return {"message": "T2 Aggregation finalized successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
        
@router.post("/slashAuditors")
def slash_auditors():
    try:
        w3 = get_w3()
        
        env_config = dotenv_values(".env")
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        current_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        deployed_DINTaskCoordinatorContract.functions.slashAuditors(current_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "Auditors slashed successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        


@router.post("/slashValidators")
def slash_validators():
    try:
        w3 = get_w3()
        
        env_config = dotenv_values(".env")
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        current_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        deployed_DINTaskCoordinatorContract.functions.slashValidators(current_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "Validators slashed successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.post("/endGI")
def end_GI():
    try:
        w3 = get_w3()
        
        env_config = dotenv_values(".env")
        model_owner_address = env_config.get("ModelOwner_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        current_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        deployed_DINTaskCoordinatorContract.functions.endGI(current_GI).transact({
            "from": model_owner_address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        return {"message": "GI ended successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
