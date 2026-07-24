import torch
from typing import Union 
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
import os
from dincli.services.ipfs import upload_to_ipfs, retrieve_from_ipfs
from pathlib import Path
from platformdirs import user_config_dir
from dincli.cli.utils import CONFIG_DIR
import torch.nn.init as init
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def initialize_weights(m):
    if isinstance(m, nn.Linear):
        # Initialize weights with Xavier uniform initialization
        init.xavier_uniform_(m.weight)
        # Initialize biases to zero
        if m.bias is not None:
            init.zeros_(m.bias)  

def getGenesisModelIpfs(base_path):

    from model import ModelArchitecture
    model = ModelArchitecture()
    
    #initialize model
    model.apply(initialize_weights)
    
    # Save the trained genesis model to disk
    model_dir = Path(base_path/"models")
    os.makedirs(model_dir, exist_ok=True)
    model_path = model_dir / "genesis_model.pth"
    # 🔑 Convert Path to string for compatibility with torch.save()
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
        

def _select_reserved_pool(
    total_test_samples: int,
    reserved_pool_fraction: float = 0.4,
    seed: int = 0,
) -> torch.Tensor:
    """Deterministically select the task's reserved test-data pool.

    Fixed for the whole task (same `seed` every call, independent of `gi`) so
    "resampling" in `_resample_round_pool` below means something: rounds draw
    fresh subsets of a stable underlying reservation, not of the whole test
    set fresh each time, which is what would let a many-round task leak the
    entire test set to auditors over time. A dedicated `torch.Generator` is
    used (not the global `torch.manual_seed`) so this selection can't be
    perturbed by unrelated torch RNG calls elsewhere in the process.
    """
    generator = torch.Generator().manual_seed(seed)
    pool_size = int(total_test_samples * reserved_pool_fraction)
    return torch.randperm(total_test_samples, generator=generator)[:pool_size]


def _resample_round_pool(
    reserved_pool_indices: torch.Tensor,
    gi: int,
    is_final_round: bool,
    resample_fraction: float = 0.5,
) -> torch.Tensor:
    """Task_210726_6 §2c resampling policy: half the reserved pool per round,
    full reserved pool on the final round.

    Whitepaper §5.2.3b's mitigation for test-set leakage/overfitting when the
    same held-out data is reused across many rounds: expose only a resampled
    half of the ~40% reserved pool (~20% of the full test set) each
    non-final round, and only reveal the complete reserved pool on the round
    the model owner has explicitly signaled as final (no further rounds to
    protect from cumulative exposure). Resampling is seeded by `gi` so each
    round's half is a genuinely fresh draw, not a repeat.
    """
    if is_final_round:
        return reserved_pool_indices
    generator = torch.Generator().manual_seed(gi)
    round_size = int(len(reserved_pool_indices) * resample_fraction)
    round_local_indices = torch.randperm(len(reserved_pool_indices), generator=generator)[:round_size]
    return reserved_pool_indices[round_local_indices]


def create_audit_testDataCIDs(
    batch_counts: int,
    gi: int,
    base_path: Union[str, Path],
    test_data_path: Union[str, Path, None] = None,
    is_final_round: bool = False,
) -> list[str]:
    """
    Create audit datasets by sampling from test data and uploading to IPFS.

    Implements the task_210726_6 §2c resampling policy (`_select_reserved_pool`
    / `_resample_round_pool` above): batches now sample from a per-round
    resampled subset of a fixed ~40% reserved pool, not directly from the
    full test set, bounding cumulative auditor exposure to the held-out data
    across a many-round task.

    Args:
        batch_counts: Number of auditor batches to create
        gi: Generation index for naming datasets AND for seeding this round's
            resample (see `_resample_round_pool`) -- do not pass an arbitrary
            or repeated value here if round-to-round freshness matters.
        base_path: Root directory path (task/workspace directory)
        test_data_path: Optional custom path to test dataset (defaults to base_path/dataset/test/test_dataset.pt)
        is_final_round: True to expose the full reserved pool (no resampling)
            for this round. Defaults to False so the existing dincli call
            site (which does not yet pass this argument -- see
            task_210726_6 PR notes) keeps behaving safely without changes:
            under-exposing the test set is the safe direction to default,
            or a manifest/CLI enhancement to pass the real value is
            follow-up work, not a blocker for this policy landing.

    Returns:
        List of IPFS CIDs for uploaded auditor datasets
    """
    # Normalize paths to Path objects
    base_path = Path(base_path)
    test_data_path = Path(test_data_path) if test_data_path else None

    print("batch_counts", batch_counts)

    # Determine test dataset path
    if test_data_path is None:
        default_test_path = base_path / "dataset" / "test" / "test_dataset.pt"
        if not default_test_path.exists():
            raise FileNotFoundError(
                f"Test dataset not found at {default_test_path.resolve()}"
            )
        test_data = torch.load(default_test_path, weights_only=False)
    else:
        if not test_data_path.exists():
            raise FileNotFoundError(
                f"Test dataset not found at {test_data_path.resolve()}"
            )
        test_data = torch.load(test_data_path, weights_only=False)

    total_test_samples = len(test_data)

    reserved_pool_indices = _select_reserved_pool(total_test_samples)
    round_pool_indices = _resample_round_pool(reserved_pool_indices, gi, is_final_round)

    testData_percentage_per_auditor_batch = 5

    # Number of samples each batch gets, sized off the FULL test set (as
    # before) but never more than the round pool actually has available --
    # relevant when is_final_round=False and the round pool (~20% of total)
    # is smaller than a naive percent-of-total calculation might assume for
    # a very large batch_counts.
    samples_per_batch = int(total_test_samples * (testData_percentage_per_auditor_batch / 100))
    samples_per_batch = min(samples_per_batch, len(round_pool_indices))

    audit_testDataCIDs = []
    audit_dir = base_path / "dataset" / "auditor" / "TestDatasets"
    audit_dir.mkdir(parents=True, exist_ok=True)  # Modern Path-based mkdir

    for batch_id in range(batch_counts):

        generator = torch.Generator().manual_seed(batch_id)

        round_local_indices = torch.randperm(len(round_pool_indices), generator=generator)[:samples_per_batch]
        random_indices = round_pool_indices[round_local_indices]
        assigned_testData = torch.utils.data.Subset(test_data, random_indices)

        # Path-based file handling (no string formatting)
        audit_path = audit_dir / f"auditorDataset_{gi}_{batch_id}.pt"
        torch.save(assigned_testData, audit_path)

        ipfs_hash = upload_to_ipfs(
            str(audit_path),  # Convert to str ONLY for external API
            f"Auditor Dataset for gi_{gi} index {batch_id} uploaded"
        )
        audit_testDataCIDs.append(ipfs_hash)
    return audit_testDataCIDs