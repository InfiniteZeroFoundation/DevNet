"""Prepare Fashion-MNIST client training data for a local devnet round.

Downloads the Fashion-MNIST *training* split (60 000 samples) and partitions
it into equal subsets — one per client account — placing each partition at the
path that ``dincli client train-lms`` expects:

    <CACHE_DIR>/<network>/model_<model_id>/dataset/clients/<account>/data.pt

where ``CACHE_DIR`` is the dincli user-cache directory (``~/Library/Caches/dincli``
on macOS; ``~/.cache/dincli`` on Linux).

Usage
-----
Partition across three client accounts on the local network, model 1:

    python cache_model_1/prepare_training_data.py \\
        --model-id 1 \\
        --network local \\
        --accounts 0xAlice 0xBob 0xCarol

For a single client (full training set, no partition):

    python cache_model_1/prepare_training_data.py \\
        --model-id 1 \\
        --accounts 0xAlice

Training data is kept separate from the test holdout produced by
``prepare_dataset.py``.  The test split lives at:

    <CACHE_DIR>/<network>/model_<model_id>/dataset/test/test_dataset.pt

and is placed there by ``dincli model-owner auditor-batches create-testdataset``,
which calls ``modelowner.py``'s ``getTestDataForAuditing`` function.
"""

import argparse
import sys
from pathlib import Path

try:
    import torch
    import torchvision
    import torchvision.transforms as transforms
    from torch.utils.data import Subset
except ImportError:
    print("torch and torchvision are required.  Install: pip install torch torchvision")
    sys.exit(1)

try:
    from platformdirs import user_cache_dir
except ImportError:
    print("platformdirs is required.  Install: pip install platformdirs")
    sys.exit(1)


def _cache_dir() -> Path:
    return Path(user_cache_dir("dincli"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare Fashion-MNIST client training datasets for dincli."
    )
    parser.add_argument(
        "--model-id",
        type=int,
        required=True,
        help="Registered model ID assigned by dincli task model-owner register.",
    )
    parser.add_argument(
        "--network",
        default="local",
        help="Network name (default: local).  Use 'sepolia_op_devnet' for Sepolia.",
    )
    parser.add_argument(
        "--accounts",
        nargs="+",
        required=True,
        metavar="ADDRESS",
        help="One or more client wallet addresses.  The training set is split "
             "evenly across the provided accounts.",
    )
    args = parser.parse_args()

    transform = transforms.Compose([transforms.ToTensor()])
    download_cache = Path(__file__).resolve().parent / "dataset" / "train" / "_download_cache"
    download_cache.mkdir(parents=True, exist_ok=True)

    print("Downloading Fashion-MNIST training split (60 000 samples) …")
    full_train = torchvision.datasets.FashionMNIST(
        root=str(download_cache),
        train=True,
        download=True,
        transform=transform,
    )

    n = len(full_train)
    k = len(args.accounts)
    per_client = n // k

    indices = list(range(n))
    base_dir = _cache_dir() / args.network / f"model_{args.model_id}" / "dataset" / "clients"

    for i, account in enumerate(args.accounts):
        start = i * per_client
        end = start + per_client if i < k - 1 else n  # last client gets any remainder
        subset = Subset(full_train, indices[start:end])

        dest_dir = base_dir / account
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "data.pt"
        torch.save(subset, str(dest))
        print(f"  [{i+1}/{k}] {len(subset)} samples → {dest}")

    print("Done.")


if __name__ == "__main__":
    main()
