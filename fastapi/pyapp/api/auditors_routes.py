from fastapi import APIRouter, Depends
from pydantic import BaseModel
from dotenv import load_dotenv, set_key, unset_key, dotenv_values
import time
from services.DAO_services import get_DINtokenContract_Instance, get_DINValidatorStake_Instance, get_DINCoordinator_Instance
from services.blockchain_services import get_w3
from services.model_architect import get_DINTaskCoordinator_Instance, GIstatestrToIndex, GIstateToStr, get_DINTaskAuditor_Instance
from services.auditor_services import Score_model_by_auditor

router = APIRouter(prefix="/auditors", tags=["Auditors"])

MIN_STAKE = 1000000 

@router.post("/getAuditorsState")
def get_auditors_state():
    try:
        print(" ****to remove ", " finding registered_auditors", )
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        Auditors_Adresses = w3.eth.accounts[50:50+9]
        
        AuditorsETHBalances = []
        AuditorsDINtokenBalances = []
        AuditorsDinStakedTokens = []
        registered_auditors = []
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        DinValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        
        
        for auditor_address in Auditors_Adresses:
            
            auditor_eth_balance = w3.from_wei(w3.eth.get_balance(auditor_address), 'ether')
            AuditorsETHBalances.append(auditor_eth_balance)
            
            if DinToken_Contract_Address is  not None:
                deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
                auditor_dintoken_balance = deployed_DINtokenContract.functions.balanceOf(auditor_address).call()
                AuditorsDINtokenBalances.append(auditor_dintoken_balance)
            else:
                AuditorsDINtokenBalances.append(0)
            
            if DinValidatorStake_Contract_Address is not None:
                deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DinValidatorStake_Contract_Address)
                auditor_din_staked_tokens = deployed_DINValidatorStakeContract.functions.getStake(auditor_address).call()
                AuditorsDinStakedTokens.append(auditor_din_staked_tokens)
            else:
                AuditorsDinStakedTokens.append(0)
                
                
        if DINTaskAuditor_Contract_Address is not None and DINTaskCoordinator_Contract_Address is not None:
            deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
            
            deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
            curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
            
            registered_auditors = deployed_DINTaskAuditorContract.functions.getDINtaskAuditors(curr_GI).call()
            

        
        return {"message": "Auditors state fetched successfully",
            "status": "success",
            "auditors_addresses": Auditors_Adresses,
            "registered_auditors": registered_auditors,
            "auditors_eth_balances": AuditorsETHBalances,
            "DINValidatorStakeAddress": DinValidatorStake_Contract_Address,
            "dintoken_address": DinToken_Contract_Address,
            "auditors_dintoken_balances": AuditorsDINtokenBalances,
            "auditors_din_staked_tokens": AuditorsDinStakedTokens
            
            }
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

     
@router.post("/buyDINTokens")
def buy_dintokens():
    try:
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        
        Auditors_Adresses = w3.eth.accounts[50:50+9]
        
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
        
        dincoordinator_contract_address = env_config.get("DINCoordinator_Contract_Address")
        
        deployed_dincoordinator = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_contract_address) 
        
        for auditor_address in Auditors_Adresses:
            tx_hash = deployed_dincoordinator.functions.depositAndMint().transact({
                "from": auditor_address,
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
        
        
class AuditorAddressRequest(BaseModel):
    auditor_address: str

@router.post("/buyDINTokensSingle")
def buy_dintokens_single(request: AuditorAddressRequest):
    try:
        auditor_address = request.auditor_address
        env_config = dotenv_values(".env")
        w3 = get_w3()
        print("Auditor address:", auditor_address)
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
        
        dincoordinator_contract_address = env_config.get("DINCoordinator_Contract_Address")
        
        deployed_dincoordinator = get_DINCoordinator_Instance(dincoordinator_address=dincoordinator_contract_address) 
        
        tx_hash = deployed_dincoordinator.functions.depositAndMint().transact({
            "from": auditor_address,
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
        Auditors_Adresses = w3.eth.accounts[50:50+9]
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
        
        DinValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DinValidatorStake_Contract_Address)
        
        MIN_STAKE = 1000000
        
        for auditor_address in Auditors_Adresses:
            auditor_Din_token_balance = deployed_DINtokenContract.functions.balanceOf(auditor_address).call()
            if auditor_Din_token_balance >= MIN_STAKE:
                tx_approval_hash = deployed_DINtokenContract.functions.approve(DinValidatorStake_Contract_Address, MIN_STAKE).transact({"from": auditor_address})
                receipt = w3.eth.wait_for_transaction_receipt(tx_approval_hash)
                
                tx_stake_hash = deployed_DINValidatorStakeContract.functions.stake(MIN_STAKE).transact({"from": auditor_address})
                
                receipt = w3.eth.wait_for_transaction_receipt(tx_stake_hash)
      
        return {"message": "DIN tokens staked successfully",
                "status": "success"}          
                
    except Exception as e:
        return {"message": str(e),
                "status": "error"} 
        

@router.post("/stakeDINTokensSingle")
def stake_dintokens_single(request: AuditorAddressRequest): 
    try:    
        auditor_address = request.auditor_address
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        MIN_STAKE = 1000000
        
        DinToken_Contract_Address = env_config.get("DINToken_Contract_Address")
        
        deployed_DINtokenContract = get_DINtokenContract_Instance(dintoken_address=DinToken_Contract_Address)
        
        DinValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DinValidatorStake_Contract_Address)
        
        auditor_Din_token_balance = deployed_DINtokenContract.functions.balanceOf(auditor_address).call()
        
        if auditor_Din_token_balance >= MIN_STAKE:
            tx_approval_hash = deployed_DINtokenContract.functions.approve(DinValidatorStake_Contract_Address, MIN_STAKE).transact({"from": auditor_address})
            receipt = w3.eth.wait_for_transaction_receipt(tx_approval_hash)
            
            tx_stake_hash = deployed_DINValidatorStakeContract.functions.stake(MIN_STAKE).transact({"from": auditor_address})
            receipt = w3.eth.wait_for_transaction_receipt(tx_stake_hash)
        
            return {"message": "DIN tokens staked successfully",
                "status": "success"}          
                
    except Exception as e:
        return {"message": str(e),
                "status": "error"}      
        
        
@router.post("/registerTaskAuditors")
def register_task_auditors():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        DINValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DINValidatorStake_Contract_Address)
        
        Auditors_Adresses = w3.eth.accounts[50:50+9]
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if GIstateToStr(curr_GIstate) != "DINauditorRegistrationStarted":
            raise Exception("Can not register auditors at this time")
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        registered_auditors = deployed_DINTaskAuditorContract.functions.getDINtaskAuditors(curr_GI).call()
        
        
        DINValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DINValidatorStake_Contract_Address)
        
        for auditor_address in Auditors_Adresses:
            if auditor_address not in registered_auditors:
                auditor_stake = deployed_DINValidatorStakeContract.functions.getStake(auditor_address).call()
                if auditor_stake >= MIN_STAKE:
                    tx_hash = deployed_DINTaskAuditorContract.functions.registerDINAuditor(curr_GI).transact({"from": auditor_address})
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                    time.sleep(0.1)
        
        
        return {"message": "Task Auditors registered successfully",
                "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}

@router.post("/registerTaskAuditorSingle")
def register_task_auditor_single(request: AuditorAddressRequest):                
    try:        
            
        auditor_address = request.auditor_address
        
        print("to remove ", " auditor_address", auditor_address)
        env_config = dotenv_values(".env")
        w3 = get_w3()
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        print("to remove ", " DINTaskCoordinator_Contract_Address", DINTaskCoordinator_Contract_Address)
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        
        print("to remove ", " curr_GI", curr_GI)
        
        GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        print("to remove ", " GIstate", GIstate)
        
        if GIstateToStr(GIstate) != "DINauditorRegistrationStarted":
            raise Exception("Can not register auditors at this time")
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        registered_auditors = deployed_DINTaskAuditorContract.functions.getDINtaskAuditors(curr_GI).call()
        
        print("to remove ", " registered_auditors", registered_auditors)
        
        time.sleep(5)
        DINValidatorStake_Contract_Address = env_config.get("DINValidatorStake_Contract_Address")
        
        deployed_DINValidatorStakeContract = get_DINValidatorStake_Instance(dinvalidatorstake_address=DINValidatorStake_Contract_Address)
        
        if auditor_address not in registered_auditors:
            
            auditor_stake = deployed_DINValidatorStakeContract.functions.getStake(auditor_address).call()
            
            
        
            if auditor_stake < MIN_STAKE:
                raise Exception("Auditor stake is less than minimum stake")
            elif auditor_stake >= MIN_STAKE:
                tx_hash = deployed_DINTaskAuditorContract.functions.registerDINAuditor(curr_GI).transact({"from": auditor_address})
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                
                return {"message": "Task auditor registered successfully",
                        "status": "success"}
    except Exception as e:
        return {"message": str(e),
                "status": "error"}
        
@router.get("/getAuditorEvaluationBatches")
def get_auditor_evaluation_batches():
    try:
        env_config = dotenv_values(".env")
    
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
    
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate < GIstatestrToIndex("LMSevaluationStarted"):
            raise Exception("Can not get auditor evaluation batches at this time")
    
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
            
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        raw_lm_submissions = deployed_DINTaskAuditorContract.functions.getClientModels(curr_GI).call()
    
        lm_submissions = {}
        
        for idx, sub in enumerate(raw_lm_submissions):
            client, model_cid, submitted_at, eligible, evaluated, approved, final_avg = sub
            lm_submissions[idx] = {
                "client": client,
                "modelCID": model_cid or "None"
            }
            
        raw_audit_batches = []
        
        audit_batch_count = deployed_DINTaskAuditorContract.functions.AuditorsBatchCount(curr_GI).call()
        
        for batch_id in range(audit_batch_count):
            raw_audit_batches.append(deployed_DINTaskAuditorContract.functions.getAuditorsBatch(curr_GI, batch_id).call())
            
        auditor_tasks = {} 
        
        for batch_data in raw_audit_batches:
            batch_id, auditors, model_indexes, test_cid = batch_data

            for auditor in auditors:
                # Ensure auditor entry exists
                if auditor not in auditor_tasks:
                    auditor_tasks[auditor] = {
                        "auditor": auditor,
                        "assignedModels": []
                    }

                # Add each model in this batch
                for m_idx in model_indexes:
                    # Fetch on-chain state: hasAuditedLM
                    try:
                        has_voted = deployed_DINTaskAuditorContract.functions.hasAuditedLM(curr_GI, batch_id, auditor, m_idx).call()
                        is_eligible = deployed_DINTaskAuditorContract.functions.LMeligibleVote(curr_GI, batch_id, auditor, m_idx).call()
                        has_auditScores = deployed_DINTaskAuditorContract.functions.auditScores(curr_GI, batch_id, auditor, m_idx).call()
                        
                    except:
                        has_voted = False  # fail-safe
                        has_auditScores = 0
                        is_eligible = False

                    # Get model details
                    model_info = lm_submissions.get(m_idx, {
                        "client": "Unknown",
                        "modelCID": "N/A"
                    })

                    auditor_tasks[auditor]["assignedModels"].append({
                        "modelIndex": m_idx,
                        "batchId": batch_id,
                        "hasVoted": has_voted,
                        "isEligible": is_eligible,
                        "hasAuditScores": has_auditScores,
                        "model": model_info,
                        "testCID": test_cid or "None"
                    })


        return {"message": "Auditor evaluation batches fetched successfully", "status": "success",
                "auditorEvaluationBatches": auditor_tasks}

    except Exception as e:
        return {"message": str(e),
                "status": "error"}

class EvaluateLMRequest(BaseModel):
    auditor_address: str
    batch_id: int
    model_index: int        
    
@router.post("/evaluateLM")
def evaluate_lm(request: EvaluateLMRequest):
    try:
        print(f"Evaluating LM for auditor {request.auditor_address}, batch {request.batch_id}, model {request.model_index}")
        
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
        
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate < GIstatestrToIndex("LMSevaluationStarted"):
            raise Exception("Can not evaluate LM at this time")

        audit_batch = deployed_DINTaskAuditorContract.functions.getAuditorsBatch(curr_GI, request.batch_id).call()
        
        testDataCID = audit_batch[3]
        
        if request.auditor_address not in audit_batch[1]:
            raise Exception("Auditor is not assigned to this batch")
        if request.model_index not in audit_batch[2]:
            raise Exception("Model is not assigned to this batch")
        
        
        lm = deployed_DINTaskAuditorContract.functions.lmSubmissions(curr_GI, request.model_index).call()
        
        lm_cid = lm[1]
        
        genesis_model_cid = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()
        
        score, eligible = Score_model_by_auditor(curr_GI, genesis_model_cid, request.batch_id, request.model_index, request.auditor_address, testDataCID, lm_cid, deployed_DINTaskAuditorContract)
        
        print("eligible",eligible, "score", score)
        
            
        deployed_DINTaskAuditorContract.functions.setAuditScorenEligibility(curr_GI, request.batch_id, request.model_index, int(score), bool(eligible)).transact({'from': request.auditor_address,  "gas": int(3000000),
            "gasPrice": w3.to_wei("5", "gwei"),})
        
        return {"message": "LM evaluated successfully", "status": "success"}
    except Exception as e:
        return {"message": str(e), "status": "error"}
    
@router.post("/evaluateallLMs")
def evaluate_all_lms():
    try:
        env_config = dotenv_values(".env")
        
        w3 = get_w3()
        
        DINTaskAuditor_Contract_Address = env_config.get("DINTaskAuditor_Contract_Address")
        
        DINTaskCoordinator_Contract_Address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        deployed_DINTaskAuditorContract = get_DINTaskAuditor_Instance(dintaskauditor_address=DINTaskAuditor_Contract_Address)
        
        deployed_DINTaskCoordinatorContract = get_DINTaskCoordinator_Instance(dintaskcoordinator_address=DINTaskCoordinator_Contract_Address)
  
        curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
        
        curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
        
        if curr_GIstate < GIstatestrToIndex("LMSevaluationStarted"):
            raise Exception("Can not evaluate LM at this time")
        
        AuditorsBatchCount = deployed_DINTaskAuditorContract.functions.AuditorsBatchCount(curr_GI).call()
        
        genesis_model_cid = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()
        
        for batch_id in range(AuditorsBatchCount):
            audit_batch = deployed_DINTaskAuditorContract.functions.getAuditorsBatch(curr_GI, batch_id).call()
            
            testDataCID = audit_batch[3]
            
            for model_index in audit_batch[2]:
                for auditor_address in audit_batch[1]:
                    lm = deployed_DINTaskAuditorContract.functions.lmSubmissions(curr_GI, model_index).call()
        
                    lm_cid = lm[1]
                    
                    score, eligible = Score_model_by_auditor(curr_GI, genesis_model_cid, batch_id, model_index, auditor_address, testDataCID, lm_cid)
                    
                    print("eligible",eligible, "score", score)
                    
                    deployed_DINTaskAuditorContract.functions.setAuditScorenEligibility(curr_GI, batch_id, model_index, int(score), bool(eligible)).transact({'from': auditor_address,  "gas": int(3000000),
                    "gasPrice": w3.to_wei("5", "gwei"),})
                    
        
        return {"message": "All LM evaluated successfully", "status": "success"}
    except Exception as e:
        return {"message": str(e), "status": "error"}