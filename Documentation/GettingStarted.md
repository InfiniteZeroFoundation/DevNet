
# 🚀 Getting Started with Model_0 on the Infinite Zero Network

Welcome to the onboarding guide for **Model_0** on the Infinite Zero Network.

A **Model Owner** has already deployed the model-specific smart contracts for this pioneer model (`ID: 0`).  
- ✅ **Global Iteration 1** has been successfully completed  
- 🔄 **Global Iteration 2** is currently in progress  

You are invited to participate in **Global Iteration 2 and beyond** by taking on one (or more) of the following roles:

### 🎭 Available Roles
1. **Aggregators**
2. **Auditors**
3. **Clients**

> 💡 You may operate **multiple accounts** and simultaneously participate as a *Client*, *Auditor*, and/or *Aggregator*.

---

## 🌐 Community Channels

### 📢 Telegram Group
Join the Telegram group [https://t.me/+I4Tl7foCVwwwM2Vk](https://t.me/+I4Tl7foCVwwwM2Vk) for:
- Announcements  
- Guidance  
- Community discussions  

> ⚠️ Active updates for **Model_0** are shared regularly — stay engaged.

---

### 🔐 Signal Group
Join the Signal group for:
- Announcements  
- Guidance  
- Community discussions  

> ⚠️ Active updates for **Model_0** are shared regularly — stay engaged.

---

## ⚙️ Initial Setup

Before participating, ensure your environment is correctly configured:

```bash
# Initialize DIN CLI
dincli system init
````

### 🔧 Required Configuration

* Set RPC URL in `.env`:

  ```env
  SEPOLIA_OP_DEVNET_RPC_URL=<your_rpc_url>
  ```

* Add multiple Ethereum private keys:

  ```env
  ETH_PRIVATE_KEY_0=...
  ETH_PRIVATE_KEY_1=...
  ```

* Recommended:

  * Use **Filebase** as your IPFS provider (see [setup.md](setup.md) for details)

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
# Connect wallet (example: account index 0)
dincli system connect-wallet --account 0

# Check ETH balance
dincli system --eth-balance

# Buy DIN tokens
dincli aggregator dintoken buy 0.00001

# Stake tokens
dincli aggregator dintoken stake 10

# Verify stake
dincli aggregator dintoken read-stake

# Register as aggregator
dincli aggregator register 0
```

### Step 4: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 5: Check your Aggregation Batch (if state = `T1nT2Bcreated`)

```bash
# Check T1 batch assigned to you
dincli model-owner aggregation show-t1-batches 0 --detailed

# Check T2 batch assigned to you
dincli model-owner aggregation show-t2-batches 0 --detailed
```
---

### Step 6: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 7: Aggregate your T1 Batch (if state = `T1AggregationStarted`)

```bash
# show the aggregator its assigned t1 batches
dincli aggregator show-t1-batches 0 --detailed
# aggregate the assigned t1 batches
dincli aggregator aggregate-t1 0 --submit
```

### Step 8: Aggregate your T2 Batch (if state = `T2AggregationStarted`)

```bash
# show the aggregator its assigned t2 batches
dincli aggregator show-t2-batches 0 --detailed
# aggregate the assigned t2 batches
dincli aggregator aggregate-t2 0 --submit
```


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
# Connect wallet
dincli system connect-wallet --account 0

# Check ETH balance
dincli system --eth-balance

# Buy DIN tokens
dincli auditor dintoken buy 0.00001

# Stake tokens
dincli auditor dintoken stake 10

# Verify stake
dincli auditor dintoken read-stake

# Register as auditor
dincli auditor register 0
```

### Step 4: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 5: Check your Auditor Batch (if state = `AuditorsBatchesCreated`)

```bash 
dincli auditor lms-evaluation show-batch 0
```
if a Auditor Batch is shown, be ready you will soon be required to audit a auditor batch that is a set of local models have already be assigned to you for auditing.

### Step 6: Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Step 7: Audit your assigned batch  (if state = `LMSevaluationStarted`)

```bash
# check your assigned batch
dincli auditor lms-evaluation show-batch 0
# Audit your batch, just run the command
# all scripts are automatically executed
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
# Connect wallet
dincli system connect-wallet --account 0

# Check ETH balance
dincli system --eth-balance

# Train and submit local model
dincli client train-lms 0 --submit

# shows your submitted local model 
# for current global iteration
# for model_0
dincli client lms show-models 0
```

### 💡 Optional (Recommended First Step)

```bash
# Train locally without submitting 
dincli client train-lms 0
```


### 📂 Dataset Requirements

Ensure your dataset is located at:

```
<CACHE_DIR>/sepolia_op_devnet/model_0/dataset/clients/<account_address>/data.pt
```

Find your cache directory:

```bash
dincli system get-cache-dir
```

---

## 📊 MNIST Dataset Distribution

Model_0 uses the **MNIST dataset**, which is integrated into `dincli`.

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

### 📌 Parameters

| Argument               | Description                         |
| ---------------------- | ----------------------------------- |
| `--seed`               | Random seed for shuffling           |
| `--model-id`           | Creates model directory             |
| `--test-train`         | Creates dataset directory          |
| `--clients`            | Enables client dataset distribution |
| `--num-clients`        | Number of participating clients     |
| `--start-client-index` | Starting wallet index               |



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

### ⚠️ Account Indexing Requirement 


To ensure proper client mapping, your `.env` must include sufficient Ethereum private keys. Let `ETH_PRIVATE_KEY_<MAX_INDEX>` be the last private key entry in `.env`

#### 📐 Formal Requirement

```
MAX_INDEX ≥ start-client-index + num-clients - 1
```

#### 🧠 Interpretation

* Clients are assigned **sequentially and inclusively**
* Total keys required = `num-clients`
* Index range:

```
[start-client-index, start-client-index + num-clients - 1]
```

#### 📌 Example

If:

* `start-client-index = 2`
* `num-clients = 9`

Then:

```
MAX_INDEX ≥ 10
```

Required keys:

```
ETH_PRIVATE_KEY_2 → ETH_PRIVATE_KEY_10
```


---

## 🧠 Final Notes

* Always verify the **Global Iteration State** before taking action
* Use multiple accounts strategically for different roles
* Stay active in community channels for updates

---

> 🚀 You are now ready to participate in **Model_0** and contribute to decentralized AI on the Infinite Zero Network.



