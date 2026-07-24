# Test-Set Resampling Policy

**Status:** Implemented (task_210726_6 §2c)
**Implements:** whitepaper §5.2.3b's test-set leakage/overfitting mitigation, referenced from `Developer/design/MECHANISM_DESIGN.md` §6 and `Developer/tasks/task_210726_6.md`.
**Code:** `cache_model_0/services/modelowner.py` — `_select_reserved_pool`, `_resample_round_pool`, wired into `create_audit_testDataCIDs`.
**Tests:** `tests/test_resampling_policy.py` (14 tests: pure policy logic + one true end-to-end integration test through `create_audit_testDataCIDs` with real file I/O).

## The problem

Every Global Iteration, auditors evaluate submitted local models against a shared held-out test dataset. If the *same* test data (or a naively-refreshed random sample of the *full* test set) is exposed round after round, two problems compound over a many-round task:

1. **Cumulative leakage.** Across enough rounds, auditors collectively see enough of the held-out set that it stops being held-out in any meaningful sense.
2. **Overfitting to the visible slice.** A model owner or colluding participants could shape submissions toward whatever portion of the test set has already been exposed.

## The policy

Two-level sampling, seeded independently at each level so the three random draws in this pipeline (reserved-pool selection, per-round resample, per-batch sample) can't perturb each other via shared global RNG state — each uses its own `torch.Generator`, not the process-global `torch.manual_seed`.

### 1. Reserved pool (task-level, fixed)

Once per task, deterministically select ~40% of the full test set as the "reserved pool" — `_select_reserved_pool(total_samples, reserved_pool_fraction=0.4, seed=0)`. Fixed seed, so this is the *same* 40% every time it's computed for a given task, not re-randomized per round. This stability is what makes "resampling" from it meaningful in step 2 — resampling a fresh random subset of the *whole* test set every round would still leak the whole set over enough rounds; resampling from a fixed, bounded reservation caps total exposure at that reservation's size, forever, regardless of round count.

### 2. Per-round resample (GI-level)

Each **non-final** round, expose only a fresh half of the reserved pool — `_resample_round_pool(reserved_pool, gi, is_final_round=False, resample_fraction=0.5)`, i.e. ~20% of the total test set. Seeded by `gi`, so each round's half is a genuinely different draw from the last (not a repeat), but deterministic if the same `gi` is passed twice (e.g. a retried transaction produces the same test data, not a different one).

The **final** round exposes the full reserved pool (`is_final_round=True` skips resampling entirely) — the task is ending, so there's no further-round exposure left to protect against, and a final comprehensive check benefits from the larger sample.

### 3. Per-batch sample (existing behavior, now scoped to the round pool)

Unchanged from before this task: each auditor batch gets ~5% of the *total* test set's worth of samples (capped at the round pool's size, for correctness when the round pool is smaller than that would imply). What changed: batches now sample *from the round pool*, not directly from the full test set — so even a batch's individual slice stays within that round's bounded exposure.

## Why this hooks into `create_audit_testDataCIDs` rather than a new design-only doc

The task's own instruction was to wire this into an existing dataset-assembly script if one exists, and one does: `create_audit_testDataCIDs` (`cache_model_0/services/modelowner.py`) is exactly the function that assembles per-batch test data before its CID gets pinned to IPFS and recorded on-chain via `assignAuditTestDataset`. This document exists alongside that wiring, not instead of it, since the task also separately asked for the algorithm to be documented for discoverability — the inline docstrings explain the *what* and *why* at the call site; this document is the one-stop summary.

## Known limitation / follow-up

`is_final_round` defaults to `False` and is **not currently passed by the real `dincli` call site** (`dincli/cli/modelownerd/auditor_batches.py:create_testdataset`, which calls `create_audit_testDataCIDs` with exactly the same 4 positional arguments it always has). This was a deliberate scope boundary for this task — `dincli/` changes were explicitly out of scope beyond §1's pytest work — and the default direction is the safe one (under-exposing the test set every round, never over-exposing it), so nothing breaks by leaving it unwired.

**Follow-up needed to actually reach the "final round: full pool" behavior in production:** `dincli`'s `create_testdataset` command needs a way to know whether the current GI is the model owner's intended final round (a manifest field like `planned_global_iterations`, compared against `curr_GI`, would do it) and pass `is_final_round=True` accordingly when calling into this service function. Until that lands, every round — including what a model owner intends as their last — gets the resampled-half treatment, which is safe but not the full intended behavior.
