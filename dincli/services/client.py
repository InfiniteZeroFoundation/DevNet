
import torch
import torch.nn as nn
import torch.optim as optim
from rich.console import Console
from torch.utils.data import DataLoader

from dincli.cli.utils import CONFIG_DIR, get_config, get_w3
from dincli.services.ipfs import retrieve_from_ipfs, upload_to_ipfs

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
    base_path=None
):

    if not base_path /"model"/"genesis_model.pth".exists():
        retrieve_from_ipfs(genesis_model_ipfs_hash,base_path/"model"/"genesis_model.pth")

        console.print("Retrieved genesis model from IPFS")

    # Step 1: Load the model architecture
    model_architecture = torch.load(base_path / "model"/"genesis_model.pth", weights_only=False)
    console.print("Genesis model loaded")

    w3 = get_w3(effective_network)
   
    account_address_norm = account_address.lower()

    if get_config("demo_mode"):
        client_addresses = w3.eth.accounts[2:2+9]
        client_addresses_norm = [addr.lower() for addr in client_addresses]

        if account_address_norm in client_addresses_norm:
            pos = client_addresses_norm.index(account_address_norm)

        else:
            if client_addresses:  # make sure the list isn't empty
                pos = random.randint(0, len(client_addresses) - 1)
            else:
                raise ValueError("client_addresses is empty — cannot choose a random index")

        # Step 2: Load the client dataset

        CACHE_DIR / effective_network / "dataset" / "clients" / client_address / "data.pt"
        client_dataset = torch.load(CONFIG_DIR / "clients"/f"client_{pos}"/"data.pt", weights_only=False)
        console.print("Client dataset loaded")


        if initial_model_ipfs_hash:
           retrieve_from_ipfs(initial_model_ipfs_hash, CONFIG_DIR / "client"/"model"/"initial_model.pth")
           model_architecture.load_state_dict(torch.load(CONFIG_DIR / "client"/"model"/"initial_model.pth"))
           console.print(f"Initial model loaded and weights initialized from GM")

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
                
        console.print(f"Client {pos} model trained successfully")

        # Step 6: Save the model
        torch.save(model_architecture.state_dict(), CONFIG_DIR / "client"/"model"/f"client_model_{pos}.pth")

        if dp_mode == "afterTraining":
           
           # Get the model weights as a state dict
           original_state_dict = model_architecture.state_dict()
           
           sigma = 0.5  # Noise standard deviation
           S = 1.0     # Clipping norm
           
           # Apply noise and clipping to the state dict
           noisy_state_dict = add_noise_and_clip_state_dict(original_state_dict, sigma, S)
           
           # Save the noisy model
           torch.save(noisy_state_dict, CONFIG_DIR / "client"/"model"/f"client_model_{pos}_noisy.pth")
           
           console.print(f"Noisy Client {pos} model saved successfully")
           
           # Step 7: Upload the model to IPFS
           client_model_ipfs_hash = upload_to_ipfs(CONFIG_DIR / "client"/"model"/f"client_model_{pos}_noisy.pth")
           console.print(f"Noisy Client {pos} model uploaded to IPFS with hash: {client_model_ipfs_hash}")

        elif dp_mode == "disabled":
           
           console.print(f"Client {pos} model saved successfully")
       
           # Step 7: Upload the model to IPFS
           client_model_ipfs_hash = upload_to_ipfs(CONFIG_DIR / "client"/"model"/f"client_model_{pos}.pth")
           console.print(f"Client {pos} model uploaded to IPFS with hash: {client_model_ipfs_hash}")

        return client_model_ipfs_hash




        











    
    