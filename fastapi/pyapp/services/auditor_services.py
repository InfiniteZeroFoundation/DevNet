from web3 import Web3
from dotenv import dotenv_values
import os
from services.blockchain_services import get_w3
import torch
from services.ipfs_service import upload_to_ipfs, retrieve_from_ipfs
from torch.utils.data import DataLoader

RPC_URL = os.getenv("RPC_URL")           # e.g. "http://127.0.0.1:8545"

def get_auditor_batches(gi, DinTaskAuditingC_address):
    w3 = get_w3()
    
    DinTaskAuditingC = w3.eth.contract(address=DinTaskAuditingC_address, abi=DinTaskAuditing_abi)
    
    return DinTaskAuditingC.functions.auditBatches(gi).call()

     
def getauditor_batch_by_address(gi, auditor_address, DinTaskAuditingC_address):
    w3 = get_w3()
    
    DinTaskAuditingC = w3.eth.contract(address=DinTaskAuditingC_address, abi=DinTaskAuditing_abi)
    
    auditBatches = DinTaskAuditingC.functions.auditBatches(gi).call()
    
    for batch in auditBatches:
        if batch.auditors.contains(auditor_address):
            return batch
        
    return None

def get_auditor_testDataCID(gi, auditor_address, DinTaskAuditingC_address):
    w3 = get_w3()
    
    auditor_batch = getauditor_batch_by_address(gi, auditor_address, DinTaskAuditingC_address)
    
    if(auditor_batch is not None):
        return auditor_batch.testDataCID
    
    return None
    
    
def Score_models_by_auditors(gi, auditor_address, DinTaskAuditingC_address):
    w3 = get_w3()
    
    auditor_batch = getauditor_batch_by_address(gi, auditor_address, DinTaskAuditingC_address)
    
    
    if(auditor_batch is not None):
        testDataCID = auditor_batch.testDataCID
    
        model_indexes = auditor_batch.modelIndexes
        
    retrieve_from_ipfs(testDataCID, f"./Dataset/auditor/auditorDataset_{gi}_{auditor_batch.batch_id}.pt")
        
    testdata = torch.load(f"./Dataset/auditor/auditorDataset_{gi}_{auditor_batch.batch_id}.pt", weights_only=False)
    
    DinTaskAuditingC = w3.eth.contract(address=DinTaskAuditingC_address, abi=DinTaskAuditing_abi)
    
    genesis_model_cid = DinTaskAuditingC.functions.genesisModelIpfsHash().call()
    
    retrieve_from_ipfs(genesis_model_cid, f"./models/auditor/genesis_model.pt")
    
    for model_index in model_indexes:
        lm = DinTaskAuditingC.functions.lmSubmissions(gi, model_index).call()
        
        os.makedirs(f"./models/auditor", exist_ok=True)
        
        retrieve_from_ipfs(genesis_model.cid, f"./models/auditor/lm_{gi}_{model_index}.pt")
        
        lm_d = torch.load(f"./models/auditor/lm_{gi}_{model_index}.pt", weights_only=True)
        
        model_architecture = torch.load(f"./models/auditor/genesis_model.pt", weights_only=False)
        
        model_architecture.load_state_dict(lm_d)
        
        model_architecture.eval()
        
        # 2. Create DataLoader for test data
        # If testdata is a TensorDataset or Subset
        test_loader = DataLoader(testdata, batch_size=32, shuffle=False)

        # 3. Move model to device (GPU/CPU)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model_architecture.to(device)
        
        with torch.no_grad():  # No gradients needed
            correct = 0
            total = 0
            for data, target in test_loader:
                data, target = data.to(device), target.to(device)

                # Forward pass
                outputs = model_architecture(data)

                # Get predicted class (for classification)
                # If outputs are logits, use argmax
                _, predicted = torch.max(outputs, 1)

                total += target.size(0)
                correct += (predicted == target).sum().item()

        accuracy = 100 * correct / total
        
        tx = DinTaskAuditingC.functions.updateModelScore(gi, model_index, accuracy).transact()
        
        receipt = w3.eth.wait_for_transaction_receipt(tx)
        
        print("Model score updated successfully")
        
        
def Score_model_by_auditor(gi, genesis_model_cid, batch_id, model_index, auditor_address, testDataCID, lm_cid):  
    try:
        
        eligible = True
        os.makedirs(f"./models/auditor", exist_ok=True) 
    
        retrieve_from_ipfs(testDataCID, f"./Dataset/auditor/auditorDataset_{gi}_{batch_id}.pt")
    
        testdata = torch.load(f"./Dataset/auditor/auditorDataset_{gi}_{batch_id}.pt", weights_only=False)
   
        retrieve_from_ipfs(genesis_model_cid, f"./models/auditor/genesis_model.pt")
        
        model_architecture = torch.load(f"./models/auditor/genesis_model.pt", weights_only=False)
        
        retrieve_from_ipfs(lm_cid, f"./models/auditor/lm_{gi}_{model_index}.pt")
        
        lm_weights = torch.load(f"./models/auditor/lm_{gi}_{model_index}.pt", weights_only=True)
        
        model_architecture.load_state_dict(lm_weights)
        
        model_architecture.eval()
        
        
        # 2. Create DataLoader for test data
        # If testdata is a TensorDataset or Subset
        test_loader = DataLoader(testdata, batch_size=32, shuffle=False)
        
    
        # 3. Move model to device (GPU/CPU)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model_architecture.to(device)
        
        with torch.no_grad():  # No gradients needed
            total = 0
            correct = 0
            for data, target in test_loader:
                data, target = data.to(device), target.to(device)

                # Forward pass
                outputs = model_architecture(data)

                # Get predicted class (for classification)
                # If outputs are logits, use argmax
                _, predicted = torch.max(outputs, 1)

                total += target.size(0)
                correct += (predicted == target).sum().item()

        accuracy = 100 * correct / total
        
        
        # by now it has been checked that 
        # 1. lm weights have desired shape
        # More checks may be added
        # Here are **five basic checks** you can safely include in your decentralized auditing code before approving a local model for aggregation:

        # 1. **Shape and Schema Check**
        # Verify that the local model (or weight update) has the exact same tensor shapes, parameter counts, and layer structure as the reference/global model. Reject if any mismatch.

        # 2. **Finite Values Check**
        # Ensure there are no `NaN` or `Inf` values in the submitted weights or updates. This prevents poisoned or corrupted updates from propagating.

        # 3. **Norm Bound Check**
        # Compute the L2 norm of the update `Δ = w_local − w_base` and reject if it exceeds a configured threshold (e.g., 1–2× the median norm of peers). This prevents extreme updates.

        # 4. **Layer-wise Magnitude Check**
        # For each layer, compare `||Δ_layer||₂ / ||w_base_layer||₂`. Reject if the ratio exceeds a max bound (e.g., 1–2%). This avoids layer-specific poisoning.

        # 5. **Cosine Similarity to Reference/Median**
        # Compare the submitted update with a robust reference (median of other updates or previous round). Reject if cosine similarity is below a threshold (e.g., ≤ −0.05). This helps catch anti-gradient or malicious updates.


        
        
        return accuracy, eligible
    except Exception as e:
        print("can not score model", e)
        return 0, False
    
    
    
    
    
    
    
    
    
    
    
        
        
        
        
        
        
        
        
        
    
    
    
    