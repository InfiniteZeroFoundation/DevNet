# Good First Issues

Welcome to InfiniteZero Network DevNet. This is a live, open experiment in building a global AI commons — and there's real work to do.

This document is your entry point for beginner-friendly contributions across federated learning, privacy-preserving systems, blockchain coordination, and developer tooling. Each detailed issue lives in `Developer/issues/`.

---

## What we're building

InfiniteZero is a protocol for collective AI training — participants run lightweight validator nodes that help train, aggregate, and validate models, while raw data never leaves the device. Built on Ethereum. Governed by the community. Models belong to the commons.

Core components:

- Public blockchain coordination
- Validator-based aggregation
- IPFS-based model exchange
- Privacy-preserving AI training
- Trustless auditing and evaluation
- Scalable subgroup aggregation

---

## Contribution areas

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

## Open issues

### 1. Differential Privacy Improvements

**Difficulty:** Beginner → Intermediate
**Area:** Privacy-Preserving Federated Learning
**Detailed issue:** [issues/DifferentialPrivacy.md](issues/DifferentialPrivacy.md)

Improve the current differential privacy workflow used in local training and model update submission. Contributors will explore:

- Stronger privacy mechanisms beyond post-training weight perturbation
- Configurable clipping and noise settings
- Privacy accounting and reporting
- Better integration with `dincli`, client services, auditor workflows, and aggregation flows

Relevant code paths:
- `cache_model_0/services/client.py`
- `cache_model_0/services/model.py`
- `dincli/`

---

## How to contribute

1. Pick an issue from this list
2. Read the detailed issue in `Developer/issues/`
3. Review relevant code paths before making changes
4. Implement with tests or supporting documentation
5. Submit a pull request with a clear explanation

```bash
git checkout -b feature/improve-differential-privacy
```

---

## Need help?

Open a discussion or issue if you need onboarding help, architecture clarification, research direction, or implementation guidance.

We welcome contributors from AI/ML, cryptography, distributed systems, blockchain, privacy-preserving computing, and open-source communities.

[Contribution Guide →](https://github.com/InfiniteZeroFoundation/DevNet/blob/develop/Developer/CONTRIBUTING.md)
[Getting Started →](https://github.com/InfiniteZeroFoundation/DevNet/blob/main/Documentation/GettingStarted.md)
[Say hello →](mailto:abrahamnash@protonmail.com)
