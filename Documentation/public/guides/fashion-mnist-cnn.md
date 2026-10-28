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
Output logits over 10 classes (824 458 parameters)
```

Label map: 0 T-shirt/top · 1 Trouser · 2 Pullover · 3 Dress · 4 Coat · 5 Sandal · 6 Shirt · 7 Sneaker · 8 Bag · 9 Ankle boot.

### CNN forward smoke check

```python
>>> import torch
>>> from cache_model_1.services.model import ModelArchitecture
>>> torch.manual_seed(42)
>>> model = ModelArchitecture(); model.eval()
>>> x = torch.randn(4, 1, 28, 28)
>>> with torch.no_grad(): out = model(x)
>>> out.shape
torch.Size([4, 10])
>>> out[0, :5].tolist()
[0.09661, 0.10927, -0.01073, -0.09551, 0.01840]   # random-init logits, seed 42
>>> out.argmax(dim=1).tolist()
[9, 8, 7, 9]
>>> sum(p.numel() for p in model.parameters())
824458
```

Output shape `[4, 10]` and parameter count `824 458` confirm correct wiring of both convolutional stages and the fully-connected head.

---

## Prerequisites

- Local devnet running (see `Documentation/public/workflows/din-workflow.md`)
- Python environment with `dincli` installed (`pip install -e .` from repo root)
- `torchvision==0.21.0` (included in `cache_model_1/requirements.txt`)

---

## Step 1 — Download the test dataset

The test split is used by the model owner and auditors to score submitted local
models.  Download it once before starting the devnet round:

```bash
python cache_model_1/prepare_dataset.py
```

This saves 10 000 test samples to `cache_model_1/dataset/test/test_dataset.pt`.
The model owner must copy (or re-save) this file into the dincli cache before
running `model submit-genesis` (see Step 5):

```bash
# find the cache dir
dincli system get-cache-dir
# example output: /Users/<you>/Library/Caches/dincli

# place test dataset at the expected path (substitute your network and model_id)
CACHE=$(dincli system get-cache-dir)
mkdir -p "$CACHE/local/model_1/dataset/test"
cp cache_model_1/dataset/test/test_dataset.pt "$CACHE/local/model_1/dataset/test/"
```

> [!NOTE]
> `model_1` here is a placeholder — the real model ID is assigned only after
> `dincli task model-owner register` completes in Step 6.  Repeat this copy
> step once you know the ID.

---

## Step 2 — Prepare client training data

Each client needs a separate training-split partition placed in the dincli
cache.  `prepare_training_data.py` downloads the Fashion-MNIST training split
(60 000 samples) and splits it evenly across the specified client accounts:

```bash
python cache_model_1/prepare_training_data.py \
    --model-id <MODEL_ID> \
    --network local \
    --accounts <CLIENT_WALLET_ADDRESS_1> <CLIENT_WALLET_ADDRESS_2>
```

Each partition is saved at:

```
<CACHE_DIR>/local/model_<MODEL_ID>/dataset/clients/<CLIENT_WALLET_ADDRESS>/data.pt
```

Run this after you have the model ID from Step 6.  Keep the training partitions
and the test holdout (`dataset/test/`) separate — the test set must never be
used for training.

---

## Step 3 — Start a local chain

```bash
./foundry/anvil.sh
```

Leave this running in a separate terminal.

---

## Step 4 — Configure the network and wallet

```bash
dincli system configure-network --network local
dincli system register-wallet --account <your_account_id>
```

---

## Step 5 — Deploy task contracts

From your project root (the directory where `dincli` stores tasks):

```bash
# deploy DINTaskCoordinator
dincli model-owner deploy task-coordinator \
    --artifact "hardhat/artifacts/contracts/DINTaskCoordinator.sol/DINTaskCoordinator.json"

# deploy DINTaskAuditor
dincli model-owner deploy task-auditor \
    --artifact "hardhat/artifacts/contracts/DINTaskAuditor.sol/DINTaskAuditor.json"
```

Both contract addresses are written to your local `.env` file.  Request
slasher authorization from the DIN-Representative before proceeding
(see step 3 in `Documentation/public/workflows/model-workflow.md`).

---

## Step 6 — Set up the task directory and manifest

Create the task directory under the project root:

```bash
dincli model-owner task create-task-dir --taskCoordinator <TASK_COORDINATOR_ADDRESS>
```

This creates:

```
tasks/local/<TASK_COORDINATOR_ADDRESS>/
```

Copy the cache_model_1 service files and manifest into it:

```bash
TASK_DIR="tasks/local/<TASK_COORDINATOR_ADDRESS>"

cp cache_model_1/manifest.json             "$TASK_DIR/manifest.json"
mkdir -p "$TASK_DIR/services"
cp cache_model_1/services/*.py             "$TASK_DIR/services/"
```

Upload each service file to IPFS and update the manifest CIDs:

```bash
dincli ipfs upload -f "$TASK_DIR/services/model.py"
dincli ipfs upload -f "$TASK_DIR/services/client.py"
dincli ipfs upload -f "$TASK_DIR/services/modelowner.py"
dincli ipfs upload -f "$TASK_DIR/services/auditor.py"
dincli ipfs upload -f "$TASK_DIR/services/aggregator.py"
```

Fill the returned CIDs into the corresponding `"ipfs"` fields in
`$TASK_DIR/manifest.json`.  Also fill in `DINTaskCoordinator_Contract` and
`DINTaskAuditor_Contract` with the deployed addresses from Step 5.

---

## Step 7 — Create and submit the genesis model

```bash
dincli model-owner model create-genesis
```

The command calls `getGenesisModelIpfs` from `modelowner.py`, uploads the
model to IPFS, and stores the resulting CID in your `.env` file.  Copy the
CID into `Genesis_Model_CID` in the manifest, then submit the genesis model
score:

```bash
dincli model-owner model submit-genesis
```

`submit-genesis` loads the test dataset from
`<CACHE_DIR>/local/model_1/dataset/test/test_dataset.pt` (adjust the path
once you know your model ID).

---

## Step 8 — Register the model

```bash
dincli task model-owner register --isOpenSource false
```

`dincli` assigns a model ID (e.g. `1`) which is printed to the console.
Record it — you will use it in every subsequent command.  Update the manifest
with the model ID and re-upload it to IPFS:

```bash
dincli task model-owner update-manifest <MODEL_ID> \
    --manifestpath "$TASK_DIR/manifest.json"
```

Then place the test dataset and client training data at the correct cache
paths as described in Steps 1 and 2, substituting the real model ID.

---

## Step 9 — Run a global iteration

A complete GI follows the same phase sequence as `cache_model_0`.  The
commands are identical; only the model ID differs.

**Model owner — open the round:**

```bash
dincli model-owner gi start <MODEL_ID>
dincli model-owner gi reg aggregators-open <MODEL_ID>
# … aggregators register …
dincli model-owner gi reg aggregators-close <MODEL_ID>
dincli model-owner gi reg auditors-open <MODEL_ID>
# … auditors register …
dincli model-owner gi reg auditors-close <MODEL_ID>
dincli model-owner lms open <MODEL_ID>
```

**Clients — train and submit (repeat for each client wallet):**

```bash
dincli client train-lms <MODEL_ID> --submit
```

The client service loads Fashion-MNIST training data from
`<CACHE_DIR>/local/model_<MODEL_ID>/dataset/clients/<CLIENT_ADDRESS>/data.pt`,
trains the CNN for 10 epochs with Adam, and (if DP is enabled in the manifest)
applies post-training noise before uploading the local model to IPFS.

**Model owner — evaluate, aggregate, and close:**

```bash
dincli model-owner lms close <MODEL_ID>
dincli model-owner auditor-batches create <MODEL_ID>
dincli model-owner auditor-batches create-testdataset <MODEL_ID> --submit
dincli model-owner lms-evaluation start <MODEL_ID>
# … auditors evaluate …
dincli model-owner lms-evaluation close <MODEL_ID>
dincli model-owner aggregation create-t1nt2-batches <MODEL_ID>
# … aggregators aggregate …
dincli model-owner gi end <MODEL_ID>
```

For the full step-by-step including aggregator and auditor commands, see
`Documentation/public/workflows/model-workflow.md`.

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

`post_training_gaussian` and `post_training_laplace` are **experimental** — they
carry no formal privacy guarantee (see `Documentation/technical/services/clients.md`
for the F4/F5 caveats).  Use `update_gaussian` for a mechanism with a defined
sensitivity bound.

Refer to `Documentation/public/manifest.md` → "Differential Privacy Parameters"
for per-mechanism guidance on choosing `clipping_norm`.

---

## Expected accuracy (standalone, no federation)

Training the CNN for 10 epochs on 50 000 Fashion-MNIST images with default
Adam (`lr=0.001`) typically reaches ~90 % test accuracy.  In a federated
setting with a small number of clients and few rounds, expect convergence to
be slower; scores above the `min_accuracy: 50.0` threshold in the audit
policy are achievable within a handful of GIs.

---

## Differences from `cache_model_0`

| | `cache_model_0` (MNIST) | `cache_model_1` (Fashion-MNIST) |
|---|---|---|
| Architecture | FC: 784→128→64→10 | CNN: Conv×2 + FC×2, 824 458 params |
| Dataset | `torchvision.datasets.MNIST` | `torchvision.datasets.FashionMNIST` |
| Test dataset prep | committed at `dataset/test/test_dataset.pt` | run `prepare_dataset.py` |
| Training data prep | manual | run `prepare_training_data.py` |
| Services | — | identical (model-agnostic copies) |
| Manifest | deployed CIDs present | CIDs empty until first deploy |
