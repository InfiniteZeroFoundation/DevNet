import torch
import os
from services.ipfs_service import upload_to_ipfs, retrieve_from_ipfs
from torch.utils.data import DataLoader

def create_audit_testDataCIDs(batch_counts: int, gi: int):
    print("batch_counts", batch_counts)
    test_data = torch.load(f"./Dataset/test/test_dataset.pt", weights_only=False)
    
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
        
        os.makedirs(f"./Dataset/auditorTestDatasets", exist_ok=True)
        
        torch.save(assigned_testData, f"./Dataset/auditorTestDatasets/auditorDataset_{gi}_{batch_id}.pt")
        
        ipfs_hash = upload_to_ipfs(f"./Dataset/auditorTestDatasets/auditorDataset_{gi}_{batch_id}.pt", f"Auditor Dataset for gi_{gi} index {batch_id} uploaded")
        
        audit_testDataCIDs.append(ipfs_hash)
    return audit_testDataCIDs


def getscoreforGM(gi: int, gmcid: str):
    try:
        testdata = torch.load(f"./Dataset/test/test_dataset.pt", weights_only=False)
        
        model_architecture = torch.load(f"./models/modelowner/genesis_model.pth", weights_only=False)
        
        retrieve_from_ipfs(gmcid, f"./models/modelowner/gm_{gi}.pt")
        
        if gi ==0 :
            temp_model = torch.load(f"./models/modelowner/gm_{gi}.pt", weights_only=False)
            gm_weights = temp_model.state_dict()
        else:
            gm_weights = torch.load(f"./models/modelowner/gm_{gi}.pt", weights_only=True)
        
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
        
    
        
        
        