from fastapi import APIRouter, Depends
from services.blockchain_services import get_w3
from services.DAO_services import get_DINCoordinator_Instance, get_DINtokenContract_Instance, get_DINValidatorStake_Instance
from dotenv import load_dotenv, set_key, unset_key, dotenv_values

router = APIRouter(prefix="/dindao", tags=["DIN DAO"])

        
@router.post("/deployDINCoordinator")
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

@router.post("/deployDinValidatorStake")
def deploy_dinvalidatorstake():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        
        dincoordinator_address = env_config.get("DINCoordinator_Contract_Address")
        dintoken_address = env_config.get("DINToken_Contract_Address")
        
        DINValidatorStake_contract = get_DINValidatorStake_Instance()
        
        constructor_tx_hash  = DINValidatorStake_contract.constructor(dintoken_address, dincoordinator_address).transact({
            "from": w3.eth.accounts[0],
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        constructor_receipt = w3.eth.wait_for_transaction_receipt(constructor_tx_hash)
        dinvalidatorstake_address = constructor_receipt.contractAddress
        
        set_key(".env", "DINValidatorStake_Contract_Address", dinvalidatorstake_address)
        
        
        
        deployed_dincoordinator = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_address)
        
        tx_hash = deployed_dincoordinator.functions.add_dinvalidatorStakeContract(dinvalidatorstake_address).transact({
            "from": w3.eth.accounts[0],
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        if tx_hash is not None:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print("DinValidatorStake contract added to DINCoordinator contract successfully")
                set_key(".env", "DINCoordinator_DINValidatorStake_Contract_Address", dinvalidatorstake_address)
            else:
                print("Failed to add DinValidatorStake contract to DINCoordinator contract")
        
        
        print("DINValidatorStake contract deployed at:", dinvalidatorstake_address)
        
        return {"message": "DinValidatorStake contract deployed successfully",
                "status": "success",
                "dinvalidatorstake_address": dinvalidatorstake_address}
    except Exception as e:
        return {"message": str(e),
                "status": "error",
                "dinvalidatorstake_address": None}


@router.post("/addDINTaskCoordinatorAsSlasher")
def add_dintaskcoordinator_as_slasher():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        dincoordinator_address = env_config.get("DINCoordinator_Contract_Address")
        
        deployed_dincoordinator = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_address)
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        tx_hash = deployed_dincoordinator.functions.add_slasher_contract(DINTaskCoordinator_Contract_Address).transact({
            "from": w3.eth.accounts[0],
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        if tx_hash is not None:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print("DINTaskCoordinator added as Slasher to DINCoordinator contract successfully")
                set_key(".env", "DINTaskCoordinatorISslasher", "True")
            else:
                print("Failed to add DINTaskCoordinator as Slasher to DINCoordinator contract")
        
        return {"message": "DINTaskCoordinator added as Slasher to DINCoordinator contract successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}


@router.post("/addDINTaskAuditorAsSlasher")
def add_dintaskauditor_as_slasher():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        dincoordinator_address = env_config.get("DINCoordinator_Contract_Address")
        
        deployed_dincoordinator = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_address)
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        tx_hash = deployed_dincoordinator.functions.add_slasher_contract(DINTaskAuditor_Contract_Address).transact({
            "from": w3.eth.accounts[0],
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
        })
        
        if tx_hash is not None:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print("DINTaskAuditor added as Slasher to DINCoordinator contract successfully")
                set_key(".env", "DINTaskAuditorISslasher", "True")
            else:
                print("Failed to add DINTaskAuditor as Slasher to DINCoordinator contract")
        
        return {"message": "DINTaskAuditor added as Slasher to DINCoordinator contract successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}


@router.post("/getDINDAOState")
def get_dindao_state():
    try:
        env_config = dotenv_values(".env")
        DINCoordinator_Contract_Address = env_config.get("DINCoordinator_Contract_Address")
        DINToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        w3 = get_w3()
        DINDAORepresentative_address = w3.eth.accounts[0]
        DINValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        DINTaskCoordinatorISslasher = env_config.get("DINTaskCoordinatorISslasher")
        DINTaskAuditorISslasher = env_config.get("DINTaskAuditorISslasher")
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        print("DINTaskCoordinatorISslasher", DINTaskCoordinatorISslasher)
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
                "DINValidatorStake_address": DINValidatorStake_Contract_Address,
                "DINTaskCoordinator_address": DINTaskCoordinator_Contract_Address,
                "DINTaskCoordinatorISslasher": DINTaskCoordinatorISslasher=="True",
                "DINTaskAuditor_address": DINTaskAuditor_Contract_Address,
                "DINTaskAuditorISslasher": DINTaskAuditorISslasher=="True"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}