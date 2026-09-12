# Auditor Documentation

Auditors evaluate the local models submitted by Clients, verifying their quality before aggregation. They must stake DIN Tokens to participate and are subject to slashing if they behave maliciously or fail to submit results for assigned Auditor Batches.

---

## 1. Token & Staking

### Buy DIN Tokens

Exchange ETH for DIN Tokens.

```bash
dincli auditor dintoken buy <amount_eth>
```

`<amount_eth>` — the amount of ETH to exchange for DIN Tokens.

### Stake DIN Tokens

Stake the required amount of DIN Tokens to become eligible.

```bash
dincli auditor dintoken stake <amount>
```

`<amount>` — the number of DIN Tokens to stake.

> [!NOTE]
> The CLI handles both the ERC-20 approval and the staking transaction in a single command.

### Check Your Stake

```bash
dincli auditor dintoken read-stake
```

---

## 2. Registration

Register as an Auditor for a specific model and Global Iteration.

```bash
dincli auditor register <model_id> [--gi <gi_index>]
```

| Argument / Option | Required | Description |
|---|---|---|
| `<model_id>` | Yes | The ID of the model you want to audit |
| `--gi <gi_index>` | No | The Global Iteration index. Defaults to the current GI if omitted |

> [!IMPORTANT]
> Registration must be open for the current GI before this command will succeed.

---

## 3. Evaluation

Once the Model Owner creates Auditor Batches and assigns you to one, you can view and evaluate your assigned models.

### Show Your Assigned Batch

```bash
dincli auditor lms-evaluation show-batch <model_id> [--gi <gi_index>] [--batch <batch_id>]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | Global Iteration index. Defaults to the current GI if omitted |
| `--batch <batch_id>` | No | View a specific batch. If omitted, your automatically assigned batch is shown |

### Evaluate Models

Run the evaluation pipeline on your assigned batch and submit the results on-chain.

```bash
dincli auditor lms-evaluation evaluate <model_id> [--gi <gi_index>] [--submit] [--batch <batch_id>] [--lmi <lmi_index>]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | Global Iteration index. Defaults to the current GI if omitted |
| `--submit` | No | Submit evaluation scores and eligibility flags to the blockchain |
| `--batch <batch_id>` | No | Evaluate a specific batch. Defaults to your assigned batch if omitted |
| `--lmi <lmi_index>` | No | Evaluate a single Local Model by index. Evaluates all models in the batch if omitted |

---

## Workflow

1. **Stake** — Ensure you have enough DIN Tokens staked.
2. **Register** — Register when the Model Owner opens Auditor registration for the current GI.
3. **Wait for Assignment** — The Model Owner will create Auditor Batches and assign models to you.
4. **Evaluate** — Run `evaluate --submit` to score assigned models and record results on-chain.