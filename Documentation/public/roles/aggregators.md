# Aggregator Documentation

Aggregators combine evaluated local models into sub-global and global model updates. They must stake DIN Tokens to participate and operate across two tiers of aggregation. They are subject to slashing if they behave maliciously or fail to submit results for assigned Aggregator Batches.

---

## 1. Token & Staking

### Buy DIN Tokens

Exchange ETH for DIN Tokens.

```bash
dincli aggregator dintoken buy <amount_eth>
```

`<amount_eth>` — the amount of ETH to exchange for DIN Tokens.

### Stake DIN Tokens

```bash
dincli aggregator dintoken stake <amount>
```

`<amount>` — the number of DIN Tokens to stake.

> [!NOTE]
> The CLI handles both the ERC-20 approval and the staking transaction in a single command.

### Check Your Stake

```bash
dincli aggregator dintoken read-stake
```

---

## 2. Registration

Register as an Aggregator for a specific model and Global Iteration.

```bash
dincli aggregator register <model_id> [--gi <gi_index>]
```

| Argument / Option | Required | Description |
|---|---|---|
| `<model_id>` | Yes | The ID of the model you want to aggregate for |
| `--gi <gi_index>` | No | The Global Iteration index. Defaults to the current GI if omitted |

> [!IMPORTANT]
> Aggregators Registration must be open for the current GI before to successfully register as an aggregator.

---

## 3. Aggregation Process

Aggregators operate in two tiers:
- **Tier 1 (T1)** — Intermediate aggregation: combine local model batches into sub-global model updates.
- **Tier 2 (T2)** — Final aggregation: combine sub-global model updates into a single global model.

### Tier 1 Aggregation

**Lock the batch-assignment seed (optional, recommended):**

```bash
dincli aggregator lock-seed <model_id> [--gi <gi_index>]
```

Between `closeLMsubmissionsEvaluation` and batch creation, the T1/T2 batch assignment is drawn from a seed anchored to a future block. Anyone can lock it once that block is mined. If only the Model Owner locks it, they can decline to lock a draw they dislike and wait ~256 blocks for a fresh one, so locking it yourself as soon as it is available removes that option. The command waits for the seed block, then locks (or skips if someone already has). `show-t1-batches` / `show-t2-batches` do the same automatically when run before batches exist. Only valid while the GI is in `LMSevaluationClosed`.

**View your assigned T1 batches:**

```bash
dincli aggregator show-t1-batches <model_id> [--gi <gi_index>] [--detailed]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | Global Iteration index. Defaults to the current GI if omitted |
| `--detailed` | No | Include your submitted aggregated CID for each T1 batch |

**Aggregate and commit a T1 batch:**

```bash
dincli aggregator aggregate-t1 <model_id> [--gi <gi_index>] [--batch <batch_id>] [--submit]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | Global Iteration index. Defaults to the current GI if omitted |
| `--batch <batch_id>` | No | Target a specific batch. Defaults to your automatically assigned batch if omitted |
| `--submit` | No | Upload the aggregated result to IPFS and **commit** a hidden hash of it on-chain (the CID and a random salt are cached locally for the reveal). Omit to aggregate locally only. Re-running skips batches you've already committed |

**Reveal your T1 commit** (after the Model Owner opens the reveal window, GI state `T1AggregationRevealStarted`):

```bash
dincli aggregator reveal-t1 <model_id> [--gi <gi_index>] [--batch <batch_id>]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | Global Iteration index. Defaults to the current GI if omitted |
| `--batch <batch_id>` | No | Reveal only this batch. Defaults to every batch you have a local commit for |

> ⚠️ Aggregation is commit-then-reveal: your CID only counts once revealed. **A commit that is never revealed is slashed like a missed submission.** Reveal from the same machine you committed from, since the salt lives in the local commit cache (`<model dir>/aggregations/commits/`).

---

### Tier 2 Aggregation

**View your assigned T2 batches:**

```bash
dincli aggregator show-t2-batches <model_id> [--gi <gi_index>] [--detailed]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | Global Iteration index. Defaults to the current GI if omitted |
| `--detailed` | No | Include your submitted aggregated CID for each T2 batch |

**Aggregate and commit a T2 batch:**

```bash
dincli aggregator aggregate-t2 <model_id> [--gi <gi_index>] [--batch <batch_id>] [--submit]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | Global Iteration index. Defaults to the current GI if omitted |
| `--batch <batch_id>` | No | Target a specific batch. Defaults to your automatically assigned batch if omitted |
| `--submit` | No | Upload the aggregated result to IPFS and **commit** a hidden hash of it on-chain (the CID and a random salt are cached locally for the reveal). Omit to aggregate locally only. Re-running skips batches you've already committed |

**Reveal your T2 commit** (after the Model Owner opens the reveal window, GI state `T2AggregationRevealStarted`):

```bash
dincli aggregator reveal-t2 <model_id> [--gi <gi_index>]
```

---

## Workflow

1. **Stake** — Ensure you have sufficient DIN Tokens staked.
2. **Register** — Join the Aggregator pool when the Model Owner opens registration for the current GI.
3. **Wait for Assignment** — The system will assign you to T1 and possibly T2 batches after the evaluation phase closes.
4. **Aggregate and commit T1** — Run `aggregate-t1 --submit` when the Tier 1 aggregation phase opens (`T1AggregationStarted`).
5. **Reveal T1** — Run `reveal-t1` once the Model Owner opens the T1 reveal window (`T1AggregationRevealStarted`).
6. **Aggregate and commit T2** — If assigned to the final tier, run `aggregate-t2 --submit` when the Tier 2 phase opens (`T2AggregationStarted`).
7. **Reveal T2** — Run `reveal-t2` once the T2 reveal window opens (`T2AggregationRevealStarted`).
