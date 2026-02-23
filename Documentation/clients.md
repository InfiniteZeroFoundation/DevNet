# Client Documentation

Clients in the DIN network contribute by training local models and submitting them to the network.

## Commands

### Train Local Model

Train a local model using the data on your machine and submit the result to IPFS and the Task Auditor.

> [!IMPORTANT]
> Your dataset file must be placed at the following path **before** running this command:
> ```
> <CACHE_DIR>/<network>/model_<model_id>/dataset/clients/<account_address>/data.pt
> ```
>
> | Placeholder | Description | Example |
> |---|---|---|
> | `<CACHE_DIR>` | The DIN CLI cache directory | `~/.cache/dincli` |
> | `<network>` | The active network name | `local`, `sepolia_devnet` |
> | `<model_id>` | The ID of the model you are participating in | `0` |
> | `<account_address>` | Your Ethereum wallet address | `0xAbC...123` |
>
> **Example:** `~/.cache/dincli/local/model_0/dataset/clients/0xAbC...123/data.pt`

```bash
dincli client train-lms <model_id> --submit --gi <global_iteration>
```

- **Arguments**:
    - `model_id`: The ID of the model/task you are participating in.
- **Options**:
    - `--submit`: Automatically submit the trained model hash to the blockchain.
    - `--gi`: Specify the Global Iteration (GI) index.

### Show Submitted Models

View your local model submission for a specific Global Iteration.

```bash
dincli client lms show-models <model_id> --gi <global_iteration>
```

- **Arguments**:
    - `model_id`: The ID of the model/task.
- **Options**:
    - `--gi`: The Global Iteration index to query.

## Workflow

1. **Wait for LMS Open**: The Model Owner must open the Local Model Submission (LMS) phase for the current GI on the model with ID `<model_id>`.
2. **Train**: Run `train-lms` to process your local dataset.
3. **Submit**: Ensure you use the `--submit` flag to record your contribution on-chain.
4. **Verify**: Use `show-models` to confirm your submission was recorded.
