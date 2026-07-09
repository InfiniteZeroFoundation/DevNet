from pathlib import Path

import numpy as np
import torch
from torchvision import datasets, transforms


def _load_mnist(dataset_dir: Path):
    """Download (or reuse cached) MNIST and return (train_dataset, test_dataset)."""
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,)),
    ])
    train_dataset = datasets.MNIST(root=dataset_dir, train=True, download=True, transform=transform)
    test_dataset = datasets.MNIST(root=dataset_dir, train=False, download=True, transform=transform)
    return train_dataset, test_dataset


# ---------------------------------------------------------------------------
# Scenario A – save raw train/test datasets
# ---------------------------------------------------------------------------

def save_test_train_datasets(base_dir):
    """
    Download the full MNIST train and test splits and save them as .pt files.

    Saves to:
        <base_dir>/dataset/train/train_dataset.pt
        <base_dir>/dataset/test/test_dataset.pt

    Returns:
        {
            "train_dataset_path": str,
            "test_dataset_path": str,
        }
    """
    base_dir = Path(base_dir)
    dataset_dir = base_dir / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    train_dataset, test_dataset = _load_mnist(dataset_dir)

    train_dir = dataset_dir / "train"
    test_dir = dataset_dir / "test"
    train_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    train_path = train_dir / "train_dataset.pt"
    test_path = test_dir / "test_dataset.pt"
    torch.save(train_dataset, train_path)
    torch.save(test_dataset, test_path)

    return {
        "train_dataset_path": str(train_path),
        "test_dataset_path": str(test_path),
    }


# ---------------------------------------------------------------------------
# Scenario B – IID split of training data across clients
# ---------------------------------------------------------------------------

def distribute_to_clients(base_dir, accounts_list, num_clients, seed=42):
    """
    Perform an IID random split of MNIST training data across N clients.

    Each client receives an equal-sized partition saved as:
        <base_dir>/dataset/clients/<wallet_address>/data.pt

    Args:
        base_dir:      Root directory for this model / task.
        accounts_list: List of wallet addresses (len == num_clients).
        num_clients:   Number of client partitions (1–10).
        seed:          Random seed for reproducibility.

    Returns:
        {
            "client_datasets": [
                {
                    "client_index": int,
                    "account_address": str,
                    "num_samples": int,
                    "path": str,
                },
                ...
            ]
        }
    """
    base_dir = Path(base_dir)
    dataset_dir = base_dir / "dataset"
    clients_dir = dataset_dir / "clients"

    if num_clients is None or num_clients <= 0:
        raise ValueError("num_clients must be >= 1 when clients=True")
    if num_clients > 10:
        raise ValueError("num_clients must be <= 10")
    if len(accounts_list) != num_clients:
        raise ValueError("accounts_list length must match num_clients")

    dataset_dir.mkdir(parents=True, exist_ok=True)
    clients_dir.mkdir(parents=True, exist_ok=True)

    train_dataset, _ = _load_mnist(dataset_dir)

    total_samples = len(train_dataset)
    indices = np.arange(total_samples)
    np.random.seed(seed)
    np.random.shuffle(indices)
    partitions = np.array_split(indices, num_clients)

    client_datasets = []
    for i, idxs in enumerate(partitions):
        client_path = clients_dir / accounts_list[i]
        client_path.mkdir(parents=True, exist_ok=True)
        subset_data = [(train_dataset[idx][0], train_dataset[idx][1]) for idx in idxs]
        save_path = client_path / "data.pt"
        torch.save(subset_data, save_path)
        client_datasets.append({
            "client_index": i,
            "account_address": accounts_list[i],
            "num_samples": len(subset_data),
            "path": str(save_path),
        })

    return {"client_datasets": client_datasets}


# ---------------------------------------------------------------------------
# Scenario C – combined entry point (A + B)
# ---------------------------------------------------------------------------

def distribute_mnist_dataset(
    base_dir,
    accounts_list,
    num_clients=None,
    seed=42,
    test_train=False,
    clients=False,
):
    """
    Convenience wrapper that runs save_test_train_datasets and/or
    distribute_to_clients based on the flags provided.

    Returns a merged dict with keys from both scenario functions:
        {
            "train_dataset_path": str | None,
            "test_dataset_path": str | None,
            "client_datasets": list,
        }
    """
    saved = {
        "train_dataset_path": None,
        "test_dataset_path": None,
        "client_datasets": [],
    }

    if test_train:
        result_a = save_test_train_datasets(base_dir)
        saved["train_dataset_path"] = result_a["train_dataset_path"]
        saved["test_dataset_path"] = result_a["test_dataset_path"]

    if clients:
        result_b = distribute_to_clients(base_dir, accounts_list, num_clients, seed)
        saved["client_datasets"] = result_b["client_datasets"]

    return saved
