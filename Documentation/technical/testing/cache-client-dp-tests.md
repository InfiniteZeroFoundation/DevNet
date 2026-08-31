# Client DP Mechanism Unit Tests (`tests/test_cache_client_dp.py`)

This document describes the unit test suite for the differential-privacy
layer of the **example client service** at `cache_model_0/services/client.py`
— specifically `resolve_dp_config()` (manifest → DP config resolution) and
`apply_dp_mechanism()` (the three post-training mechanisms). Background on
the manifest's nested `dp` block is in the repo docs on manifest-driven
services (see `CLAUDE.md`, "Manifest-driven, pluggable model services").

Note the target: `cache_model_0/` is a *reference service implementation*
(MNIST-style), not `dincli` framework code. In production, model owners ship
their own `client.py` via IPFS; this suite pins down the behavior of the
bundled example that other implementations are likely to copy.

These are pure unit tests: no chain, no IPFS, no training loop. Real
PyTorch tensors are used (the suite is skipped entirely if `torch` is not
installed, via `pytest.importorskip`), but every DP configuration is chosen
so the mechanisms are exercised in a *deterministic identity regime* — zero
noise scale and a clipping norm far above the tensor norms — so exact
`torch.equal` assertions hold without seeding RNG.

---

## Running

```bash
cd /path/to/devnet
pytest tests/test_cache_client_dp.py -v

# single test
pytest tests/test_cache_client_dp.py -k test_update_gaussian_preserves_weights_when_noise_is_zero
```

Requires `torch` in the environment; without it the whole module is
**skipped** (not failed).

---

## What the suite verifies

### Manifest resolution (`resolve_dp_config`)

| Test | Behavior pinned down |
|------|----------------------|
| `test_resolve_dp_config_uses_nested_manifest` | A nested `dp` manifest block (`enabled`, `mode: afterTraining`, `mechanism: update_gaussian`, `parameters.{clipping_norm, noise_multiplier, clip_scope}`) resolves field-for-field into the returned DP config, read through the runtime's `get_manifest_key("dp", ...)` |

### Mechanism application (`apply_dp_mechanism`)

All three supported mechanisms are driven with zero noise
(`noise_multiplier`/`laplace_scale` = 0.0 — a deliberate no-op per
`add_gaussian_noise`/`add_laplace_noise`) and `clipping_norm: 100.0` (no
tensor comes near the bound), so the output must equal the input exactly.

| Test | Behavior pinned down |
|------|----------------------|
| `test_post_training_mechanisms_preserve_weights_when_noise_is_zero[post_training_gaussian]` | Clip-then-Gaussian-noise pipeline is the identity when noise is 0 and clipping is loose (`clip_scope: per_layer`) |
| `test_post_training_mechanisms_preserve_weights_when_noise_is_zero[post_training_laplace]` | Same for the clip-then-Laplace pipeline (`laplace_scale: 0.0`) |
| `test_update_gaussian_preserves_weights_when_noise_is_zero` | The delta path — compute trained−reference delta, clip (`clip_scope: global`), noise the delta, reconstruct reference+delta — round-trips back to the trained weights exactly |

### Sensitivity calibration

These drive real, nonzero noise and real clipping.

| Test | Behavior pinned down |
|------|----------------------|
| `test_noise_scales_with_clipping_norm[...]` | For all three mechanisms, quadrupling `clipping_norm` at a fixed multiplier quadruples the noise standard deviation. Weights sit well inside the bound so clipping is a no-op and the measured difference is noise alone |
| `test_noise_scales_with_noise_multiplier[...]` | For all three mechanisms, quadrupling `noise_multiplier` at a fixed clipping norm quadruples the noise. Without this, an implementation that used `clipping_norm` alone would still pass the test above |
| `test_noise_is_zero_when_clipping_norm_is_zero[...]` | A non-positive `clipping_norm` disables clipping, leaving no sensitivity to calibrate against, so the scaled noise is zero and the mechanism is an explicit no-op |
| `test_global_clip_scope_bounds_the_combined_norm` | Sixteen tensors each driven past the bound: `per_layer` leaves a combined L2 norm of `clipping_norm * 4` (that is, `sqrt(16)`), `global` leaves exactly `clipping_norm` |
| `test_resolve_dp_config_defaults_clip_scope_to_global` | A manifest with no `clip_scope` resolves to `global` |

All three zero-noise tests also include a non-floating tensor (`counter`, dtype
`long`) in the state_dict and assert it survives untouched, pinning down
that clipping/noising apply **only to floating-point tensors**; integer
buffers are cloned through unchanged (see `clip_state_dict` /
`add_noise_to_state_dict` / `reconstruct_state_dict_from_delta`).

---

## Isolation patterns

Conventions to reuse when adding tests to this suite:

- **Skip, don't fail, without torch** — `torch = pytest.importorskip("torch")`
  at module top level; keeps the suite runnable in environments where the
  ML stack isn't installed (dincli itself does not depend on torch).

- **Dynamic module load** — `cache_model_0/` is not an importable package;
  `load_client_module()` loads `services/client.py` via
  `importlib.util.spec_from_file_location`. This mirrors how `dincli`
  actually consumes model-owner services at runtime
  (`DinContext.load_custom_fn` dynamically loads IPFS-fetched files), so the
  tests exercise the module the way production does.

- **`DummyRuntime`** — a two-line stand-in for `ServiceRuntimeContext`
  exposing only `get_manifest_key(key, default)` backed by a plain dict.
  Reuse it for any test of manifest-driven service behavior.

- **Identity regime instead of seeded RNG** — rather than seeding
  `torch.manual_seed` and asserting statistics, configs are chosen so the
  mechanism is provably a no-op (`noise ≤ 0` short-circuits, loose clipping
  norm). Assertions can then use exact `torch.equal`.

---

## Coverage gaps

Behavior of the DP layer this suite does not yet exercise:

- **Noise distribution shape** — the sensitivity tests measure standard
  deviation only. Nothing asserts that Gaussian noise is Gaussian or that
  Laplace noise has Laplace tails, so a mechanism swapped for the wrong
  distribution at the same scale would pass.
- **`resolve_dp_config` beyond the happy path** — untested: absent/empty
  `dp` block → compact disabled config; `enabled: false` / disabled mode
  spellings (`DISABLED_DP_MODES`: `none`, `off`, `false`, …); `enabled: true`
  with no mode coercing to `afterTraining`; parameter defaults injected by
  `setdefault` (`clipping_norm` 1.0, `noise_multiplier` 0.5, `laplace_scale`
  defaulting to `noise_multiplier`; `clip_scope` now covered above); the
  `ValueError` for unsupported mechanisms.
- **Alias normalization** — `normalize_dp_mechanism` (`gaussian` →
  `post_training_gaussian`, `update` → `update_gaussian`, …) and
  `normalize_dp_mode` (`after_training` → `afterTraining`) have no direct
  tests; the manifest test uses canonical names only.
- **Error paths in `apply_dp_mechanism`** — `update_gaussian` without a
  `reference_state_dict` (ValueError), invalid `clip_scope`, and unsupported
  mechanism names are unasserted.
- **Helper primitives in isolation** — `clip_weights` (incl. the
  non-finite-norm guard), `compute_state_dict_delta`,
  `reconstruct_state_dict_from_delta`, and `clone_state_dict`'s
  mapping-type preservation are only covered indirectly.
- **Non-tensor state_dict entries** — the copy-through branches for
  non-tensor values are never hit (only tensors appear in test inputs).
- **Integration with training** — `train_client_model` invoking
  `resolve_dp_config`/`apply_dp_mechanism` (the `afterTraining` hook point,
  and passing the genesis model as `reference_state_dict` for
  `update_gaussian`) is out of scope here and untested.
