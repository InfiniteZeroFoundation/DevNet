import os
import torch
import sys

from dincli.services.ipfs import upload_to_ipfs, retrieve_from_ipfs
from torch.utils.data import DataLoader
from dincli.cli.utils import CONFIG_DIR, CACHE_DIR
from rich import console


sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from model import ModelArchitecture
console = console.Console()


def Score_model_by_auditor(gi, genesis_model_cid, batch_id, model_index, auditor_address, testDataCID, lm_cid, model_base_dir):  
    try:
        
        eligible = True
        
        os.makedirs(f"{model_base_dir}/dataset", exist_ok=True) 

        batch_test_data_path = f"{model_base_dir}/dataset/auditor/TestDatasets/auditorDataset_{gi}_{batch_id}.pt"

        retrieve_from_ipfs(testDataCID, batch_test_data_path)

        console.print("Auditor test data of batch", batch_id, "retrieved with IPFS hash ", testDataCID, "at path", batch_test_data_path)

        testdata = torch.load(batch_test_data_path, weights_only=False)

        genesis_model_path = f"{model_base_dir}/models/genesis_model.pth"

        retrieve_from_ipfs(genesis_model_cid, genesis_model_path)

        console.print("Auditor genesis model retrieved with IPFS hash ", genesis_model_cid, "at path", genesis_model_path)

        model_architecture = torch.load(genesis_model_path, weights_only=False)

        lm_path = f"{model_base_dir}/models/auditor/lm_{gi}_{model_index}.pth"

        retrieve_from_ipfs(lm_cid, lm_path)

        console.print(f"lm model {model_index} for batch {batch_id} retrieved with IPFS hash {lm_cid} at path {lm_path}")

        lm_weights = torch.load(lm_path, weights_only=True)
        
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





