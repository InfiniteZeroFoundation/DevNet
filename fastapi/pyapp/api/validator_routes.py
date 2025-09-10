from fastapi import APIRouter, Depends
from pydantic import BaseModel
from dotenv import load_dotenv, set_key, unset_key, dotenv_values
import time

from services.blockchain_services import get_w3
from services.model_architect import get_DINTaskCoordinator_Instance, get_DINTaskAuditor_Instance, GIstatestrToIndex, GIstateToStr
from services.DAO_services import get_DINtokenContract_Instance, get_DINValidatorStake_Instance, get_DINCoordinator_Instance

from services.ipfs_service import generate_fake_cid_v0

from services.validators_services import get_validator_aggregated_cid

from .schemas import Tier1Batch, Tier2Batch

router = APIRouter(prefix="/validators", tags=["Validators"])

MIN_STAKE = 1000000 
    
@router.post("/getValidatorsState")
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
            
            
            if curr_GI > 0 and GIstate >= 6 : #DINvalidatorRegistrationStarted
                registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
                print("registered_validators: ", registered_validators)
                
            if curr_GI > 0 and GIstate >= 14: # T1nT2Bcreated
                t1_batches_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()
                print("t1_batches_count: ", t1_batches_count)
                
                t2_batches_count = 1
                
                for validator_address in registered_validators:
                    val_assigned_t1_batches = []
                    validator_cids_t1 = []
                    validator_cids_t2 = []
                    for i in range(t1_batches_count):
                        (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
                        if validator_address in val:
                            val_assigned_t1_batches.append(Tier1Batch(batch_id=bid, validators=val, model_indexes=idxs, finalized=fin, final_cid=cid))
                            
                        has_submitted_t1 = deployed_DINTaskCoordinatorContract.functions.t1Submitted(curr_GI, i, validator_address).call()
                        
                        if has_submitted_t1:
                            cid = deployed_DINTaskCoordinatorContract.functions.t1SubmissionCID(curr_GI, i, validator_address).call()
                            validator_cids_t1.append(cid)
                        else:
                            validator_cids_t1.append(None)
                            
                    val_assigned_t2_batches = []  
                    for i in range(t2_batches_count):
                        (bid, val, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, i).call()
                        if validator_address in val:
                            val_assigned_t2_batches.append(Tier2Batch(batch_id=bid, validators=val, finalized=fin, final_cid=cid))
                                
                            has_submitted_t2 = deployed_DINTaskCoordinatorContract.functions.t2Submitted(curr_GI, i, validator_address).call()
                        
                            if has_submitted_t2:
                                cid = deployed_DINTaskCoordinatorContract.functions.t2SubmissionCID(curr_GI, i, validator_address).call()
                                validator_cids_t2.append(cid)
                            else:
                                validator_cids_t2.append(None)
                                
                                
                    all_reg_val_assigned_t1_batches.append(val_assigned_t1_batches)
                    all_reg_val_assigned_t2_batches.append(val_assigned_t2_batches)
                    all_res_val_t1.append(validator_cids_t1)
                    all_res_val_t2.append(validator_cids_t2)
                    
        
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
                ValidatorDinStakedTokens.append(validator_din_staked_tokens)
            else:
                ValidatorDinStakedTokens.append(0)
                
        
        print("all_res_val_t1: ", all_res_val_t1)
        
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
        
        
@router.post("/buyDINTokens")
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

@router.post("/buyDINTokensSingle")
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
        
@router.post("/stakeDINTokens")
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
            
        
@router.post("/stakeDINTokensSingle")
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
        
@router.post("/registerTaskValidators")
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
    
        
        if GIstateToStr(curr_GIstate) != "DINvalidatorRegistrationStarted":
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

@router.post("/registerTaskValidatorSingle")
def register_task_validator_single(request: ValidatorAddressRequest):
    try:
        
        validator_address = request.validator_address
        env_config = dotenv_values(".env")
        w3 = get_w3()
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        DINValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DINValidatorStake_Contract_Address)
        
        
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if GIstateToStr(curr_GIstate) != "DINvalidatorRegistrationStarted":
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

@router.post("/aggregateHonestlyT1")
def aggregateHonestlyT1(request: ValidatorAddressRequest):
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        validator_address = request.validator_address
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 16: #T1AggregationStarted
            raise Exception("Can not submit aggregated T1 CiD honestly at this time")
        
        registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
       
        if validator_address not in registered_validators:
            raise Exception("Validator is not registered")
        
        t1_batches_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()
        
        val_assigned_t1_batches = []
        for i in range(t1_batches_count):
            (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
            if validator_address in val:
                val_assigned_t1_batches.append(Tier1Batch(batch_id=bid, validators=val, model_indexes=idxs, finalized=fin, final_cid=cid))
        
        validator_batch = val_assigned_t1_batches[0]
        model_indexes = validator_batch.model_indexes
        
        model_cids = []
        for i in range(len(model_indexes)):
            (client, modelCID, submittedAt, eligible,evaluated, approved, finalAvgScore) = deployed_DINTaskAuditorContract.functions.lmSubmissions(curr_GI, model_indexes[i]).call()
            model_cids.append(modelCID)
            
        genesis_model_ipfs_hash = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()
        
        validator_aggregated_cid = get_validator_aggregated_cid(curr_GI, validator_address, model_cids, genesis_model_ipfs_hash)
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.submitT1Aggregation(curr_GI, validator_batch.batch_id, validator_aggregated_cid).transact({"from": validator_address})
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        
        print("model cids: ", model_cids)
        time.sleep(0.1)
        
        print("Validator address:", validator_address)
        print("Validator assigned t1 batches:", val_assigned_t1_batches)  
        print("Validator aggregated CID: ", validator_aggregated_cid)
        return {"message": "Validator aggregated CID honestly successfully",
                "status": "success"}
    
    except Exception as e:
        return {"message": str(e),
                "status": "error"}


@router.post("/aggregateMaliciouslyT1")
def aggregateMaliciouslyT1(request: ValidatorAddressRequest):
    try:
        env_config = dotenv_values(".env")
        validator_address = request.validator_address
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        w3 = get_w3()
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 16: #T1AggregationStarted
            raise Exception("Can not submit aggregated T1 CID maliciously at this time")
        
        registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
       
        if validator_address not in registered_validators:
            raise Exception("Validator is not registered")
        
        t1_batches_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()
        
        val_assigned_t1_batches = []
        for i in range(t1_batches_count):
            (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
            if validator_address in val:
                val_assigned_t1_batches.append(Tier1Batch(batch_id=bid, validators=val, model_indexes=idxs, finalized=fin, final_cid=cid))
        
        batch_id = val_assigned_t1_batches[0].batch_id
        
        cid = generate_fake_cid_v0()
        print("fake cid: ", cid)
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.submitT1Aggregation(curr_GI, batch_id, cid).transact({"from": validator_address})
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        time.sleep(0.1)
         
        print("Validator address:", validator_address)
        print("Validator assigned t1 batches:", val_assigned_t1_batches) 
        print("Validator CID: ", cid)
        
        return {"message": "Aggregated CID maliciously submitted successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.post("/aggregateHonestlyAllT1")
def aggregateHonestlyAllT1():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
       
        t1_batches_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()
       
        
        for validator_address in registered_validators:
            val_assigned_t1_batches = []
            for i in range(t1_batches_count):
                (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
                if validator_address in val:
                    val_assigned_t1_batches.append(Tier1Batch(batch_id=bid, validators=val, model_indexes=idxs, finalized=fin, final_cid=cid))
            
            if len(val_assigned_t1_batches) != 0:
            
                validator_batch = val_assigned_t1_batches[0]
                model_indexes = validator_batch.model_indexes
                
                model_cids = []
                for i in range(len(model_indexes)):
                    (client, modelCID, submittedAt, eligible,evaluated, approved, finalAvgScore) = deployed_DINTaskAuditorContract.functions.lmSubmissions(curr_GI, model_indexes[i]).call()
                    model_cids.append(modelCID)
                    
                genesis_model_ipfs_hash = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()
                
                validator_aggregated_cid = get_validator_aggregated_cid(curr_GI, validator_address, model_cids, genesis_model_ipfs_hash)
                
                tx_hash = deployed_DINTaskCoordinatorContract.functions.submitT1Aggregation(curr_GI, validator_batch.batch_id, validator_aggregated_cid).transact({"from": validator_address})
                
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                
            else:
                continue
                
        return {"message": "Aggregated honestly all T1 successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

        
@router.post("/aggregateHonestlyT2")
def aggregateHonestlyT2(request: ValidatorAddressRequest):
    try:
        env_config = dotenv_values(".env")
        validator_address = request.validator_address
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        w3 = get_w3()
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 18: #T2AggregationStarted
            raise Exception("Can not submit aggregated T2 CID honestly at this time")
        
        registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
       
        if validator_address not in registered_validators:
            raise Exception("Validator is not registered")
        
        t2_batches_count = 1
        
        val_assigned_t2_batches = []
        for i in range(t2_batches_count):
            (bid, val, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, i).call()
            if validator_address in val:
                val_assigned_t2_batches.append(Tier2Batch(batch_id=bid, validators=val, finalized=fin, final_cid=cid))
        
        batch_id = val_assigned_t2_batches[0].batch_id
        
        t1_batches = []
        
        t1_batches_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()
        
        for i in range(t1_batches_count):
            (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
            
            t1_batches.append(Tier1Batch(batch_id=bid, validators=val, model_indexes=idxs, finalized=fin, final_cid=cid))
        
        model_cids = []
        
        for i in range(len(t1_batches)):
            model_cids.append(t1_batches[i].final_cid)
        
        genesis_model_ipfs_hash = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()
        
        validator_aggregated_cid = get_validator_aggregated_cid(curr_GI, validator_address, model_cids, genesis_model_ipfs_hash)
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.submitT2Aggregation(curr_GI, batch_id, validator_aggregated_cid).transact({"from": validator_address})
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        time.sleep(0.1)
        
        print("Validator address:", validator_address)
        print("Validator assigned t2 batches:", val_assigned_t2_batches) 
        print("Validator aggregated CID: ", validator_aggregated_cid)
        
        return {"message": "Validator aggregated CID honestly submitted successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.post("/aggregateMaliciouslyT2")
def aggregateMaliciouslyT2(request: ValidatorAddressRequest):
    try:
        env_config = dotenv_values(".env")
        validator_address = request.validator_address
        
        w3 = get_w3()
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate != 18: #T2AggregationStarted
            raise Exception("Can not submit aggregated T2 CID maliciously at this time")
        
        registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
       
        if validator_address not in registered_validators:
            raise Exception("Validator is not registered")
        
        t2_batches_count = 1
        
        val_assigned_t2_batches = []
        for i in range(t2_batches_count):
            (bid, val, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, i).call()
            if validator_address in val:
                val_assigned_t2_batches.append(Tier2Batch(batch_id=bid, validators=val, finalized=fin, final_cid=cid))
        
        batch_id = val_assigned_t2_batches[0].batch_id
        
        cid = generate_fake_cid_v0()
        print("fake cid: ", cid)
        
        tx_hash = deployed_DINTaskCoordinatorContract.functions.submitT2Aggregation(curr_GI, batch_id, cid).transact({"from": validator_address})
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        time.sleep(0.1)
         
        print("Validator address:", validator_address)
        print("Validator assigned t2 batches:", val_assigned_t2_batches) 
        print("Validator CID: ", cid)
        
        return {"message": "Aggregated T2 CID maliciously submitted successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.post("/aggregateHonestlyAllT2")
def aggregateHonestlyAllT2():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        registered_validators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
        
        t2_batches_count = 1
        
        for validator_address in registered_validators:
            
            val_assigned_t2_batches = []
            for i in range(t2_batches_count):
                (bid, val, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, i).call()
                if validator_address in val:
                    val_assigned_t2_batches.append(Tier2Batch(batch_id=bid, validators=val, finalized=fin, final_cid=cid))
                    
            
            if len(val_assigned_t2_batches) != 0:
                
                batch_id = val_assigned_t2_batches[0].batch_id
                
                t1_batches = []
        
                t1_batches_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()
                
                for i in range(t1_batches_count):
                    (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
                    
                    t1_batches.append(Tier1Batch(batch_id=bid, validators=val, model_indexes=idxs, finalized=fin, final_cid=cid))
                    
                model_cids = []
        
                for i in range(len(t1_batches)):
                    model_cids.append(t1_batches[i].final_cid)
                    
                genesis_model_ipfs_hash = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()
        
                validator_aggregated_cid = get_validator_aggregated_cid(curr_GI, validator_address, model_cids, genesis_model_ipfs_hash)
                
                tx_hash = deployed_DINTaskCoordinatorContract.functions.submitT2Aggregation(curr_GI, batch_id, validator_aggregated_cid).transact({"from": validator_address})
        
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                
                time.sleep(0.1)
                
            else:
                
                continue
        
        return {"message": "Aggregated honestly all T2 successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
            
            
            
        
        
        
        
        
        
        
        
        
        
        
