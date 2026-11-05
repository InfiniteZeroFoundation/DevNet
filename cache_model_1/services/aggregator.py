import os
import sys

import torch
from rich import console

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from model import ModelArchitecture
console = console.Console()


def _average_state_dicts(model_paths, genesis_model_path, aggregator_models_path):
    state_dicts = [torch.load(path) for path in model_paths]

    base_model = torch.load(genesis_model_path, weights_only=False)
    averaged_state_dict = base_model.state_dict()

    for key in averaged_state_dict:
        averaged_state_dict[key] = torch.zeros_like(averaged_state_dict[key])

    for state_dict in state_dicts:
        for key in averaged_state_dict:
            averaged_state_dict[key] += state_dict[key]

    num_models = len(state_dicts)
    for key in averaged_state_dict:
        averaged_state_dict[key] /= num_models

    base_model.load_state_dict(averaged_state_dict)

    averaged_model_path = os.path.join(aggregator_models_path, "averaged_model.pth")
    torch.save(base_model.state_dict(), averaged_model_path)
    return averaged_model_path


def get_aggregated_cid_t1(curr_GI, aggregator_address, model_cids, genesis_model_ipfs_hash, bid, model_base_dir):
    """Average a T1 batch's local models and write the result locally.

    `model_cids`/`genesis_model_ipfs_hash` are kept as parameters purely to
    derive the same local filenames dincli already fetched them into via IPFS
    before invoking this function (`<aggregator_models_path>/<cid>.pth` and
    `models/genesis_model.pth`); no network access happens in here. The
    return value is a local path, which dincli uploads to IPFS afterward.
    """

    aggregator_models_path = f"{model_base_dir}/aggregator/{aggregator_address}/{curr_GI}/T1/{bid}/models"
    os.makedirs(aggregator_models_path, exist_ok=True)

    model_paths = [os.path.join(aggregator_models_path, f"{cid}.pth") for cid in model_cids]
    genesis_model_path = os.path.join(model_base_dir, "models", "genesis_model.pth")

    return _average_state_dicts(model_paths, genesis_model_path, aggregator_models_path)


def get_aggregated_cid_t2(curr_GI, aggregator_address, model_cids, genesis_model_ipfs_hash, bid, model_base_dir):
    """Average a T2 batch's T1 outputs and write the result locally.

    Same contract as `get_aggregated_cid_t1`: dincli pre-fetches inputs and
    uploads the returned local path; no IPFS access happens in here.
    """

    aggregator_models_path = f"{model_base_dir}/aggregator/{aggregator_address}/{curr_GI}/T2/{bid}/models"
    os.makedirs(aggregator_models_path, exist_ok=True)

    model_paths = [os.path.join(aggregator_models_path, f"{cid}.pth") for cid in model_cids]
    genesis_model_path = os.path.join(model_base_dir, "models", "genesis_model.pth")

    return _average_state_dicts(model_paths, genesis_model_path, aggregator_models_path)
