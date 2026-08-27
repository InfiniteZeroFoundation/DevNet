# Rejected Idea: Stake-Weighted Validator Selection

**Tracking:** Issue #37 · staking-design.md §3.4 · MECHANISM_DESIGN §3
**Decision:** Rejected for DevNet 2.0. Stake gates eligibility only; it does not influence selection weight.

---

## Summary

Stake-weighted validator selection would assign higher probability of being selected for aggregation or auditing subgroups to validators who hold more DIN stake. This was considered as a way to align economic commitment with protocol influence.

**It is rejected.** Stake acts as a minimum eligibility bar — a validator must meet `minStake` to register — but all eligible validators above the floor are treated equally in selection.

---

## Why It Was Rejected

### 1. Concentrates work in whales

If selection probability scales with stake, validators with large balances receive disproportionately more assignment opportunities. Over time, work concentrates in a small set of high-stake operators, reducing the effective diversity of the validator set. DIN's security model depends on independent, uncorrelated validators producing scores and aggregations — concentration undermines that.

### 2. Weakens the cross-validator median

DIN's auditing layer relies on the median of independent evaluations to detect outliers and misbehaving aggregators. If high-stake validators are selected more often, the median is increasingly determined by a correlated subset. A coordinated group of high-stake validators could manipulate the median without triggering the outlier detection that a diverse random assignment would catch.

### 3. Creates a centralisation feedback loop

Higher stake → more assignments → more rewards → higher stake. This self-reinforcing dynamic tends toward a small oligopoly of validators and is inconsistent with the federated, decentralised nature of the DIN network.

### 4. Unnecessary for Sybil resistance

Stake's primary Sybil-resistance role is to make false-identity attacks expensive: an attacker needs `minStake` per identity to register multiple validators. This is fully achieved by the eligibility gate. Weighting adds no additional Sybil resistance while introducing the concentration problems above.

---

## What Stake Does Instead

- **Eligibility gate:** `getStake(validator) >= minStake` must hold for GI registration (and, once wired, `>= max(networkMin, modelMin)`).
- **Slashability:** Stake backs protocol commitments — misbehaviour costs real capital regardless of how much is staked above the floor.
- **Concurrent-registration cap:** `stake / slashableAmountPerRegistration` bounds how many GIs a single stake can back simultaneously (follow-up enforcement work).

Selection above the floor is random, producing an unbiased draw from the eligible validator set each GI. The selection engine design (randomness source, rotation, subgroup sizing) is tracked separately in `Developer/issues/validator_selection.md`.
