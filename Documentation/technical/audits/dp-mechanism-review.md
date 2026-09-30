# Differential Privacy & Responsible AI Review

**Reviewer:** walkonwayvs
**Scope:** Starter Task — DP & Responsible AI Review (`Developer/issues/dp-governance-review-starter-task.md`)
**Reviewed:** `cache_model_0/services/client.py`, `cache_model_0/manifest.json`, `tests/test_cache_client_dp.py`, `Developer/issues/DifferentialPrivacy.md`
**Perspective:** node operator / protocol verification, not academic DP research. Findings below are stated with the confidence I actually have, and I have flagged where something needs a specialist to confirm.
**Source:** [PR #89](https://github.com/InfiniteZeroFoundation/DevNet/pull/89), submitted as `Developer/issues/REVIEW.md` and relocated here on merge — findings-against-existing-code belong in `Documentation/technical/` per `Developer/README.md`'s placement rules, matching where the earlier `foundry/src/` security review landed (`Documentation/technical/audits/foundry-src-security-review.md`). Content unchanged from the PR.
**Independent verification:** every finding below was independently reproduced against unmodified `develop` (not just read) — see [PR #89's review thread](https://github.com/InfiniteZeroFoundation/DevNet/pull/89#issuecomment-5346477118), including real (unforced) execution of F1–F3, F7, F8 and a 160M-sample real-draw reproduction of F2's `-inf` bug. All findings held up; F4's structural claim is confirmed but its exact magnitude still wants a DP specialist's sign-off.

---

## Summary

The three mechanisms are not equivalent baselines. `update_gaussian` is structurally sound and worth building on. The two `post_training_*` mechanisms perturb the wrong quantity and should be labelled experimental only — they do not bound anything an attacker cares about, and keeping them at parity in the docs invites a model owner to pick one and believe they have privacy.

Separately, three implementation-level issues below would affect any epsilon you eventually try to claim, and one of them is a live correctness bug that will fire on any reasonably sized model.

---

## Findings

### F1 — `noise_multiplier` is not a multiplier (correctness + naming)

`add_gaussian_noise(weights, sigma)` uses the configured value directly as the standard deviation. In the standard formulation, `σ = noise_multiplier × sensitivity`, where sensitivity is the clipping norm.

As written, changing `clipping_norm` changes sensitivity but leaves the noise untouched, so the privacy level moves silently while the config looks unchanged. A model owner tightening `clipping_norm` from 1.0 to 0.5 would reasonably expect *more* privacy; they get the same absolute noise against a smaller signal — better privacy by accident, but not because the system tracked it.

Recommend either renaming the parameter to `noise_sigma`, or multiplying by `clipping_norm` at use site. The second is preferable because it is the form every accounting library expects.

### F2 — `laplace` inverse-CDF sampling can emit `-inf` (live bug)

```python
uniform = torch.rand_like(weights) - 0.5
noise = -scale * torch.sign(uniform) * torch.log1p(-2 * torch.abs(uniform))
```

`torch.rand_like` samples from `[0, 1)`, so `uniform` lands in `[-0.5, 0.5)`. The lower endpoint is attainable: when the draw is exactly `0.0`, `abs(uniform)` is exactly `0.5`, `log1p(-1.0)` is `-inf`, and that element of the tensor becomes infinite. It then propagates to NaN through aggregation.

For float32, `P(draw == 0.0) ≈ 2⁻²⁴ ≈ 5.96e-8`. On a 10M-parameter model that is roughly **0.6 expected occurrences per noising pass** — this is not a theoretical edge case, it will occur in normal operation within a few rounds.

Two fixes, either works: clamp `abs(uniform)` below `0.5` by an epsilon, or sample from `(0, 1)` exclusive. The interval is also asymmetric as written (closed at `-0.5`, open at `+0.5`), which introduces a small distributional bias independent of the `-inf` case.

Worth noting why this has not surfaced: all three tests in `tests/test_cache_client_dp.py` set the noise scale to `0.0`, which short-circuits both noise helpers on their early-return path. No test in the suite ever draws a random sample, so no test can reach this branch. A single test asserting `torch.isfinite(...).all()` on a real noised tensor would have caught it, and is worth adding alongside the fix.

### F3 — per-layer clipping does not compose to the stated bound

`clip_scope` defaults to `per_layer`. Clipping each of *n* floating tensors independently to norm *C* bounds the total L2 norm at `C·√n`, not `C` — but the same `σ` is applied to every tensor regardless. Effective privacy therefore degrades as model depth grows, invisibly, with no config change.

`clip_scope: global` is the only setting with a defensible sensitivity bound. The default is currently the weaker of the two. If per-layer is kept for utility reasons, the noise scale needs to account for *n*, and that relationship should be explicit in the manifest docs.

### F4 — Laplace noise is calibrated against an L2 clip (mismatch)

Laplace calibrates to **L1** sensitivity; the clipping here is **L2**. Converting between them costs a factor of up to `√d` in dimension, which for model weights is enormous. This means `post_training_laplace` cannot be given a meaningful ε through this code path even after accounting is added, without either switching to L1 clipping or absorbing a dimension-sized penalty.

I would treat this as a specialist confirmation point rather than a settled conclusion, but the mismatch is structural, not a tuning detail.

### F5 — clipping final weights is not a sensitivity bound

`post_training_gaussian` and `post_training_laplace` clip the *absolute trained weights*. DP sensitivity is about how much one participant's data can change the released output, not about the magnitude of that output. Two clients trained on completely different data can both sit inside radius *C* while differing from each other by up to *2C*.

So the clip in these two mechanisms buys no guarantee. It does actively harm utility, because rescaling absolute weights toward the origin distorts the function the network computes — unlike rescaling an update, which only shortens a step.

`update_gaussian` clips the delta relative to the round's starting model. That *is* a bound on the contribution of one local training run, and it is the same shape as DP-FedAvg. It is the only one of the three with a story that survives scrutiny.

### F6 — this is post-hoc perturbation, not DP-SGD

Noise is applied once, after training completes. During training itself, a single example can influence the weights without bound across many SGD steps. Per-example gradient clipping is what bounds individual contribution; clipping the end state does not reconstruct that property retroactively.

The practical consequence: the current baseline offers *client-level* obfuscation at best, and no *example-level* guarantee at all. That distinction matters most for the exact case the project cares about — a participant whose device holds data about one person.

### F7 — non-floating tensors bypass privacy entirely

`add_noise_to_state_dict` and `clip_state_dict` clone integer tensors through unchanged. For most architectures this is benign (`num_batches_tracked` and similar). It stops being benign for quantised models or anything storing integer-coded state, where a passthrough tensor could carry data-dependent information out unprotected. Worth an explicit note in the manifest docs rather than a silent behaviour.

Related: BatchNorm `running_mean` / `running_var` *are* floating point, so they do get noised — but they are direct summary statistics of the training data and a known leakage vector. They deserve mention in their own right.

### F8 — defaults and disable paths

- Absent `dp` block, or `dp.enabled: false`, uploads raw trained weights. Privacy is off by default. That is a reasonable engineering choice for a devnet, but it should be stated loudly in model-owner-facing docs, not just in code comments.
- `clipping_norm <= 0` silently disables clipping while noise still applies — producing noise with no sensitivity bound behind it, which is the worst of both worlds. Recommend rejecting non-positive clipping norms when DP is enabled rather than treating it as a no-op.
- `laplace_scale` defaults to `noise_multiplier`. Those two parameters have different units and different calibration; sharing a default invites misconfiguration.

---

## Answers to the review questions

**Which mechanisms are worth keeping as-is?**

Keep `update_gaussian` as the path forward — subject to F1 and F3. Reclassify `post_training_gaussian` and `post_training_laplace` as experimental baselines with an explicit note that they carry no formal guarantee (F5). `post_training_laplace` additionally needs F2 fixed before it is safe to run at all, and F4 resolved before it can ever carry an ε.

**What privacy claims can honestly be made today?**

Defensible today: *"Client updates are clipped and perturbed with calibrated noise before leaving the device, which reduces the fidelity of information recoverable from a single submission. This is a heuristic privacy layer; no formal guarantee is claimed."*

Overreach today: any use of the phrase "differentially private" without qualification, any (ε, δ) figure, any claim of protection against membership inference or reconstruction, and any comparison to DP-SGD. With no accountant and no per-example clipping, none of those are supportable.

I would specifically avoid the unqualified phrase "differential privacy" in model-owner-facing copy until F6 is addressed, because it carries a formal meaning that the current implementation does not deliver. This is the highest-risk item in the review from a governance standpoint — not because the code is bad for a devnet baseline, but because the vocabulary already promises more than the code does.

**Which model classes is this inadequate for?**

- **Embedding-heavy models and recommender systems** — worst case. Embedding rows map close to one-to-one onto individual users or items, so a single row carries individual-level information. Uniform noise across a sparse, high-dimensional table is both weak where it matters and destructive where it doesn't.
- **Transformers** — the parameter count makes uniform per-tensor noise a blunt instrument, and per-layer clipping (F3) degrades hardest exactly here. Memorisation of rare sequences is well documented and post-hoc weight noise is not a credible defence against it.
- **CNNs** — the least bad case. Dense, spatially redundant parameters tolerate noise relatively well, which is why the current baseline appears to work.
- **Any model with meaningful BatchNorm statistics** — see F7.

**Privacy-vs-utility tradeoff, in plain terms for a model owner:**

- `post_training_gaussian` — shrinks all weights toward zero, then blurs them. Costs accuracy in proportion to how aggressively you clip, and buys no guarantee. Treat the accuracy loss as the price of a rough obfuscation layer, not of privacy.
- `post_training_laplace` — same as above with heavier tails, so occasional large distortions to individual weights. Currently also carries the `-inf` risk in F2.
- `update_gaussian` — limits how far your model can move from the shared starting point in one round, then blurs that step. Costs convergence *speed* rather than final quality, because you take shorter, noisier steps toward the same place. This is the mechanism whose cost a model owner can reason about, and it is the one to recommend.

**What to prioritise, and why in this order:**

1. **F2 (`-inf` bug).** A correctness defect that will produce NaN models in normal operation. Nothing else matters if submissions are poisoned.
2. **F1 and F3 (sensitivity plumbing).** Noise must scale with the clipping norm, and clipping must compose to a bound you can name. Both are prerequisites for any accountant to produce a number that means anything — doing accounting first would just yield a confident wrong ε.
3. **Accountant integration (Opacus / RDP).** Once 1 and 2 are done, this converts the mechanism from "we add noise" to "we report (ε, δ)". This is the single highest-value governance step, because it turns claims into measurements.
4. **DP-SGD (per-example gradient clipping).** The real fix for F6, and the point at which "differentially private" becomes an honest description. Placed after accounting because accounting is cheaper, unblocks honest external communication immediately, and DP-SGD without accounting still cannot be reported.
5. **Adaptive clipping.** A utility optimisation on top of a correct foundation. Valuable, but only once there is a measured ε to trade against — otherwise you are tuning a quantity you cannot observe.

Update-level privatisation is already covered by `update_gaussian`, so I would fold it into item 2 rather than treat it as separate work.

---

## Note on method

I read the implementation and the review packet; I did not run the full training pipeline end to end. F2 was verified directly: `add_laplace_noise` was extracted verbatim from `cache_model_0/services/client.py` on `develop` and executed with `torch.rand_like` returning its attainable lower bound of `0.0`, which produced `tensor([-inf, -inf, -inf, -inf, -inf])`. The frequency estimate is analytic, derived from float32 sampling granularity rather than measured over a long run.

F4 in particular would benefit from a second opinion from someone with a formal DP background before it is treated as settled.
