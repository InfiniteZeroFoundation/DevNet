import os
import sys

import torch
from rich import console

from dincli.services.ipfs import retrieve_from_ipfs, upload_to_ipfs

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

console = console.Console()


def get_aggregated_cid_t1(curr_GI, aggregator_address, model_cids, genesis_model_ipfs_hash, bid, model_base_dir):

    aggregator_models_path = f"{model_base_dir}/aggregator/{aggregator_address}/{curr_GI}/T1/{bid}/models"

    os.makedirs(aggregator_models_path, exist_ok=True)

    local_paths = []
    for cid in model_cids:
        out_path = os.path.join(aggregator_models_path, f"{cid}.pth")
        retrieve_from_ipfs(cid, out_path) 
        local_paths.append(out_path) 


    # Load all state_dicts
    state_dicts = []
    for path in local_paths:
        state_dict = torch.load(path)
        state_dicts.append(state_dict)

    
    out_path = os.path.join(model_base_dir, f"models/genesis_model.pth")
    retrieve_from_ipfs(genesis_model_ipfs_hash, out_path)    
    
    base_model = torch.load(out_path, weights_only=False)
    averaged_state_dict = base_model.state_dict()
    
    # Initialize accumulator
    for key in averaged_state_dict:
        averaged_state_dict[key] = torch.zeros_like(averaged_state_dict[key])
    
    
    # Accumulate weights
    for state_dict in state_dicts:
        for key in averaged_state_dict:
            averaged_state_dict[key] += state_dict[key]
            
    num_models = len(state_dicts)
    
    # Average weights
    for key in averaged_state_dict:
        averaged_state_dict[key] /= num_models
    
    # Load averaged weights into the model
    base_model.load_state_dict(averaged_state_dict)
    
    # Save averaged model
    torch.save(base_model.state_dict(), os.path.join(aggregator_models_path, "averaged_model.pth"))
    
    # Upload the model to IPFS
    model_hash = upload_to_ipfs(os.path.join(aggregator_models_path, "averaged_model.pth"), "Averaged model")
    return model_hash 
    
def get_aggregated_cid_t2(curr_GI, aggregator_address, model_cids, genesis_model_ipfs_hash, bid, model_base_dir):

    aggregator_models_path = f"{model_base_dir}/aggregator/{aggregator_address}/{curr_GI}/T1/{bid}/models"

    os.makedirs(aggregator_models_path, exist_ok=True)

    local_paths = []
    for cid in model_cids:
        out_path = os.path.join(aggregator_models_path, f"{cid}.pth")
        retrieve_from_ipfs(cid, out_path) 
        local_paths.append(out_path) 


    # Load all state_dicts
    state_dicts = []
    for path in local_paths:
        state_dict = torch.load(path)
        state_dicts.append(state_dict)

    
    out_path = os.path.join(model_base_dir, f"models/genesis_model.pth")
    retrieve_from_ipfs(genesis_model_ipfs_hash, out_path)    
    
    base_model = torch.load(out_path, weights_only=False)
    averaged_state_dict = base_model.state_dict()
    
    # Initialize accumulator
    for key in averaged_state_dict:
        averaged_state_dict[key] = torch.zeros_like(averaged_state_dict[key])
    
    
    # Accumulate weights
    for state_dict in state_dicts:
        for key in averaged_state_dict:
            averaged_state_dict[key] += state_dict[key]
            
    num_models = len(state_dicts)
    
    # Average weights
    for key in averaged_state_dict:
        averaged_state_dict[key] /= num_models
    
    # Load averaged weights into the model
    base_model.load_state_dict(averaged_state_dict)
    
    # Save averaged model
    torch.save(base_model.state_dict(), os.path.join(aggregator_models_path, "averaged_model.pth"))
    
    # Upload the model to IPFS
    model_hash = upload_to_ipfs(os.path.join(aggregator_models_path, "averaged_model.pth"), "Averaged model")
    return model_hash 
    
    
