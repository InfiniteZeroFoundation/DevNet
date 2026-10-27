# Running Fashion-MNIST CNN on a Local Devnet

`cache_model_1/` is the second end-to-end example model for the DIN Protocol.
It trains a small CNN on [Fashion-MNIST](https://github.com/zalandoresearch/fashion-mnist) — 10 clothing categories, same 28×28 grayscale images as MNIST — and demonstrates that the protocol works with convolutional architectures, not just fully-connected ones.

**Related:** `cache_model_0/` (MNIST reference), `Documentation/public/what-can-be-trained.md`, issue No. 240.

---

## Model architecture

```
Input [batch, 1, 28, 28]
  Conv2d(1 → 32, kernel=3, padding=1)  → ReLU → MaxPool2d(2,2)  [→ 32×14×14]
  Conv2d(32 → 64, kernel=3, padding=1) → ReLU → MaxPool2d(2,2)  [→ 64×7×7]
  Flatten                                                         [→ 3136]
  Linear(3136 → 256)                   → ReLU
  Dropout(0.25)
  Linear(256 → 10)
Output logits over 10 classes
```

Label map: 0 T-shirt/top · 1 Trouser · 2 Pullover · 3 Dress · 4 Coat · 5 Sandal · 6 Shirt · 7 Sneaker · 8 Bag · 9 Ankle boot.

---

## Prerequisites

- Local devnet running (see `Documentation/public/workflows/din-workflow.md`)
- Python environment with `dincli` installed (`pip install -e .` from repo root)
- `torchvision==0.21.0` (included in `cache_model_1/requirements.txt`)

---

## Step 1 — Download the dataset

```bash
python cache_model_1/prepare_dataset.py
```

This downloads the Fashion-MNIST test split (~29 MB) via torchvision and saves it as `cache_model_1/dataset/test/test_dataset.pt`. The file is in the same format as `cache_model_0/dataset/test/test_dataset.pt` so the same `modelowner.py` logic applies unchanged.

The download cache lands in `cache_model_1/dataset/test/_download_cache/` and can be deleted after the first run.

---

## Step 2 — Start a local chain

```bash
./foundry/anvil.sh
```

Leave this running in a separate terminal.

---

## Step 3 — Configure the network

```bash
dincli system configure-network --network local
dincli system register-wallet --account <your_account_id>
```

---

## Step 4 — Deploy task contracts and register the model

Follow the same steps as `cache_model_0` in `Documentation/public/workflows/model-workflow.md`:

1. Deploy `DINTaskCoordinator` and `DINTaskAuditor`.
2. Request slasher authorization for both contracts via `DinCoordinator`.
3. Fill in the deployed addresses in `cache_model_1/manifest.json` under `DINTaskCoordinator_Contract` and `DINTaskAuditor_Contract` (and the matching `task_contracts` block).
4. Upload the service files to IPFS and fill in the CIDs:
   ```bash
   dincli model-owner upload-services --manifest cache_model_1/manifest.json
   ```
5. Generate the genesis model and upload it:
   ```bash
   dincli model-owner genesis --manifest cache_model_1/manifest.json
   ```
   Copy the returned CID into `manifest.json` → `Genesis_Model_CID`.
6. Register the model:
   ```bash
   dincli model-owner register --manifest cache_model_1/manifest.json
   ```

---

## Step 5 — Run a global iteration

Open a GI, register validators, submit local models, run audit scoring, and close the round — identical to the MNIST walkthrough in `Documentation/public/workflows/model-workflow.md`. The only difference is the manifest path:

```bash
dincli model-owner open-gi --manifest cache_model_1/manifest.json --gi 1
# … client trains, auditors score …
dincli model-owner close-gi --manifest cache_model_1/manifest.json --gi 1
```

Each client trains with:

```bash
dincli client train --manifest cache_model_1/manifest.json
```

The `train_client_model` function in `cache_model_1/services/client.py` is identical to the MNIST one: 10 local epochs with Adam, then optional post-training DP if enabled in the manifest. The CNN forward pass handles the 2D feature maps internally; the rest of the training loop is unchanged.

---

## Differential privacy

DP is disabled by default (`dp.enabled: false` in `manifest.json`). To enable post-training Gaussian noise, set:

```json
"dp": {
  "enabled": true,
  "mode": "afterTraining",
  "mechanism": "post_training_gaussian",
  "parameters": {
    "clipping_norm": 10.0,
    "noise_multiplier": 0.5,
    "clip_scope": "global"
  }
}
```

Refer to `Documentation/public/manifest.md` → "Differential Privacy Parameters" for per-mechanism guidance on choosing `clipping_norm`.

---

## Expected accuracy (standalone, no federation)

Training the CNN for 10 epochs on 50 000 Fashion-MNIST images with default Adam (`lr=0.001`) typically reaches ~90 % test accuracy. In a federated setting with a small number of clients and few rounds, expect convergence to be slower; scores above the `min_accuracy: 50.0` threshold in the audit policy are achievable within a handful of GIs.

---

## Differences from `cache_model_0`

| | `cache_model_0` (MNIST) | `cache_model_1` (Fashion-MNIST) |
|---|---|---|
| Architecture | FC: 784→128→64→10 | CNN: Conv×2 + FC×2, see above |
| Dataset | `torchvision.datasets.MNIST` | `torchvision.datasets.FashionMNIST` |
| Dataset prep | committed at `dataset/test/test_dataset.pt` | run `prepare_dataset.py` |
| Services | — | identical (model-agnostic) |
| Manifest | deployed CIDs present | CIDs empty until first deploy |
