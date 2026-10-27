"""Download Fashion-MNIST test dataset and save it for cache_model_1.

Run once from the repo root before starting a local devnet round:

    python cache_model_1/prepare_dataset.py

The script requires torchvision (included in requirements.txt).
It saves dataset/test/test_dataset.pt in the same format as
cache_model_0/dataset/test/test_dataset.pt so that modelowner.py,
auditor.py and scoring.py can load it without changes.

Fashion-MNIST label map (same 10-class structure as MNIST):
    0 T-shirt/top   1 Trouser      2 Pullover    3 Dress      4 Coat
    5 Sandal        6 Shirt        7 Sneaker     8 Bag        9 Ankle boot
"""

import sys
from pathlib import Path

try:
    import torchvision
    import torchvision.transforms as transforms
except ImportError:
    print("torchvision is required. Install it with: pip install torchvision==0.21.0")
    sys.exit(1)

DEST = Path(__file__).resolve().parent / "dataset" / "test" / "test_dataset.pt"


def main():
    DEST.parent.mkdir(parents=True, exist_ok=True)

    transform = transforms.Compose([transforms.ToTensor()])
    dataset = torchvision.datasets.FashionMNIST(
        root=str(DEST.parent / "_download_cache"),
        train=False,
        download=True,
        transform=transform,
    )

    import torch
    torch.save(dataset, str(DEST))
    print(f"Saved {len(dataset)} samples to {DEST}")


if __name__ == "__main__":
    main()
