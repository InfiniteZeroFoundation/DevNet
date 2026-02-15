import os

import torch
from rich import console
from torch.utils.data import DataLoader

from dincli.cli.utils import CONFIG_DIR
from dincli.services.ipfs import retrieve_from_ipfs

console = console.Console()


def Score_model_by_auditor(gi, genesis_model_cid, batch_id, model_index, auditor_address, testDataCID, lm_cid):  
    try:
        
        eligible = True
        
        os.makedirs(f"{CONFIG_DIR}/auditor/{auditor_address}/datasets", exist_ok=True) 

        retrieve_from_ipfs(testDataCID, f"{CONFIG_DIR}/auditor/{auditor_address}/datasets/auditorDataset_{gi}_{batch_id}.pt")

        console.print("testDataCID retrieved")

        testdata = torch.load(f"{CONFIG_DIR}/auditor/{auditor_address}/datasets/auditorDataset_{gi}_{batch_id}.pt", weights_only=False)

        os.makedirs(f"{CONFIG_DIR}/auditor/{auditor_address}/models", exist_ok=True) 

        retrieve_from_ipfs(genesis_model_cid, f"{CONFIG_DIR}/auditor/{auditor_address}/models/genesis_model.pt")

        
        model_architecture = torch.load(f"{CONFIG_DIR}/auditor/{auditor_address}/models/genesis_model.pt", weights_only=False)

        retrieve_from_ipfs(lm_cid, f"{CONFIG_DIR}/auditor/{auditor_address}/models/lm_{gi}_{model_index}.pt")

        lm_weights = torch.load(f"{CONFIG_DIR}/auditor/{auditor_address}/models/lm_{gi}_{model_index}.pt", weights_only=True)
        
        model_architecture.load_state_dict(lm_weights)
        
        model_architecture.eval()

        # If testdata is a TensorDataset or Subset
        test_loader = DataLoader(testdata, batch_size=32, shuffle=False)
        
    
        # Move model to device (GPU/CPU)
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

        return accuracy, eligible
    except Exception as e:
        print("can not score model", e)
        return 0, False





