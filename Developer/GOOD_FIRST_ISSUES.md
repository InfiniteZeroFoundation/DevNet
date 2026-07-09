# Good First Issues

Welcome to InfiniteZero Network DevNet. This is a live, open experiment in building a global AI commons, and there's real work to do.

This document is your entry point for beginner-friendly contributions across federated learning, privacy-preserving systems, blockchain coordination, and developer tooling. Each detailed issue lives in `Developer/issues/`.

---

## What We're Building

InfiniteZero is a protocol for collective AI training. Participants run lightweight validator nodes that help train, aggregate, and validate models, while raw data never leaves the device. Built on Ethereum. Governed by the community. Models belong to the commons.

Core components:

- Public blockchain coordination
- Validator-based aggregation
- IPFS-based model exchange
- Privacy-preserving AI training
- Trustless auditing and evaluation
- Scalable subgroup aggregation

---

## Contribution Areas

| Area | Description |
|---|---|
| Federated Learning | Local model training, aggregation, optimisation |
| Differential Privacy | DP-SGD, clipping, privacy accounting |
| Blockchain | Smart contracts, validator coordination |
| IPFS | Model storage and distribution |
| Aggregation | Validator-based decentralised aggregation |
| Evaluation | Contribution scoring and benchmarking |
| Security | Sybil resistance, secure aggregation |
| DevOps | Testing, CI/CD, Docker |
| CLI | `dincli` improvements |
| Documentation | Guides, onboarding, examples |

---

## Open Issues

### 0. Starter Task: Differential Privacy & Responsible AI Review

**Difficulty:** Beginner (review/analysis, not implementation)
**Area:** Privacy-Preserving Federated Learning / AI Governance
**Detailed issue:** [issues/dp-governance-review-starter-task.md](issues/dp-governance-review-starter-task.md)

A self-contained, no-coding-required entry point for contributors coming from an AI governance / responsible-AI / policy background rather than deep systems engineering. Review the three DP mechanisms already implemented for client model updates and assess them from a "what privacy claims can we honestly make" angle. Good first step before taking on implementation work in issue #1 below.

### 1. Differential Privacy Improvements

**Difficulty:** Beginner → Intermediate  
**Area:** Privacy-Preserving Federated Learning  
**Detailed issue:** [issues/DifferentialPrivacy.md](issues/DifferentialPrivacy.md)

Improve the current differential privacy workflow used in local training and model update submission.

Current focus areas:

- stronger privacy mechanisms beyond simple post-training perturbation;
- configurable clipping and noise settings;
- privacy accounting and reporting;
- better integration with `dincli`, client services, auditor workflows, and aggregation flows;
- clearer design guidance on when different model types should use different privacy mechanisms.

Important framing:

- different kinds of models may need different privacy mechanisms;
- a simple post-training mechanism may be acceptable for a small MLP baseline, but it may be a poor fit for CNNs, transformer-style models, recommender systems, sequence models, or embedding-heavy pipelines;
- we do not want to assume one DP mechanism is correct for every task shape.

#### What We Need From Contributors Or Reviewers

- assess whether the current mechanisms are technically appropriate for the model and training setup;
- explain how effective the current mechanisms are likely to be in practice;
- analyze the utility versus privacy tradeoff for each mechanism;
- identify which parts are acceptable baselines and which parts are only temporary heuristics;
- recommend which model classes likely need different privacy mechanisms entirely.

#### Questions We Want Answered

- Is `post_training_gaussian` a defensible baseline here, or only a placeholder?
- Is `post_training_laplace` useful in practice for this workflow, or mostly experimental?
- Is `update_gaussian` materially better aligned with federated learning than weight-level perturbation in this codebase?
- Which model families should use different privacy mechanisms entirely?
- What should be measured to compare privacy effectiveness against model utility?
- Should this roadmap move toward DP-SGD, per-layer clipping, adaptive clipping, accountant integration, or something else first?
- What privacy claims should we avoid making with the current implementation?

#### Curated Review Packet

Code and docs to review first:

- [cache_model_0/services/client.py](/home/azureuser/projects/devnet/cache_model_0/services/client.py)
- [cache_model_0/manifest.json](/home/azureuser/projects/devnet/cache_model_0/manifest.json)
- [cache_model_0/services/aggregator.py](/home/azureuser/projects/devnet/cache_model_0/services/aggregator.py)
- [dincli/services/runtime.py](/home/azureuser/projects/devnet/dincli/services/runtime.py)
- [dincli/cli/client.py](/home/azureuser/projects/devnet/dincli/cli/client.py)
- [dincli/services/client.py](/home/azureuser/projects/devnet/dincli/services/client.py)
- [tests/test_cache_client_dp.py](/home/azureuser/projects/devnet/tests/test_cache_client_dp.py)
- [Developer/issues/DifferentialPrivacy.md](/home/azureuser/projects/devnet/Developer/issues/DifferentialPrivacy.md)
- [Documentation/technical/services/clients.md](/home/azureuser/projects/devnet/Documentation/technical/services/clients.md)
- [Documentation/technical/manifest.md](/home/azureuser/projects/devnet/Documentation/technical/manifest.md)

Related reference material (Note: TKNN-Shapley is rejected for client model scoring due to FL privacy constraints - see [Rejected Ideas: TKNN-Shapley](issues/../rejected-ideas/tknn-shapley.md)):

- Threshold KNN-Shapley paper: <https://arxiv.org/abs/2308.15709>
- [TKNN-Shapley README](https://github.com/Jiachen-T-Wang/TKNN-Shapley/blob/main/README.md)
- [TKNN-Shapley helper_privacy.py](https://github.com/Jiachen-T-Wang/TKNN-Shapley/blob/main/helper_privacy.py)
- [TKNN-Shapley helper_knn.py](https://github.com/Jiachen-T-Wang/TKNN-Shapley/blob/main/helper_knn.py)
- <https://github.com/easeml/datascope>
- <https://github.com/daviddao/awesome-data-valuation>

#### What A Strong DP Review Should Include

- a critique of each implemented mechanism, not just a preferred replacement;
- explicit notes on which model and task types the current mechanisms fit or do not fit;
- utility-risk comments such as expected accuracy degradation, convergence issues, or update distortion;
- guidance on whether privacy should be applied to gradients, updates, weights, layers, logits, or scoring outputs for different scenarios;
- a prioritized recommendation list for implementation sequencing.

Relevant code paths:

- `cache_model_0/services/client.py`
- `cache_model_0/services/model.py`
- `cache_model_0/services/aggregator.py`
- `dincli/`

---

### 2. Client-Side Data Labeling & The Labeling Paradox

**Difficulty:** Intermediate → Advanced  
**Area:** Client Services & Tooling  
**Detailed issue:** [issues/client-data-labeling.md](issues/client-data-labeling.md)  
**Detailed tooling:** [tooling/client-labeling.md](tooling/client-labeling.md)

Address the challenge of client-side data labeling where raw edge data is unlabeled but federated learning requires high-quality labeled datasets.

Current focus areas:
- implementing PyTorch-based semi-supervised consistency regularization (e.g., FixMatch) locally;
- designing uncertainty/diversity active learning interfaces for client human-in-the-loop tagging;
- building data staging, auto-labeling, and quality analytics into `dincli` and client services.

#### Curated Review Packet
- [Developer/issues/client-data-labeling.md](/home/azureuser/projects/devnet/Developer/issues/client-data-labeling.md)
- [Developer/tooling/client-labeling.md](/home/azureuser/projects/devnet/Developer/tooling/client-labeling.md)
- [cache_model_0/services/client.py](/home/azureuser/projects/devnet/cache_model_0/services/client.py)
- [dincli/services/client.py](/home/azureuser/projects/devnet/dincli/services/client.py)

---

## How To Contribute

1. Pick an issue from this list
2. Read the detailed issue in `Developer/issues/`
3. Review relevant code paths before making changes
4. Implement with tests or supporting documentation
5. Submit a pull request with a clear explanation

```bash
git checkout -b feature/improve-differential-privacy
```

---

## Need Help?

Open a discussion or issue if you need onboarding help, architecture clarification, research direction, or implementation guidance.

We welcome contributors from AI/ML, cryptography, distributed systems, blockchain, privacy-preserving computing, and open-source communities.

[Contribution Guide →](https://github.com/InfiniteZeroFoundation/DevNet/blob/develop/Developer/CONTRIBUTING.md)  
[Getting Started →](https://github.com/InfiniteZeroFoundation/DevNet/blob/main/Documentation/GettingStarted.md)  
[Say hello →](mailto:abrahamnash@protonmail.com)
