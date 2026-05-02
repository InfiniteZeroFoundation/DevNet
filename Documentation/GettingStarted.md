# 🚀 Getting Started with Model_0 on the Infinite Zero Network

Welcome to the onboarding guide for **Model_0** on the Infinite Zero Network.

A **Model Owner** has already deployed the model-specific smart contracts for this pioneer model (`ID: 0`).

* ✅ **Global Iteration 1** has been successfully completed
* 🔄 **Global Iteration 2** is currently in progress

You are invited to participate in **Global Iteration 2 and beyond** by taking on one (or more) of the following roles:

### 🎭 Available Roles

1. **Aggregators**
2. **Auditors**
3. **Clients**

> 💡 You may operate **multiple accounts** and simultaneously participate as a *Client*, *Auditor*, and/or *Aggregator*.

---

## 💻 Compute Requirements

Running a node is lightweight — no specialized hardware required.

### ✅ Minimum Requirements

* **RAM:** 4 GB
* **Disk:** ~30 GB free space
* **CPU:** Standard (no GPU required)
* **Environment:** Python 3 + `venv`

### 📦 Dependencies

* `dincli`: a few MB
* Python dependencies (e.g. PyTorch): ~2 GB

> 💡 If you’ve set up a Python environment before, setup should take ~10–15 minutes.

---

## ❓ Validator vs Miner (Important Clarification)

This system does **not** use traditional mining.

Instead, it uses **role-based participation**:

* **Aggregators** → Aggregate model updates
* **Auditors** → Evaluate and validate models
* **Clients** → Train and submit local models

> 💡 These roles collectively function similarly to **validators** in other networks.

---

## 🌐 Community Channels

### 📢 Telegram Group

Join the Telegram group https://t.me/+I4Tl7foCVwwwM2Vk for:

* Announcements
* Guidance
* Community discussions

> ⚠️ Active updates for **Model_0** are shared regularly — stay engaged.

---

### 🔐 Signal Group

Join the Signal group:
https://signal.group/#CjQKICVqJ0Ri3KGCZOsf8A3dhmg8GC_vc1MBmBrq0JV7lIr6EhBCOwElVHvE0swjO8kSk7ky

* Announcements
* Guidance
* Community discussions

> ⚠️ Active updates for **Model_0** are shared regularly — stay engaged.

---

## ⚙️ DIN CLI Installation and Setup

Before participating, ensure your environment is correctly configured. Please read `setup.md` for full setup instructions.

```bash
# Initialize DIN CLI
dincli system init
```

---

### 🔧 Required Configuration

Set RPC URL in `.env`:

```env
SEPOLIA_OP_DEVNET_RPC_URL=<your_rpc_url>
```

Add Ethereum private keys:

```env
ETH_PRIVATE_KEY_0=...
ETH_PRIVATE_KEY_1=...
```

---

### ✅ Recommended

* Use **Filebase** as your IPFS provider
* See `setup.md` for detailed configuration

---

## 🧩 Aggregators

### Step 1: Explore Model

```bash
dincli task explore 0
```

### Step 2: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 3: Register (if state = `DINaggregatorsRegistrationStarted`)

```bash
dincli system connect-wallet --account 0
dincli system --eth-balance
dincli aggregator dintoken buy 0.00001
dincli aggregator dintoken stake 10
dincli aggregator dintoken read-stake
dincli aggregator register 0
```

---

### Step 4: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 5: Check your Aggregation Batch (if state = `T1nT2Bcreated`)

```bash
dincli model-owner aggregation show-t1-batches 0 --detailed
dincli model-owner aggregation show-t2-batches 0 --detailed
```

---

### Step 6: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 7: Aggregate your T1 Batch (if state = `T1AggregationStarted`)

```bash
dincli aggregator show-t1-batches 0 --detailed
dincli aggregator aggregate-t1 0 --submit
```

---

### Step 8: Aggregate your T2 Batch (if state = `T2AggregationStarted`)

```bash
dincli aggregator show-t2-batches 0 --detailed
dincli aggregator aggregate-t2 0 --submit
```

---

## 🛡️ Auditors

### Step 1: Explore Model

```bash
dincli task explore 0
```

### Step 2: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 3: Register (if state = `DINauditorsRegistrationStarted`)

```bash
dincli system connect-wallet --account 0
dincli system --eth-balance
dincli auditor dintoken buy 0.00001
dincli auditor dintoken stake 10
dincli auditor dintoken read-stake
dincli auditor register 0
```

---

### Step 4: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 5: Check your Auditor Batch (if state = `AuditorsBatchesCreated`)

```bash
dincli auditor lms-evaluation show-batch 0
```

> 💡 If a batch appears, you will soon be required to evaluate it.

---

### Step 6: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 7: Audit your assigned batch (if state = `LMSevaluationStarted`)

```bash
dincli auditor lms-evaluation show-batch 0
dincli auditor lms-evaluation evaluate 0 --submit
```

---

## 🤖 Clients

### Step 1: Explore Model

```bash
dincli task explore 0
```

### Step 2: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 3: Submit Local Model (if state = `LMSstarted`)

```bash
dincli system connect-wallet --account 0
dincli system --eth-balance
dincli client train-lms 0 --submit
dincli client lms show-models 0
```

---

### 💡 Optional (Recommended First Step)

```bash
dincli client train-lms 0
```

---

## 📂 Dataset Requirements

Dataset must be located at:

```
<CACHE_DIR>/sepolia_op_devnet/model_0/dataset/clients/<account_address>/data.pt
```

Find cache directory:

```bash
dincli system get-cache-dir
```

---

## 📊 MNIST Dataset Distribution

Model_0 uses the **MNIST dataset**, integrated into `dincli`.

### 📦 Distribute Dataset

```bash
dincli system dataset distribute-mnist \
  --seed <seed> \
  --model-id <model-id> \
  --test-train \
  --clients \
  --num-clients <num-clients> \
  --start-client-index <start-client-index>
```

---

### 📌 Parameters

| Argument               | Description                         |
| ---------------------- | ----------------------------------- |
| `--seed`               | Random seed for shuffling           |
| `--model-id`           | Creates model directory             |
| `--test-train`         | Creates dataset directory           |
| `--clients`            | Enables client dataset distribution |
| `--num-clients`        | Number of participating clients     |
| `--start-client-index` | Starting wallet index               |

---

### ✅ Example

```bash
dincli system dataset distribute-mnist \
  --seed 42 \
  --model-id 0 \
  --test-train \
  --clients \
  --num-clients 9 \
  --start-client-index 0
```

---

## ⚠️ Account Indexing Requirement

Ensure sufficient keys in `.env`.

### Formal Requirement

```
MAX_INDEX ≥ start-client-index + num-clients - 1
```

### Interpretation

* Clients are assigned sequentially
* Total required keys = `num-clients`

### Example

If:

* `start-client-index = 2`
* `num-clients = 9`

Then:

```
ETH_PRIVATE_KEY_2 → ETH_PRIVATE_KEY_10
```

---

## 🧠 Final Notes

* Always verify **Global Iteration State** before acting
* You can run multiple roles and accounts
* Stay active in community channels for updates

---

> 🚀 You are now ready to participate in **Model_0** and contribute to decentralized AI on the Infinite Zero Network.
