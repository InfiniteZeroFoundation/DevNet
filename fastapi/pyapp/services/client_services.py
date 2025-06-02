import torch

from services.ipfs_service import upload_to_ipfs, retrieve_from_ipfs

from web3 import Web3

from dotenv import load_dotenv
from torch.utils.data import DataLoader
import torch.nn as nn
import torch.optim as optim
import os
import torch
import torch.nn.functional as F

load_dotenv()

RPC_URL = os.getenv("RPC_URL")  

from services.model_architect import get_w3, get_DINTaskCoordinator_Instance

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


def train_client_model_and_upload_to_ipfs(genesis_model_ipfs_hash, initial_model_ipfs_hash=None, dp_mode="disabled"):
    
    num_clients = 9
    client_model_ipfs_hashes = []
    
    retrieve_from_ipfs(genesis_model_ipfs_hash,"./models/clients/genesis_model.pth")
    
    print("Genesis model retrieved from IPFS")
    
    for i in range(num_clients):
       # Step 1: Load the model architecture
       model_architecture = torch.load("./models/clients/genesis_model.pth", weights_only=False)
       print("Genesis model loaded")
       # Step 2: Load the client dataset
       client_dataset = torch.load(f"./Dataset/clients/clientDataset_{i+1}.pt", weights_only=False)
       print(f"Client {i+1} dataset loaded")
       
       if initial_model_ipfs_hash:
           retrieve_from_ipfs(initial_model_ipfs_hash, f"./models/clients/initial_model_ipfs_hash.pth")
           model_architecture.load_state_dict(torch.load(f"./models/clients/initial_model_ipfs_hash.pth"))
           print(f"Initial model loaded and weights initialized from GM")
           
      
           

       # Step 3: Define the DataLoader
       batch_size = 32  # Adjust batch size as needed
       data_loader = DataLoader(client_dataset, batch_size=batch_size, shuffle=True)
       
       # Step 4: Define the loss function and optimizer
       criterion = nn.CrossEntropyLoss()  
       optimizer = optim.Adam(model_architecture.parameters(), lr=0.001)  # Adam optimizer with learning rate 0.001
       
       # Step 5: Train the model
       num_local_epochs = 10  # Adjust number of epochs as needed
       for epoch in range(num_local_epochs):
           for inputs, labels in data_loader:
               optimizer.zero_grad()
               outputs = model_architecture(inputs)
               loss = criterion(outputs, labels)
               loss.backward()
               optimizer.step()
               
       print(f"Client {i+1} model trained successfully")
       
       # Step 6: Save the model
       torch.save(model_architecture.state_dict(), f"./models/clients/client_model_{i+1}.pth")
       
       if dp_mode == "afterTraining":
           
           # Get the model weights as a state dict
           original_state_dict = model_architecture.state_dict()
           
           sigma = 0.5  # Noise standard deviation
           S = 1.0     # Clipping norm
           
           # Apply noise and clipping to the state dict
           noisy_state_dict = add_noise_and_clip_state_dict(original_state_dict, sigma, S)
           
           # Save the noisy model
           torch.save(noisy_state_dict, f"./models/clients/client_model_{i+1}_noisy.pth")
           
           print(f"Client {i+1} model saved successfully")
           
           # Step 7: Upload the model to IPFS
           client_model_ipfs_hash = upload_to_ipfs(f"./models/clients/client_model_{i+1}_noisy.pth")
           print(f"Client {i+1} noisy model uploaded to IPFS with hash: {client_model_ipfs_hash}")
           client_model_ipfs_hashes.append(client_model_ipfs_hash)
           
       elif dp_mode == "disabled":
           
           print(f"Client {i+1} model saved successfully")
       
           # Step 7: Upload the model to IPFS
           client_model_ipfs_hash = upload_to_ipfs(f"./models/clients/client_model_{i+1}.pth")
           print(f"Client {i+1} model uploaded to IPFS with hash: {client_model_ipfs_hash}")
           client_model_ipfs_hashes.append(client_model_ipfs_hash)
       
    return client_model_ipfs_hashes
       
    
   