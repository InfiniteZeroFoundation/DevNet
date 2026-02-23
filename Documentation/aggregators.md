# Aggregator Documentation

Aggregators are responsible for combining the evaluated local models into a sub-global or global model update.

## Token & Staking

Like Auditors, Aggregators must stake DIN Tokens to participate.

### Buy & Stake
```bash
# Buy Tokens
dincli aggregator dintoken buy <amount_eth>
# where <amount_eth> is the amount of ETH you want to exchange for DIN Tokens.

# Stake Tokens
dincli aggregator dintoken stake <amount>
# where <amount> is the amount of DIN Tokens you want to stake.
```

### Check Stake
```bash
dincli aggregator dintoken read-stake
# read the amount of DIN Tokens staked by the you.
```

## Registration

Register as an Aggregator for a specific Model and Global Iteration.

```bash
dincli aggregator register <model_id> [--gi <gi_index>]
# --gi is optional; omit to use the current GI
```
*Registration must be open for the current GI.*

## Aggregation Process

Aggregators operate in two tiers: Tier 1 (intermediate aggregation - sub-global model aggregations) and Tier 2 (final aggregation - global model aggregation).

### Tier 1 Aggregation (T1)

1. **View T1 Batches**:

   View the T1 batches assigned to you.

   ```bash
   dincli aggregator show-t1-batches <model_id> [--gi <gi_index>] [--detailed]
   ```
   * `--gi` is optional; omit to use the current GI
   * `--detailed` is optional; omit to see limited information, add to see your submitted aggregated_CID for T1 batch

2. **Aggregate T1**:
   Process and submit the result for a Tier 1 batch.
   ```bash
   dincli aggregator aggregate-t1 <model_id> [--batch <batch_id>] [--submit] [--gi <gi_index>]
   ```
   * `--batch` is optional; omit to auotmated aggregation on assigned batch
   * `--submit` is optional; add to aggregate and submit to the DIN task contracts, otherwise it will only aggregate the batch locally
   * `--gi` is optional; omit to use the current GI

### Tier 2 Aggregation (T2)

1. **View T2 Batches**:

   View the T2 batches assigned to you.

   ```bash
   dincli aggregator show-t2-batches <model_id> [--gi <gi_index>] [--detailed]
   ```
   * `--gi` is optional; omit to use the current GI
   * `--detailed` is optional; omit to see limited information, add to see your submitted aggregated_CID for T2 batch

2. **Aggregate T2**:
   Process Tier 1 results into a final global model update.
   ```bash
   dincli aggregator aggregate-t2 <model_id> [--batch <batch_id>] [--submit] [--gi <gi_index>]
   ```
   * `--batch` is optional; omit to auotmated aggregation on assigned batch
   * `--submit` is optional; add to aggregate and submit to the DIN task contracts, otherwise it will only aggregate the batch locally
   * `--gi` is optional; omit to use the current GI

## Workflow

1. **Stake**: Ensure sufficient stake.
2. **Register**: Join the Aggregator pool when registration opens.
3. **Wait for Assignment**: The system will assign you to T1 and possibly T2 batches.
4. **Aggregate T1**: Run `aggregate-t1` when the phase starts.
5. **Aggregate T2**: Run `aggregate-t2` if assigned to the final tier.
