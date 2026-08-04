# DIN White Paper — Summary & Implementation Mapping

> **Source:** [Decentralized Intelligence Network (DIN)](https://github.com/InfiniteZeroFoundation/White-Paper/blob/main/Decentralized%20Intelligence%20Network%20(DIN).pdf.zip), Abraham Nash (23 pp., zip published Jun 2026).
> **Purpose of this document:** working summary of the white paper for aligning ROADMAP.md, `Documentation/`, and `issues/` with the canonical protocol design. Section references (§) are to the white paper.

---

## 1. One-paragraph summary

DIN is a framework for training AI models on data that never leaves its owners' decentralized data stores. It combines (1) participant-owned data stores, (2) a scalable federated-learning (FL) protocol coordinated by smart contracts on a public blockchain with model artifacts on IPFS, and (3) a trustless, cryptographically enforced rewards mechanism with decentralized auditing. The central design move is replacing the central FL server with staked, randomly assigned **Validators** organized into subgroups, so that aggregation, coordination, and rewards are all peer-to-peer with no gatekeeper.

## 2. Problem statement & requirements (§2)

Problems addressed: data ownership loss, siloed/fragmented data limiting AI, access barriers for developers, misaligned incentives for data providers, centralization risk (walled gardens, power concentration), breach exposure, and AI-safety concerns of ever-larger centralized models.

Three hard requirements (§2.1) — useful as acceptance criteria for any protocol change:

1. **Data Ownership** — participants retain full control of their data stores; no entity can manage or control their data.
2. **Decentralized AI** — data access for FL is opt-in by participants; no entity can deny model owners access to data participants chose to contribute.
3. **Direct Rewards** — reward distribution is transparent and decentralized, with no third-party intermediary deciding compensation.

Everything is organized around three orchestration components: **Aggregation, Coordination, Rewards**.

## 3. Roles (§4)

| White paper role | Responsibility | DevNet equivalent |
|---|---|---|
| **Participant** | Owns a data store, opts into FL, trains locally, submits encrypted model updates | `client` role in `dincli` |
| **Model Owner** | Deploys the "intelligence" smart contracts, publishes genesis model + encrypted test set, deposits rewards, finalizes global model | `model-owner` role; `DINTaskCoordinator`/`DINTaskAuditor` deployer |
| **Validator** | Staked node; aggregates model updates, evaluates/audits contributions, distributes rewards; slashed for misbehavior | Split in DevNet into **aggregator** + **auditor** roles staked via `DinValidatorStake` |

Note the terminology delta: the paper uses one "Validator" entity for both aggregation and evaluation duties; the DevNet implementation splits this into aggregator and auditor. Documentation should state this mapping explicitly.

## 4. Core mechanisms

### 4.1 Aggregation (§3.2)

- Participants are partitioned into **aggregator subgroups** (example: 1,000 participants → 10 subgroups of 100), each with Validators assigned at roughly a **1:10 validator-to-participant ratio**.
- Each Validator independently aggregates its subgroup's updates on its own hardware, publishes results to IPFS; the smart contract verifies all Validators reached the same result. Off-chain first, escalating on-chain only on discrepancy (cost optimization).
- Random validator assignment + staking + **>50% agreement threshold** provide Sybil/collusion resistance; misbehaving validators are slashed.
- Secure aggregation keeps individual updates uninspectable; the paper claims collusion cannot reveal a participant's data when N ≥ 3; differential privacy is a further optional layer.

### 4.2 Coordination (§3.3, §5.1)

- A public blockchain smart-contract protocol replaces the central coordinator (explicitly modeled on Bonawitz et al. 2019 scalable-FL architecture, decentralized).
- Public chain (not private/consortium) is a deliberate requirement — prevents re-centralization and institutional gatekeeping.
- IPFS is the off-chain artifact layer; only CIDs and coordination state go on-chain.

### 4.3 Training-round protocol (§5.1, Figure 1)

1. Model Owner deploys the intelligence SC(s) (may be several contracts: protocol, validator registry, staking, aggregation management, reward distribution), uploads genesis model to IPFS, records CID, deposits rewards.
2. Participants download genesis model, train locally, encrypt updates (secure aggregation / DP), upload to IPFS, record CIDs on-chain.
3. Validators (random, staked, subgrouped) fetch encrypted weights by CID, aggregate independently; >50% subgroup consensus required; mismatch triggers on-chain dispute; losers of disputes are slashed.
4. Model Owner sums subgroup results into the new global model; the SC tracks the expected sum so participants can verify the published global model on-chain (tamper-evidence against the Model Owner too).
5. Rounds repeat until the Model Owner signals the final round (one extra round then occurs, signaled on-chain).
6. Post-training: encrypted test dataset published → validator evaluation → reward distribution (see below).

This corresponds closely to the DevNet **Global Iteration (GI)** lifecycle (registration → LMS → evaluation → T1/T2 aggregation → slashing → GI end). The paper's "subgroup then sum" model maps to the DevNet two-tier (T1 sub-batch / T2 combine) aggregation.

### 4.4 Rewards & decentralized auditing (§3.4, §5.2)

- Key scalability contribution vs. prior art (BlockFlow, 2CP): **role delineation** (not every participant evaluates) and a **validator-to-participant ratio Q ≪ N** instead of 1:1 all-pairs evaluation.
- The Model Owner publishes an **encrypted test dataset** to IPFS. Key distribution scheme (§5.2.3b): CID signed with owner's key, symmetrically encrypted with random key K; K encrypted per-validator with each validator's public key; mapping stored on-chain. Single CID location, linear key growth, gas-efficient.
- **Test-set resampling strategy:** a reserved pool (e.g. 40% of the dataset); each round evaluates on a resampled half of the pool (~20% of total); the **final round uses the full 40%** without resampling. Mitigates leakage/overfitting if the test set is partially exposed.
- Scoring: contributivity procedures — BlockFlow-style **median scoring** (scores >0.5 from median → score 0, a-priori score 0.5) or 2CP/Substra step-by-step evaluation. Gross deviations (>50%) penalized; commit-then-reveal (secret sharing / ECDH) prevents validators copying each other's scores.
- Rewards distributed by the SC proportionally to verified scores. The paper explicitly prefers market-utility valuation over Shapley-based contribution measures (relevant precedent: `rejected-ideas/` TKNN-Shapley).
- Future hardening: homomorphic encryption / ZKPs (Zama, EZKL cited) so validators can prove correct evaluation without ever seeing the test data.

### 4.5 Threat model (§6)

Resilient to **M < N/2** malicious actors per group, resting on:

1. Public-chain PoS security (Ethereum assumption).
2. Sybil resistance via decentralized identity / verifiable credentials / staking (multi-enrollment countered).
3. IPFS immutability — models can't be swapped after CID commitment; model availability guaranteed if >N/2 honest parties re-share.
4. Contribution-scoring penalties against malicious models (random weights, inverted labels): median scoring bounds the damage while honest validators are the majority.
5. Data/model-sharing collusion among participants is explicitly **not** treated as an attack (equivalent to strong overlapping datasets).
6. Encrypted test dataset + resampling + median scoring against reward-manipulation collusion.
7. Validators gated: test-set access only after training complete and rewards deposited; randomness in group assignment limits targeted leakage.

Slashing consequences (§8.1): immediate slash for incorrect aggregation scores or deviant evaluations; **delegators to a slashed validator lose a % of their stake**; slashed validators are permanently removed and must re-register a new validator identity. → Direct input to P3-4.x slashing-conditions spec.

## 5. Tokenomics & governance (§8)

- **PoS with a native ERC-20 staking token**; anyone who stakes can validate. (Earlier NFT-leased-validator PoS experiments are historical — see arXiv versions.)
- **Chain-agnostic** posture; validator revenue: aggregation services, compute provision, evaluation services, network fees in native chain currency (ETH on Optimism/Arbitrum-style L2s). A dedicated "Layer AI" chain is floated as a possible future.
- **DPoS delegation**: token holders can delegate to validators without running nodes; no minimum for delegators (validators do have minimums); commission on delegation rewards; auto-compounding.
- Emission: inflation-funded staking rewards with an Ethereum-2-style decreasing rate, plus fee-funded burn.
- **Governance:** DIN Proposal Protocols (DPPs); **non-coin-based voting credits** for most decisions (anti-plutocracy), community vote required for economic-parameter changes; infrastructure improvements can ship without a vote.
- **Public goods:** a share of network fees to open-source funding via quadratic funding (Gitcoin/GovGit-style).
- Privacy default: data-owner encryption of model updates, but open/unencrypted updates are a per-application choice (§8.4, §9 open-source discussion).

## 6. Applications (§7)

DePIN, decentralized smart cities, DeFi, DeHealth, DeEdTech, DeSo — all the same pattern: data stays in participant stores, FL trains the shared model, stablecoin/token rewards close a circular economy. Useful vocabulary for outreach docs and use-case pages, not protocol-binding.

## 7. Emphases relevant to future phases (§9, §10)

- **Asynchronous FL orchestration** — decoupled event-driven processing, adaptive synchronization, fault-tolerant update propagation, dynamic on/offboarding, non-blocking submissions, backpressure/load-balancing. This is effectively a requirements list for the **P4 `dind` daemon**.
- **Small models first (SLMs)** — consumer/edge hardware, resource-efficient models over LLM-centric scaling; supports the roadmap's smaller-model/test-environment expansion goal.
- **Steady-state assumption flagged**: fixed validator/participant ratios per subgroup per round are assumed; dynamic ratios are open research.
- **Open problems** the paper leaves for us: empirical validation of the validator ratio under adversaries, heterogeneous-data stress testing, dynamic membership, proprietary-model/private-dataset reward attribution, affordable HE/ZKP integration.

## 8. Gap / alignment checklist (DevNet vs. white paper)

Items to feed into ROADMAP.md, `Documentation/`, and `issues/`:

| # | White paper element | DevNet status | Suggested action |
|---|---|---|---|
| 1 | Single "Validator" role (aggregate + evaluate) | Split into aggregator/auditor roles | Document the mapping in `Documentation/public/`; keep the split (it matches the paper's role-delineation rationale) |
| 2 | Random validator assignment to subgroups | Assignment mechanism status unclear in docs | Verify implementation; if absent, open an issue — randomness is load-bearing for the threat model |
| 3 | >50% consensus + off-chain-first aggregation w/ on-chain dispute escalation | Two-tier aggregation + dispute resolution in P3 slashing work | Cross-check P3-4.x specs against §5.1.3d–e semantics |
| 4 | Slashing: immediate slash, delegator penalty %, permanent removal | P3-4.1 slashing conditions in progress | Ensure delegator penalty and permanent-removal semantics are considered (delegation itself is not yet implemented — see #7) |
| 5 | Encrypted test dataset + per-validator key mapping (§5.2.3b) | Auditor test-data flow exists via `modelowner.py` services | Compare against the paper's on-chain key-mapping scheme; open design issue if the current flow is plaintext or centrally shared |
| 6 | Test-set resampling (40% pool / ~20% per round / full 40% final) | Not visible in current docs | Candidate `issues/` entry for the evaluation pipeline |
| 7 | DPoS delegation, no delegator minimum, commissions, auto-compounding | Not implemented | Feeds P3 token-utility design (Weeks 11–13); decide in/out of scope for P3 |
| 8 | Inflation emission + fee burn (Eth2-style decay) | P3 emission-model task upcoming | Use §8.1 as the reference model |
| 9 | Non-coin-based voting (DPPs), quadratic public-goods funding | P3 DAO-governed parameter controls planned | Governance design should note the paper's anti-plutocratic stance |
| 10 | Asynchronous FL orchestration requirements (§9) | P4 `dind` daemon phase | Import §9's async bullet list into the P4 design doc as requirements |
| 11 | BlockFlow median scoring, commit-then-reveal between validators | BlockFLow-inspired scoring shipped (WP 2.2); hardening in P3 | Verify commit-then-reveal (anti score-copying) is included in the hardening scope |
| 12 | HE/ZKP validator evaluation (Zama, EZKL) | Not started | Long-term; park as `discussion/` or future-phase item |
| 13 | Decentralized identity / verifiable credentials for Sybil resistance | Staking only today | Note as open item; the paper cites DIDs/VCs as complements to staking |
| 14 | Market-utility over Shapley valuation | Matches `rejected-ideas/` (TKNN-Shapley) | Alignment confirmed — cite the paper in the rejection rationale |

---

*Extracted from the PDF at `~/projects/HR/roadMap/Decentralized Intelligence Network (DIN).pdf` (July 19, 2026).*
