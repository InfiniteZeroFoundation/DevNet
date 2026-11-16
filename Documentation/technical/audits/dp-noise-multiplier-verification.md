# DP Noise Multiplier Verification Against Real Trained Weights

**Tracking:** [BL-23](../../../Developer/BACK_LOG.md); manifest `clipping_norm` fix in [PR No. 263](https://github.com/InfiniteZeroFoundation/DevNet/pull/263)
**Scope:** BL-23's `clipping_norm` question is already resolved by PR #263, which raised the manifest default to `10.0` and added reproducible tests (`tests/test_cache_client_dp.py`'s `_build_and_train_reference`) pinning the reference model's real post-training L2 norm at ≈ 9.44 and its one-round `update_gaussian` delta norm at ≈ 3.62. This document instead records a related, previously unscoped finding surfaced while verifying that work: the manifest's default `noise_multiplier: 0.5` is independently destructive, regardless of `clipping_norm`.
**Method (Finding 2, reproducible):** [`scripts/dp_noise_multiplier_sweep.py`](../../../scripts/dp_noise_multiplier_sweep.py) uses the exact same fixture as PR #263's `_build_and_train_reference()` — the committed `cache_model_0/dataset/test/test_dataset.pt`, seed=42, 2,000 samples, 20 epochs, lr=0.01 — so its numbers are directly comparable to that test's pinned values, and the script is runnable with no network access or extra dependencies.

---

## Finding 1 (already fixed by PR #263): `clipping_norm: 1.0` was destructive

This was BL-23's original question, resolved by PR #263 before this document was committed. `_build_and_train_reference`'s pinned numbers (reproducible via `pytest tests/test_cache_client_dp.py -k test_real_weights_combined_norm_fits_manifest_clipping_norm`): the reference model's real post-training combined L2 norm is **≈ 9.44**, well above the old default of `1.0` and comfortably under PR #263's new default of `10.0`.

An earlier, separate exploratory sweep (config: 400 real MNIST samples via `sklearn.datasets.fetch_openml`, 10 local epochs, Adam lr=0.001 — `train_client_model`'s exact hyperparameters, not committed as a script since it depends on network access) found the same order of magnitude across more configs/seeds — global L2 norm consistently in **9.3–12.6** across 5 seeds × 3 `(sample count, epoch count)` combinations — and confirmed utility stops degrading from clipping once `clipping_norm` reaches roughly 4:

| `clipping_norm` | accuracy after clip only (that sweep's config) |
|---|---|
| 1.0 | 36.25% |
| 2.0 | 69.80% |
| 4.0 | 85.15% |
| 6.0–20.0 | 85.25–85.60% (flat, matches that config's unclipped baseline of 85.25%) |

The two configs differ (400 samples/10 epochs/Adam lr=0.001 vs. PR #263's 2,000 samples/20 epochs/plain-SGD lr=0.01), which is why the norms differ slightly (9.3–12.6 vs. 9.44) — both are well inside the same order of magnitude, and both are well below PR #263's `clipping_norm: 10.0`, which sits in the flat, non-destructive region either way. No further `clipping_norm` change is proposed here.

---

## Finding 2 (new, not in BL-23's original scope): the default `noise_multiplier: 0.5` is independently destructive, regardless of `clipping_norm`

Run `python3 scripts/dp_noise_multiplier_sweep.py` to reproduce the numbers below exactly (no network access needed — it loads the committed test dataset the same way `tests/test_cache_client_dp.py` does).

```
Baseline (no DP) holdout accuracy: 0.8600
Post-training combined L2 norm:     9.44
One-round delta L2 norm:             3.62
```

The post-training norm (9.44) and delta norm (3.62) match PR #263's pinned values exactly, confirming the script reproduces the same fixture.

**Raising `clipping_norm` alone does not fix the accuracy collapse**, because the Gaussian noise's scale (`noise_multiplier * clipping_norm`) moves in lockstep with the clip. Holding `clipping_norm` fixed at the measured delta norm (3.62 — no clipping distortion at all) and sweeping `noise_multiplier`:

| `noise_multiplier` | accuracy |
|---|---|
| 0.5 (current manifest default) | 10.50% |
| 0.1 | 10.00% |
| 0.01 | 73.00% |
| 0.001 | 85.50% |
| 0.0005 | 85.75% |
| 0.0 (no noise) | 86.00% |

At the current default (`noise_multiplier: 0.5`), accuracy collapses to 10.50% — at the 10-class random-guessing floor — even with zero clipping distortion. Utility only recovers once `noise_multiplier` drops to roughly `0.001`, about **500x** below the current default.

**Why:** noise is added independently to every floating-point coordinate. For a `D`-parameter model, the *aggregate* L2 norm of the injected noise scales as `noise_multiplier * clipping_norm * √D`, not `noise_multiplier * clipping_norm`. `cache_model_0`'s MLP has ~109K parameters (`√D ≈ 330`), so the aggregate noise norm at the default `noise_multiplier: 0.5` is roughly 330x the per-coordinate scale — far exceeding the signal it's added to, regardless of how well-tuned `clipping_norm` is. This is the same `√d` dimension penalty `dp-mechanism-review.md` F4 describes for the Laplace/L1 case, showing up again here on the Gaussian/noise-multiplier side.

**This is left unfixed here.** Retuning `noise_multiplier` is a privacy-level decision that properly belongs with an epsilon/accounting discussion (`dp-mechanism-review.md`'s priority list, item 3 — "Accountant integration" — and item 4, DP-SGD), not a standalone default-value change made without that context. Recorded here as a concrete, measured, reproducible finding for whoever picks up that work next — see [issue #279](https://github.com/InfiniteZeroFoundation/DevNet/issues/279).

---

## Reproducing this

```bash
python3 scripts/dp_noise_multiplier_sweep.py
```

The script trains the real `ModelArchitecture` (`cache_model_0/services/model.py`) on the committed `cache_model_0/dataset/test/test_dataset.pt`, then runs `apply_dp_mechanism` from `cache_model_0/services/client.py` with `update_gaussian` across the `noise_multiplier` sweep above. It depends only on `torch` (already required by `tests/test_cache_client_dp.py`), with no network access and no `torchvision` dependency (it stubs the torchvision classes referenced by the dataset pickle, the same technique `tests/test_cache_client_dp.py`'s `_load_test_dataset()` uses).
