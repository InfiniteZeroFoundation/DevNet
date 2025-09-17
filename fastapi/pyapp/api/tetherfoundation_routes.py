from fastapi import APIRouter, Depends
from services.blockchain_services import get_w3
from dotenv import load_dotenv, set_key, unset_key, dotenv_values

from services.tetherfoundation_services import get_TetherMock_Instance

router = APIRouter(prefix="/tetherfoundation", tags=["Tether Foundation"])



@router.get("/getTetherFoundationState")
def get_tetherfoundation_state():
    try:
        w3 = get_w3()
        
        env_config = dotenv_values(".env")
        TetherMock_Contract_Address = env_config.get("TetherMock_Contract_Address")
        
        TetherFoundationAddress = w3.eth.accounts[2+9+12+1]
        
        TetherFoundation_Eth_balance = w3.from_wei(w3.eth.get_balance(TetherFoundationAddress), 'ether')
        
        tethermock_contract_supply_in_usdt  = 0
        tethermock_contract_balance_in_usdt = 0
        
        if TetherMock_Contract_Address is not None:
            deployed_TetherMockContract = get_TetherMock_Instance(tethermock_address=TetherMock_Contract_Address)
            
            tethermock_contract_supply = deployed_TetherMockContract.functions.totalSupply().call()
            
            tethermock_contract_decimals = deployed_TetherMockContract.functions.decimals().call()
            
            # Convert supply to float (with decimals)
            tethermock_contract_supply_in_usdt = tethermock_contract_supply / (10 ** tethermock_contract_decimals)
            
            tethermock_contract_balance_in_usdt = deployed_TetherMockContract.functions.balanceOf(TetherFoundationAddress).call()
            
            tethermock_contract_balance_in_usdt = tethermock_contract_balance_in_usdt / (10 ** tethermock_contract_decimals)
        
        return {"message": "Tether Foundation state fetched successfully",
                "status": "success",
                "tetherfoundation_address": TetherFoundationAddress,
                "tetherfoundation_eth_balance": TetherFoundation_Eth_balance,
                "tethermock_contract_address": TetherMock_Contract_Address,
                "tethermock_contract_supply": tethermock_contract_supply_in_usdt,
                "tethermock_contract_balance": tethermock_contract_balance_in_usdt}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        

@router.post("/deployTetherMockContract")
def deploy_tethermock_contract():
    try:
        w3 = get_w3()
           
        env_config = dotenv_values(".env")
        
        model_owner_address = env_config.get("ModelOwner_Address")
        
        if model_owner_address is None:
            model_owner_address = w3.eth.accounts[1] 
            set_key(".env", "ModelOwner_Address", model_owner_address)
      
     
        
        TetherMock_Contract_Address = env_config.get("TetherMock_Contract_Address")
        
        TetherFoundationAddress = w3.eth.accounts[2+9+12+1]
        
        if TetherMock_Contract_Address is not None:
            return {"message": "Tether Mock Contract already deployed",
                    "status": "success",
                    "tethermock_contract_address": TetherMock_Contract_Address}
        
        else:
            
            TetherMock_contract = get_TetherMock_Instance()
            
            constructor_tx_hash  = TetherMock_contract.constructor(1000_000_000_000_000).transact({
                "from": TetherFoundationAddress,
                "gas": 3000000,
                "gasPrice": w3.to_wei("5", "gwei"),
            })
            
            constructor_receipt = w3.eth.wait_for_transaction_receipt(constructor_tx_hash)
            tethermock_contract_address = constructor_receipt.contractAddress
            
            set_key(".env", "TetherMock_Contract_Address", tethermock_contract_address)
            
            deployed_TetherMockContract = get_TetherMock_Instance(tethermock_address=tethermock_contract_address)
            
            tethermock_contract_supply = deployed_TetherMockContract.functions.totalSupply().call()
            
            tethermock_contract_decimals = deployed_TetherMockContract.functions.decimals().call()
            
            # Convert supply to float (with decimals)
            tethermock_contract_supply_in_usdt = tethermock_contract_supply / (10 ** tethermock_contract_decimals)
            
            tethermock_contract_balance_in_usdt = deployed_TetherMockContract.functions.balanceOf(TetherFoundationAddress).call()
            
            tethermock_contract_balance_in_usdt = tethermock_contract_balance_in_usdt / (10 ** tethermock_contract_decimals)
            
            return {"message": "Tether Mock Contract deployed successfully",
                    "status": "success",
                    "tethermock_contract_address": tethermock_contract_address,
                    "tethermock_contract_supply": tethermock_contract_supply_in_usdt,
                    "tethermock_contract_balance": tethermock_contract_balance_in_usdt}
            
    except Exception as e:
        return {"message": str(e),
                "status": "error"}   
        