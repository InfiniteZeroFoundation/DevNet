# Auditor Documentation

Auditors are responsible for evaluating the local models submitted by clients. They verify the quality and correctness of the models before they are aggregated.

## Token & Staking

Before participating, Auditors must acquire DIN Tokens and stake them.

### Buy DIN Tokens
Exchange ETH for DIN Tokens.
```bash
dincli auditor dintoken buy <amount_eth>
# where <amount_eth> is the amount of ETH you want to exchange for DIN Tokens.
```

### Stake DIN Tokens
Stake the required amount of DIN Tokens to become eligible.
```bash
dincli auditor dintoken stake <amount>
# where <amount> is the amount of DIN Tokens you want to stake.
```
*Note: The CLI usually handles approval and staking in one go if configured.*

### Check Stake
View your current stake.
```bash
dincli auditor dintoken read-stake
# read the amount of DIN Tokens staked by the you.
```

## Registration

Register as an Auditor for a specific Model and Global Iteration.

```bash
dincli auditor register <model_id> --gi <gi_index>
# --gi is optional; omit to use the current GI
# where <model_id> is the ID of the model you want to register for and <gi_index> is the index of the global iteration you want to register for.
```
*Registration must be open for the current GI.*

## Evaluation

Once appointed to a batch, Auditors evaluate the assigned models.

### Show Assigned Auditor Batch
View the Auditor batches assigned to you for evaluation. Also shows the your Evaluation of the local models in the batch.
```bash
dincli auditor lms-evaluation show-batch <model_id> [--gi <gi_index>] [--batch <batch_id>]
```
* `--gi` is optional; omit to use the current GI
* `--batch` is optional; add if you want to see a specific batch assigned to you, else the system will show you the auditor batch assigned to you automatically



### Evaluate Models
Run the evaluation process on your assigned batch.

```bash
dincli auditor lms-evaluation evaluate <model_id> [--gi <gi_index>] [--submit] [--batch <batch_id>] [--lmi <lmi_index>]
```
- **Options**:
    - `--gi`: Global Iteration number (optional). If not provided, the current GI will be used.
    - `--submit`: Submit the evaluation results (scores and eligibility) to the blockchain.
    - `--batch`: Evaluate a specific batch (optional). If not provided, the auditor batch assigned to you will be used.
    - `--lmi`: Evaluate a specific Local Model Index (optional). If not provided, all local models in the batch will be evaluated.

## Workflow

1. **Stake**: Ensure you have enough DIN Tokens staked.
2. **Register**: Register when the Model Owner opens Auditor registration for the current GI.
3. **Wait for Assignment**: Wait for the Model Owner to create Auditor Batches.
4. **Evaluate**: Run `evaluate` with `--submit` to process and score the models in your assigned batch.
