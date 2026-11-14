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
> Registration must be open for the current GI before this command will succeed. A wallet registered as an aggregator in the same GI can't also register as an auditor.

### Register an Encryption Key (once per wallet)

The Model Owner encrypts each batch's test data to its auditors' X25519 public keys, so you need a registered key before you can be given test data.

```bash
dincli auditor register-encryption-key
```

The command generates this wallet's key, saves it as `<CONFIG_DIR>/auditor_x25519_<address>.key` (mode 0600), and registers the public key on `DinValidatorStake`. It skips the transaction if that key is already registered. Run it from the machine you evaluate on, and keep the file: without it you can't decrypt your batch's test data. Until every auditor in a batch has a key, the Model Owner's `create-testdataset --submit` stops and names the keyless auditors.

---

## 3. Evaluation

Once the Model Owner creates Auditor Batches and assigns you to one, you can view and evaluate your assigned models.

### Lock the Batch-Assignment Seed (optional, recommended)

```bash
dincli auditor lock-seed <model_id> [--gi <gi_index>]
```

Between `closeLMsubmissions` and batch creation, the auditor batch assignment is drawn from a seed anchored to a future block. Anyone can lock it once that block is mined. If only the Model Owner locks it, they can decline to lock a draw they dislike and wait ~256 blocks for a fresh one, so locking it yourself as soon as it is available removes that option. The command waits for the seed block, then locks (or skips if someone already has). `lms-evaluation show-batch` does the same automatically when run before batches exist. Only valid while the GI is in `LMSclosed`; a successful lock moves it to `AuditSeedLocked`.

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
| `--submit` | No | **Commit** a hidden hash of each score and eligibility vote on-chain (the score, vote and a random salt are cached locally for the reveal). Omit to evaluate locally only. Re-running skips models you've already committed |
| `--batch <batch_id>` | No | Evaluate a specific batch. Defaults to your assigned batch if omitted |
| `--lmi <lmi_index>` | No | Evaluate a single Local Model by index. Evaluates all models in the batch if omitted |

Evaluation needs your batch's test data, which the Model Owner assigns before opening evaluation (GI state `AuditTestDataAssigned`).

### Reveal Your Scores

Once the Model Owner closes the commit window (`lms-evaluation start-reveal`), reveal what you committed. Only revealed scores count, and a commit that is never revealed is slashed as a missed vote.

```bash
dincli auditor lms-evaluation reveal <model_id> [--gi <gi_index>] [--batch <batch_id>] [--lmi <lmi_index>]
```

| Option | Required | Description |
|---|---|---|
| `--gi <gi_index>` | No | Global Iteration index. Defaults to the current GI if omitted |
| `--batch <batch_id>` | No | Reveal only this batch. Defaults to every batch you committed in |
| `--lmi <lmi_index>` | No | Reveal only this Local Model |

Reveal from the same machine you committed from: the score, vote and salt are in the local commit cache (`<model dir>/audits/commits/<your address>/`).

---

## 4. Rewards

After the Model Owner ends the GI, credit your share of its reward pool and withdraw it:

```bash
# Credit your share for an ended GI
dincli rewards claim <model_id> --gi <gi_index>

# Transfer your whole claimable balance to your wallet
dincli rewards withdraw <model_id>
```

---

## 5. Disputing Test Data

If your batch's test data is wrong (for example, you received no key for it), open a dispute. It posts a DIN bond (100 DIN by default), and must be opened before the GI's rewards settle at `gi end`:

```bash
dincli auditor dispute-test-data <model_id> --batch <batch_id> [--gi <gi_index>]
```

The Model Owner answers by revealing the batch key. If it matches the on-chain commitment, the dispute fails and the bond is forfeited. If it doesn't, or the Model Owner doesn't answer within the window (anyone can then close it with `dincli model-owner disputes close-expired`), the dispute is upheld and the bond comes back to you.

---

## Workflow

1. **Stake** — Ensure you have enough DIN Tokens staked.
2. **Register** — Register when the Model Owner opens Auditor registration for the current GI, and register an encryption key if this wallet doesn't have one yet.
3. **Wait for Assignment** — After LMS closes, lock the seed (`lock-seed`); the Model Owner creates Auditor Batches and assigns each batch its test data.
4. **Evaluate** — Run `evaluate --submit` to score assigned models and commit the results on-chain.
5. **Reveal** — When the reveal window opens, run `lms-evaluation reveal`.
6. **Claim** — After the GI ends, run `rewards claim` and `rewards withdraw`.