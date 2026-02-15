import os
import sys

import torch
import torch.nn as nn
import torch.optim as optim
from rich.console import Console
from torch.utils.data import DataLoader

from dincli.cli.utils import get_w3
from dincli.services.ipfs import retrieve_from_ipfs, upload_to_ipfs

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
console = Console()


def add_noise(weights, sigma):
    noise = torch.normal(0, sigma, size=weights.shape, device=weights.device)
    return weights + noise

def clip_weights(weights, S):
    norm = torch.norm(weights)
    factor = max(1.0, norm / S)
    return weights / factor

def add_noise_and_clip_state_dict(state_dict, sigma, S):
    noisy_state_dict = {}
    for key, weights in state_dict.items():
        # Clip weights
        clipped_w = clip_weights(weights, S)
        # Add noise
        noisy_w = add_noise(clipped_w, sigma)
        # Store in the new state dict
        noisy_state_dict[key] = noisy_w
    return noisy_state_dict


def train_client_model_and_upload_to_ipfs(
    genesis_model_ipfs_hash,
    account_address,
    effective_network="local",
    initial_model_ipfs_hash=None,
    dp_mode="disabled",
    model_base_dir="",
    gi=None,
):

    retrieve_from_ipfs(genesis_model_ipfs_hash,model_base_dir /"models"/"genesis_model.pth")

    console.print("Retrieved genesis model from IPFS")

    # Step 1: Load the model architecture
    model_architecture = torch.load(model_base_dir /"models"/"genesis_model.pth", weights_only=False)
    console.print("Genesis model with IPFS hash " + genesis_model_ipfs_hash + " loaded from path :  " + str(model_base_dir /"models"/"genesis_model.pth"))

    w3 = get_w3(effective_network)
   

    # Step 2: Load the client dataset
    client_dataset_path = model_base_dir / "dataset"/"clients"/account_address/"data.pt"

    if not client_dataset_path.exists():
        raise Exception("Client dataset not found at " + str(client_dataset_path))
    client_dataset = torch.load(client_dataset_path, weights_only=False)
    console.print("Client dataset loaded from path :  " + str(client_dataset_path))

    # Step 3: Load the initial model
    if initial_model_ipfs_hash:
        retrieve_from_ipfs(initial_model_ipfs_hash, model_base_dir /"models"/f"gm_{gi-1}.pt")
        model_architecture.load_state_dict(torch.load(model_base_dir /"models"/f"gm_{gi-1}.pt"))
        console.print(f"Initial model loaded and weights initialized from GM")

    # Step 4: Define the DataLoader
    batch_size = 32  # Adjust batch size as needed
    data_loader = DataLoader(client_dataset, batch_size=batch_size, shuffle=True)

    # Step 5: Define the loss function and optimizer
    criterion = nn.CrossEntropyLoss()  
    optimizer = optim.Adam(model_architecture.parameters(), lr=0.001)  # Adam optimizer with learning rate 0.001

    # Step 6: Train the model
    num_local_epochs = 10  # Adjust number of epochs as needed
    for epoch in range(num_local_epochs):
        for inputs, labels in data_loader:
            optimizer.zero_grad()
            outputs = model_architecture(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
                
    

    # Step 6: Save the model
    os.makedirs(model_base_dir / "models"/"clients"/account_address, exist_ok=True)
    torch.save(model_architecture.state_dict(), model_base_dir / "models"/"clients"/account_address/f"lm_{gi}.pth")

    console.print(f"Client {account_address} model trained successfully at path :  " + str(model_base_dir / "models"/"clients"/account_address/f"lm_{gi}.pth"))

    if dp_mode == "afterTraining":
           
        # Get the model weights as a state dict
        original_state_dict = model_architecture.state_dict()
            
        sigma = 0.5  # Noise standard deviation
        S = 1.0     # Clipping norm
            
        # Apply noise and clipping to the state dict
        noisy_state_dict = add_noise_and_clip_state_dict(original_state_dict, sigma, S)
            
        # Save the noisy model
        torch.save(noisy_state_dict, model_base_dir / "models"/"clients"/account_address/f"lm_{gi}_noisy.pth")
            
        console.print(f"Noisy Client {account_address} model saved successfully at path :  " + str(model_base_dir / "models"/"clients"/account_address/f"lm_{gi}_noisy.pth"))
           
        # Step 7: Upload the model to IPFS
        client_model_ipfs_hash = upload_to_ipfs(model_base_dir / "models"/"clients"/account_address/f"lm_{gi}_noisy.pth", f"Noisy Client {account_address} model uploaded to IPFS")
        console.print(f"Noisy Client {account_address} model uploaded to IPFS with hash: {client_model_ipfs_hash}")

    elif dp_mode == "disabled":
       
        # Step 7: Upload the model to IPFS
        client_model_ipfs_hash = upload_to_ipfs(model_base_dir / "models"/"clients"/account_address/f"lm_{gi}.pth", f"Client {account_address} model uploaded to IPFS")
        console.print(f"Client {account_address} model uploaded to IPFS with hash: {client_model_ipfs_hash}")

    return client_model_ipfs_hash




        











    
    