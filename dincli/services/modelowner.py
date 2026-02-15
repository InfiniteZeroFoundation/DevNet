import os
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.init as init
from torch.utils.data import DataLoader

from dincli.cli.utils import CONFIG_DIR
from dincli.services.ipfs import retrieve_from_ipfs, upload_to_ipfs
from dincli.services.model import ModelArchitecture


def initialize_weights(m):
    if isinstance(m, nn.Linear):
        # Initialize weights with Xavier uniform initialization
        init.xavier_uniform_(m.weight)
        # Initialize biases to zero
        if m.bias is not None:
            init.zeros_(m.bias)  

def getGenesisModelIpfs(base_path):
    model = ModelArchitecture()
    
    #initialize model
    model.apply(initialize_weights)
    
    # Save the trained genesis model to disk
    model_dir = Path(base_path/"models")
    os.makedirs(model_dir, exist_ok=True)
    model_path = model_dir / "genesis_model.pth"
    torch.save(model, str(model_path))

    print("saving genesis model at " + str(model_path))
    
    # Upload the model to IPFS
    model_hash = upload_to_ipfs(str(model_path), "Genesis model")
    return model_hash


def getscoreforGM(gi: int, gmcid: str, base_path):
    try:
        os.makedirs(base_path / "dataset"/"test", exist_ok=True)
        if not os.path.exists(base_path / "dataset"/"test"/"test_dataset.pt"):
            print("test dataset not found at " + str(base_path / "dataset"/"test"/"test_dataset.pt"))
            return
        testdata = torch.load(base_path / "dataset"/"test"/"test_dataset.pt", weights_only=False)
        
        model_architecture = torch.load(base_path /"models"/"genesis_model.pth", weights_only=False)
        
        retrieve_from_ipfs(gmcid, base_path / "models"/ f"gm_{gi}.pt")
        
        if gi ==0 :
            temp_model = torch.load(base_path / "models"/ f"gm_{gi}.pt", weights_only=False)
            gm_weights = temp_model.state_dict()
        else:
            gm_weights = torch.load(base_path / "models"/f"gm_{gi}.pt", weights_only=True)
        
        model_architecture.load_state_dict(gm_weights)
        
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
            
            return accuracy
    
    except Exception as e:
        print(e)
        

def create_audit_testDataCIDs(batch_counts: int, gi: int):
    print("batch_counts", batch_counts)
    test_data = torch.load(f"{CONFIG_DIR}/dataset/test/test_dataset.pt", weights_only=False)
    
    total_test_samples = len(test_data)
    
    testData_percentage_per_auditor_batch = 5
    
    # Number of samples each batch gets
    samples_per_batch = int(total_test_samples * (testData_percentage_per_auditor_batch / 100))
    
    audit_testDataCIDs = []
    
    for batch_id in range(batch_counts):
        
        torch.manual_seed(batch_id)
        
        # Generate random indices
        random_indices = torch.randperm(total_test_samples)[:samples_per_batch]
        
        # Create shuffled subset
        assigned_testData = torch.utils.data.Subset(test_data, random_indices)
        
        os.makedirs(f"{CONFIG_DIR}/dataset/auditor/TestDatasets", exist_ok=True)
        
        torch.save(assigned_testData, f"{CONFIG_DIR}/dataset/auditor/TestDatasets/auditorDataset_{gi}_{batch_id}.pt")
        
        ipfs_hash = upload_to_ipfs(f"{CONFIG_DIR}/dataset/auditor/TestDatasets/auditorDataset_{gi}_{batch_id}.pt", f"Auditor Dataset for gi_{gi} index {batch_id} uploaded")
        
        audit_testDataCIDs.append(ipfs_hash)
    return audit_testDataCIDs