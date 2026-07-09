# Starter Task: Differential Privacy & Responsible AI Review

**Difficulty:** Beginner (review/analysis, not implementation)
**Area:** Privacy-Preserving Federated Learning / AI Governance
**Best fit for:** contributors with an AI governance, policy, or responsible-AI background who also have a CS/engineering foundation — this task is scoped as a structured review, not a coding task, so it's a good entry point before taking on implementation work.

## Why This Task

InfiniteZero's federated learning pipeline currently applies differential privacy (DP) to client model updates before they are shared on-chain/IPFS. The mechanisms are implemented (see below) but have never been reviewed from a "is this a defensible privacy claim" / governance angle — only from an engineering-correctness angle. That's exactly the gap a Responsible AI / AI governance background is suited to close, and it doesn't require deep familiarity with this codebase's stack (Solidity, web3, IPFS) to do well.

This is the full "DP Expert Review Request" already scoped in [DifferentialPrivacy.md](DifferentialPrivacy.md#dp-expert-review-request), pulled out here as a self-contained starter task.

## What You're Reviewing

Three manifest-driven DP mechanisms currently implemented in client-side training:

- `post_training_gaussian` — clips final model weights, adds Gaussian noise.
- `post_training_laplace` — clips final model weights, adds Laplace noise.
- `update_gaussian` — clips the local update relative to the starting model, adds Gaussian noise, reconstructs the full weight file.

None of these currently report measurable privacy guarantees (no epsilon/delta accounting). Parameters (`clipping_norm`, `noise_multiplier`, `laplace_scale`) are configured per-model via the manifest.

## Review Packet (read in this order)

1. [Developer/issues/DifferentialPrivacy.md](DifferentialPrivacy.md) — full context, limitations, product direction
2. [cache_model_0/services/client.py](/home/azureuser/projects/devnet/cache_model_0/services/client.py) — the actual mechanism implementations
3. [cache_model_0/manifest.json](/home/azureuser/projects/devnet/cache_model_0/manifest.json) — how DP parameters are configured per model
4. [Documentation/technical/services/clients.md](/home/azureuser/projects/devnet/Documentation/technical/services/clients.md)
5. [Documentation/technical/manifest.md](/home/azureuser/projects/devnet/Documentation/technical/manifest.md)
6. [tests/test_cache_client_dp.py](/home/azureuser/projects/devnet/tests/test_cache_client_dp.py) — current test coverage, useful for seeing expected behavior without reading all of client.py in depth

You do not need to read the Solidity contracts or `dincli` CLI internals to do this review.

## Questions To Answer

- Which of the three implemented mechanisms are useful enough to keep as-is, and which should be treated as temporary baselines only?
- What privacy claims can we honestly make today, and which claims would be overreach given there's no epsilon/delta accounting?
- Which model classes (CNNs, transformers, recommender systems, embedding-heavy models) would this baseline be inadequate for, and why?
- What's the privacy-vs-utility tradeoff a model owner should expect from each mechanism, in plain terms a non-specialist model owner could understand?
- What should be prioritized next — accountant integration (e.g. Opacus/RDP), DP-SGD, adaptive clipping, or update-level privatization — and why that order?

## Deliverable

A short written review (markdown, doesn't need to be long) covering the questions above, submitted as a PR adding a `REVIEW.md` (or similar) under `Developer/issues/`, or as comments on the tracking issue if one exists on GitHub. Code changes are not expected for this task — the goal is to produce a governance-grade assessment the engineering team can act on.

## How To Contribute

1. Fork the repo, checkout `develop` (see [DEVELOPMENT_SETUP.md](../DEVELOPMENT_SETUP.md) if you want to run anything locally — not required just to read code).
2. Work through the review packet above.
3. Write up your findings against the questions listed.
4. Open a PR or discussion with your review.

Questions welcome — see [Say hello →](mailto:abrahamnash@protonmail.com).
