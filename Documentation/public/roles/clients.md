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
> | `<network>` | The active network name | `local`, `sepolia_op_devnet` |
> | `<model_id>` | The ID of the model you are participating in | `0` |
> | `<account_address>` | Your Ethereum wallet address | `0xAbC...123` |
>
> **Example path:** `~/.cache/dincli/local/model_0/dataset/clients/0xAbC...123/data.pt`

---

## Commands

### Train a Local Model

Train a local model on your dataset, in the worker container. Nothing is sent on-chain.

```bash
dincli client train-lms <model_id> [--gi <gi_index>] [--packages-dir <dir>] [--no-cache]
```

| Argument / Option | Required | Description |
|---|---|---|
| `<model_id>` | Yes | The ID of the model/task you are participating in |
| `--gi <gi_index>` | No | The Global Iteration index. Defaults to the current GI if omitted |
| `--packages-dir <dir>` | No | Packages directory to mount into the worker |
| `--no-cache` | No | Don't use cached packages |

### Submit the Local Model

Upload the trained model to IPFS and record its CID on-chain. LMS must be open.

```bash
dincli client submit-lm <model_id> [--gi <gi_index>]
```

> [!NOTE]
> Training alone doesn't count: run `submit-lm` to make your contribution visible to the network.

---

### Claim Rewards

After the Model Owner ends the GI, credit your share of its reward pool and withdraw it:

```bash
# Credit your share for an ended GI
dincli rewards claim <model_id> --gi <gi_index>

# Transfer your whole claimable balance to your wallet
dincli rewards withdraw <model_id>
```

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
3. **Train** — Run `train-lms` to train on your data.
4. **Submit** — Run `submit-lm` to upload the model and record it on-chain.
5. **Verify** — Run `show-models` to confirm your submission was recorded successfully.
6. **Claim** — After the GI ends, run `rewards claim` and `rewards withdraw`.