# Client Documentation

Clients contribute to the DIN network by training local models on their own data and submitting the local models for aggregation to a specific task.

---

## Prerequisites

> [!IMPORTANT]
> Before running any training command, client dataset file must be placed at the following path:
>
> ```
> <CACHE_DIR>/<network>/model_<model_id>/dataset/clients/<account_address>/data.pt
> ```
>
> | Placeholder | Description | Example |
> |---|---|---|
> | `<CACHE_DIR>` | The DIN CLI cache directory | `~/.cache/dincli` |
> | `<network>` | The active network name | `local`, `sepolia_devnet`, `sepolia_op_devnet`, `mainnet` |
> | `<model_id>` | The ID of the model you are participating in | `0` |
> | `<account_address>` | Your Ethereum wallet address | `0xAbC...123` |
>
> **Example path:** `~/.cache/dincli/local/model_0/dataset/clients/0xAbC...123/data.pt`

---

## Commands

### Train & Submit a Local Model

Train a local model using your dataset and optionally submit the result to the blockchain.

```bash
dincli client train-lms <model_id> [--gi <gi_index>] [--submit]
```

| Argument / Option | Required | Description |
|---|---|---|
| `<model_id>` | Yes | The ID of the model/task you are participating in |
| `--gi <gi_index>` | No | The Global Iteration index. Defaults to the current GI if omitted |
| `--submit` | No | Upload the trained model to IPFS and record the submission on-chain |

> [!NOTE]
> Always include `--submit` to make your contribution visible to the network.

---

### Show Submitted Models

View your local model submissions for a specific Global Iteration.

```bash
dincli client lms show-models <model_id> [--gi <gi_index>]
```

| Argument / Option | Required | Description |
|---|---|---|
| `<model_id>` | Yes | The ID of the model/task |
| `--gi <gi_index>` | No | The Global Iteration index to query. Defaults to the current GI if omitted |

---

## Workflow

1. **Wait for LMS Open** — The Model Owner must open the Local Model Submission (LMS) phase for the current GI.
2. **Place Dataset** — Ensure your `data.pt` file is at the correct path (see Prerequisites above).
3. **Train** — Run `train-lms` with `--submit` to process your data and record the result on-chain.
4. **Verify** — Run `show-models` to confirm your submission was recorded successfully.