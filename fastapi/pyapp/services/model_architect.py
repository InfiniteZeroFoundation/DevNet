import torch
import torch.nn as nn
import torch.nn.functional as F
import os
from services.ipfs_service import upload_to_ipfs
from services.blockchain_services import get_w3
import torch.nn.init as init
from dotenv import dotenv_values
import json




class ModelArchitecture(nn.Module):
    def __init__(self):
        super(ModelArchitecture, self).__init__()
        self.fc1 = nn.Linear(28*28, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3 = nn.Linear(64, 10)

    def forward(self, x):
        # x shape: [batch_size, 1, 28, 28]
        x = x.view(x.size(0), -1)         # flatten to [batch_size, 784]
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x
    
def initialize_weights(m):
    if isinstance(m, nn.Linear):
        # Initialize weights with Xavier uniform initialization
        init.xavier_uniform_(m.weight)
        # Initialize biases to zero
        if m.bias is not None:
            init.zeros_(m.bias)    

    
def getGenesisModelIpfs():
    model = ModelArchitecture()
    
    #initialize model
    model.apply(initialize_weights)
    
    # Save the trained genesis model to disk
    os.makedirs("./models", exist_ok=True)
    torch.save(model, "./models/modelowner/genesis_model.pth")
    
    # Upload the model to IPFS
    model_hash = upload_to_ipfs("./models/modelowner/genesis_model.pth", "Genesis model")
    return model_hash

def get_DINTaskCoordinator_Instance(dintaskcoordinator_address=None):
    w3 = get_w3()
    if dintaskcoordinator_address is None:
        dintaskcoordinator_address = dotenv_values(".env").get("DINTaskCoordinator_Contract_Address")
    
    with open("../../hardhat/artifacts/contracts/DINTaskCoordinator.sol/DINTaskCoordinator.json") as f:
        dintaskcoordinator_data = json.load(f)
        dintaskcoordinator_abi = dintaskcoordinator_data["abi"]
        dintaskcoordinator_bytecode = dintaskcoordinator_data["bytecode"]
        
    if dintaskcoordinator_address:
        deployed_DINTaskCoordinatorContract = w3.eth.contract(address=dintaskcoordinator_address, abi=dintaskcoordinator_abi, bytecode=dintaskcoordinator_bytecode)
        return deployed_DINTaskCoordinatorContract
    else:
        return w3.eth.contract(abi=dintaskcoordinator_abi, bytecode=dintaskcoordinator_bytecode)
 