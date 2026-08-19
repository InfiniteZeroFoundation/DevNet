# Model_0 — Infinite Zero Network Protocol

Welcome to the onboarding guide for **Model_0** on the Infinite Zero Network.

Infinite Zero Network devnet has been launched as `sepolia-op-devnet`.

Model_0 is the first active model registered on the Infinite Zero Network and serves as the
pioneer deployment of Infinite Zero's model-specific smart contracts.

The Infinite Zero Network coordinates decentralised AI training, auditing, aggregation, and
validation through Ethereum smart contracts, off-chain distributed compute, and
decentralised storage.

---

# 🧭 Protocol Overview

Model_0 operates through recurring **Global Iterations (GI)**.

Each Global Iteration represents a complete decentralised training cycle coordinated by
Ethereum smart contracts.

A typical iteration includes:

1. Clients train local models on their own datasets
2. Local model updates are submitted to IPFS and referenced on-chain
3. Auditors independently evaluate the submitted local models and approve (or reject) them
4. Approved local models are batched and assigned to aggregators for aggregation
5. Aggregators aggregate assigned T1 and subsequently T2 aggregation batches
6. The resulting global model is finalised and published
7. The next iteration begins using the updated global model

This process enables decentralised, verifiable, and scalable collaborative AI training
without centralising participant data.

---

# 🌐 What is `sepolia-op-devnet`?

To simplify onboarding, we refer to our devnet as:

> **`sepolia-op-devnet` = Optimism Sepolia testnet + DIN deployed contracts**

So when you see:

```env
SEPOLIA_OP_DEVNET_RPC_URL=YOUR_RPC_URL
```

It means:

- You are connecting to **Optimism Sepolia**
- And interacting specifically with **DIN protocol contracts deployed there**

---

# Current Status

- ✅ Global Iteration 1 completed
- 🔄 Global Iteration 2 in progress

---

# 🔐 Security Model

The Infinite Zero Network is secured by Ethereum smart contracts deployed on Sepolia OP
Devnet.

Ethereum acts as the source of truth for:

- Participant registration
- State transitions
- Submission coordination
- Staking logic
- Validation rules
- Protocol enforcement

### On-chain responsibilities

| Layer               | Responsibility                               |
| ------------------- | -------------------------------------------- |
| Ethereum (on-chain) | Coordination, state, validation, enforcement |
| IPFS/Filebase       | Model artifacts and decentralised storage    |
| Off-chain compute   | Training, aggregation, auditing              |
| Participants        | Execute computation and submit results       |

---

### Core guarantee

The system is **fully verifiable end-to-end**:

- Ethereum enforces correctness, coordination, and finality
- IPFS ensures reproducible and distributed data availability
- Off-chain compute enables scalable ML execution

> 💡 Trust is shifted from participants to cryptographic and economic enforcement.

# 📦 Data Availability Layer (IPFS via Filebase)

The protocol uses IPFS (recommended through Filebase) as a decentralised storage layer for
protocol artifacts.

This includes:

- Local model uploads
- Aggregated/global model artifacts
- Manifest or scripts artifacts
- Aggregation outputs

---

# 🎭 Participation Model

Participants may operate as one or more of the following roles simultaneously:

1. **Aggregators** — Aggregate Tier 1 and Tier 2 batches of models
2. **Auditors** — Independently evaluate the submitted local models and approve (or
   reject) them
3. **Clients** — Train local models on local datasets and submit local model updates to
   the network

> 💡 A single participant may act as Client, Auditor, and Aggregator simultaneously using
> multiple accounts.

---

# 🧠 Validator Model (No Mining)

This system does not use mining or Proof-of-Work.

Instead, it uses a role-based validation model coordinated through Ethereum smart
contracts on `sepolia-op-devnet`.

- Clients train and submit local model updates
- Auditors independently evaluate the submitted local models and approve (or reject) them
- Approved model updates are batched and assigned to aggregators
- Aggregators aggregate assigned T1 and subsequently T2 aggregation batches
- Ethereum finalises accepted protocol state transitions

> 💡 Aggregators and Auditors collectively function as validators.

---

# 💻 System Requirements

Participating in Model_0 on the Infinite Zero Network is lightweight and does not require
specialised hardware.

### Minimum Requirements

- RAM: 4 GB
- Disk: ~15 GB
- CPU: Standard CPU (GPU not required)
- Python 3 + virtual environment

### Dependencies

- `dincli`
- Python ML/runtime dependencies (~5 GB virtual environment)

> 💡 Once the `.env`, wallet, RPC, and IPFS are configured and the address is funded,
> role registration takes 2–3 minutes.

---

# ⚠️ Current Devnet Scope

The current devnet primarily focuses on:

- Decentralised coordination
- Distributed training
- Aggregation workflows
- Validation workflows
- Ethereum-enforced protocol state transitions

Staking and slashing concepts exist within the protocol architecture.

The slashing enforcement path on the currently deployed contracts is **non-functional**
and under remediation. The intended duties and penalties are documented in the role
sections below; the caveats described there apply to every mention of slashing in this
document.

Economic and reward distribution mechanisms are still under active development and are
not yet the primary focus of the current devnet phase.

---

# 🌐 Community Channels

### Telegram

- Announcements
- Coordination
- Community support

https://t.me/+I4Tl7foCVwwwM2Vk

### Signal

- Technical discussions
- Coordination
- Protocol updates

https://signal.group/#CjQKICVqJ0Ri3KGCZOsf8A3dhmg8GC_vc1MBmBrq0JV7lIr6EhBCOwElVHvE0swjO8kSk7ky

> ⚠️ Global Iteration updates and onboarding assistance are shared regularly.

---

## Faucet Access (Sepolia Optimism)

To participate in the Infinite Zero Network devnet, you will need **Optimism Sepolia ETH**
for transaction fees.

> [!IMPORTANT]
> The DIN contracts are on **Optimism Sepolia (L2, chain 11155420)**, not Ethereum Sepolia
> (L1, chain 11155111). Ethereum Sepolia ETH **cannot** pay `dincli` transactions — it
> must be bridged to Optimism Sepolia first (see `Documentation/setup.md` §8.2). The two
> chains differ by one URL path segment; sending to the wrong one costs a faucet cooldown.

You can request testnet tokens from the following official faucets:

- [Optimism Faucet](https://console.optimism.io/faucet)
- [Chainlink Faucet (Optimism Sepolia)](https://faucets.chain.link/optimism-sepolia)
- [LearnWeb3 Faucet](https://learnweb3.io/faucets/optimism_sepolia/)
- [ETHGlobal OP Sepolia Faucet](https://ethglobal.com/faucet/op-sepolia-11155420)
- [Alchemy Optimism Sepolia Faucet](https://www.alchemy.com/faucets/optimism-sepolia)

> [!WARNING]
> As of August 2026, all of the above require connecting a browser wallet (MetaMask,
> Coinbase, WalletConnect, or similar), and several demand mobile verification. A
> headless server operator may not be able to self-fund through any of them.

### Fund on Ethereum Sepolia, then Bridge

If the direct faucets do not work, fund on **Ethereum Sepolia (L1)**, where faucets are
less gated, then bridge to Optimism Sepolia. The full procedure — including funding
sources, bridge address, preflight checks, and gas guidance — is in
`Documentation/setup.md` §8.

A non-exhaustive funding source for L1:

- [Google Cloud Web3 Faucet — Ethereum Sepolia](https://cloud.google.com/application/web3/faucet/ethereum/sepolia)

Funds arrive on **chain 11155111** and must be bridged to **11155420**.

If you are unable to obtain funds through faucets or bridging, you may also request
Sepolia Optimism ETH through the Infinite Zero Foundation Telegram and Signal community
groups.

---

# ⚙️ DIN CLI Installation and Setup

Before participating, ensure `dincli` is correctly installed and configured.

Please read: [Documentation/setup.md](https://github.com/InfiniteZeroFoundation/DevNet/blob/main/Documentation/setup.md)

The setup guide covers installation, virtual environment, `.env` creation, wallet
connection, RPC configuration, IPFS setup, funding, and a readiness checklist.

Once you have completed the readiness checklist, you are ready for the role-specific
sections below.

---

## Prerequisites for all roles

Before entering any of the role sections below, confirm:

- Demo mode is off: `dincli system configure-demo --mode no`
- Wallet is connected and the address matches the funded address
- RPC chain ID is 11155420
- ETH balance is non-zero: `dincli system --eth-balance`
- Manifest retrieval works: `dincli task explore 0 --update`

The full readiness checklist, with verification commands, is at the end of `setup.md`.

---

# 🧩 Aggregators

### Prerequisites

Complete the shared setup in `Documentation/setup.md` and the readiness checklist above.
Specifically: **`configure-demo --mode no`**, wallet connected via
`connect-wallet --account N`, RPC chain ID confirmed 11155420, ETH balance non-zero,
and IPFS provider configured and verified.

### Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Buy and Stake DIN Tokens

**How much to buy.** At the current rate of 1,000,000 DIN per ETH:

| ETH spent | DIN minted | Notes |
|---|---|---|
| `0.00001` | 10 DIN | Exactly `MIN_STAKE`. Works, but leaves **zero margin** — any rate change or rounding leaves you unable to stake |
| `0.0001` | ~100 DIN | Recommended. Leaves a liquid reserve for re-staking or a second account |

> [!NOTE]
> The rate (`dinPerEth` on `DinCoordinator`) is owner-mutable, so these amounts hold only
> at the current rate. Check it yourself before buying:
> ```bash
> dincli aggregator dintoken read-din-per-eth
> ```
> The values above were confirmed against the deployed contract in August 2026.

```bash
# Buy DIN tokens (see the table above before choosing an amount)
dincli aggregator dintoken buy 0.0001

# Stake tokens — stake() currently ignores the amount argument and always
# stakes MIN_STAKE (10 DIN). Extra DIN stays liquid; it is not a bigger stake.
dincli aggregator dintoken stake 10

# Verify stake
dincli aggregator dintoken read-stake
```

### Register (if state = `DINaggregatorsRegistrationStarted`)

```bash
dincli aggregator register 0
```

### Check your Aggregation Batch (if state = `T1nT2Bcreated`)

```bash
# Check T1 batch assigned to you
dincli model-owner aggregation show-t1-batches 0 --detailed

# Check T2 batch assigned to you
dincli model-owner aggregation show-t2-batches 0 --detailed
```

### Aggregate your T1 Batch (if state = `T1AggregationStarted`)

```bash
# Show the aggregator its assigned T1 batches if assigned
dincli aggregator show-t1-batches 0 --detailed

# Aggregate the assigned T1 batches
dincli aggregator aggregate-t1 0 --submit
```

### Aggregate your T2 Batch (if state = `T2AggregationStarted`)

```bash
# Show the aggregator its assigned T2 batches if assigned
dincli aggregator show-t2-batches 0 --detailed

# Aggregate the assigned T2 batches
dincli aggregator aggregate-t2 0 --submit
```

> 💡 T1 and T2 batch assignments depend on the current Global Iteration state and
> protocol allocation logic. A registered aggregator may not receive a batch in every
> iteration.

### Slashing

Non-submission, or submitting a CID that differs from the finalised batch CID, violates
the intended aggregator duty and is intended to be slashable for the full `minStake()`.
Enforcement on the currently deployed contracts is **non-functional** and under
remediation — `slashAggregators` reverts because the coordinator's `minStake` value is
below the staking contract's `MIN_STAKE` floor.

The real present-tense consequence of a missed or divergent submission is that
`slashAggregators` cannot produce the `AggregatorsSlashed` state, and `endGI` requires
exactly that state — so **the Global Iteration cannot be ended at all**. What happens
when a GI is wedged is not a slashing question; it is a protocol-liveness question and
is still under discussion.

---

# 🛡️ Auditors

### Prerequisites

Complete the shared setup in `Documentation/setup.md` and the readiness checklist above.
Specifically: **`configure-demo --mode no`**, wallet connected via
`connect-wallet --account N`, RPC chain ID confirmed 11155420, ETH balance non-zero,
and IPFS provider configured and verified.

### Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Buy and Stake DIN Tokens

The amounts work exactly as in the Aggregators section above: `0.00001` ETH mints 10 DIN
(exactly `MIN_STAKE`, no margin), `0.0001` mints ~100 DIN and leaves a liquid reserve.

```bash
# Buy DIN tokens
dincli auditor dintoken buy 0.0001

# Stake tokens — stake() currently ignores the amount argument and always
# stakes MIN_STAKE (10 DIN). Extra DIN stays liquid; it is not a bigger stake.
dincli auditor dintoken stake 10

# Verify stake
dincli auditor dintoken read-stake
```

### Register (if state = `DINauditorsRegistrationStarted`)

```bash
dincli auditor register 0
```

### Check your Auditor Batch (if state = `AuditorsBatchesCreated`)

```bash
dincli auditor lms-evaluation show-batch 0
```

If a batch is shown, you will soon be required to audit it.

### Audit your assigned batch (if state = `LMSevaluationStarted`)

```bash
# Check your assigned batch
dincli auditor lms-evaluation show-batch 0

# Audit your batch (scripts run automatically)
dincli auditor lms-evaluation evaluate 0 --submit
```

> 💡 Auditor batch assignments depend on the current Global Iteration state and protocol
> allocation logic. A registered auditor may not receive a batch in every iteration.

### Slashing

Auditor slashing exists on the published contracts as a stub — `slashAuditors` on the
coordinator carries a placeholder comment and the deployed `DINTaskAuditor` has no
`slashAuditors` function. The real implementation lives on `develop` which will be released in devnet 2.0 onwards. Auditor economic
accountability is not enforced on the current devnet deployment.

---

# 🤖 Clients

### Prerequisites

Complete the shared setup in `Documentation/setup.md` and the readiness checklist above.
Specifically: **`configure-demo --mode no`**, wallet connected via
`connect-wallet --account N`, RPC chain ID confirmed 11155420, ETH balance non-zero,
and IPFS provider configured and verified.

Clients train local models using their dataset partition and submit model updates to the
network. No DIN token staking is required.

## 📊 MNIST Dataset Distribution

Model_0 uses the **MNIST dataset**, which is integrated into `dincli` for ease of use for
clients. If you have your own MNIST dataset please proceed to the **Dataset Requirements**
subsection. Otherwise you can distribute the dataset as follows:

### 📦 Distribute Dataset

```bash
dincli system dataset distribute-mnist \
  --seed YOUR_SEED \
  --model-id YOUR_MODEL_ID \
  --test-train \
  --clients \
  --num-clients YOUR_NUM_CLIENTS \
  --start-client-index YOUR_START_CLIENT_INDEX
```

where:

| Argument               | Description                         |
| ---------------------- | ----------------------------------- |
| `--seed`               | Random seed for shuffling           |
| `--model-id`           | Creates model directory             |
| `--test-train`         | Creates dataset directory           |
| `--clients`            | Enables client dataset distribution |
| `--num-clients`        | Number of participating clients     |
| `--start-client-index` | Starting wallet index               |

Example:

```bash
dincli system dataset distribute-mnist \
  --seed 42 \
  --model-id 0 \
  --test-train \
  --clients \
  --num-clients 9 \
  --start-client-index 0
```

### Account Indexing Requirement

Ensure sufficient private keys in `.env`.

#### Formal Requirement

```
MAX_INDEX ≥ start-client-index + num-clients - 1
```

#### Interpretation

- Clients are assigned sequentially and inclusively
- Total keys required = `num-clients`

#### Example

If:

- `start-client-index = 2`
- `num-clients = 9`

Then:

```
ETH_PRIVATE_KEY_2 → ETH_PRIVATE_KEY_10
```

## 📂 Dataset Requirements

Ensure your dataset is located at:

```
<CACHE_DIR>/sepolia_op_devnet/model_0/dataset/clients/<account_address>/data.pt
```

Find your cache directory:

```bash
dincli system get-cache-dir
```

## Training Process

### Explore Model
```bash
dincli task explore 0 --update
```

### Check Global Iteration State

```bash
dincli task gi show-state 0
```

### Submit Local Model (if state = `LMSstarted`)

```bash
# Check ETH balance
dincli system --eth-balance

# Optional (Recommended Step) to ensure training is running fine locally
# Train locally without submitting
dincli client train-lms 0

# Train and submit local model
dincli client train-lms 0 --submit

# Show submitted models
dincli client lms show-models 0
```

---

# 🧠 Final Notes

- Always verify the Global Iteration State before taking action
- Use multiple accounts strategically if desired
- Stay active in community channels for protocol updates and troubleshooting assistance

---

> 🚀 You are now ready to participate in **Model_0** and contribute to decentralised AI on
> the Infinite Zero Network.