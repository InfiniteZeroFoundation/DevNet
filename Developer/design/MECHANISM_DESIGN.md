# DIN DevNet 2.0 — Cryptoeconomic Mechanism Design

**Status:** Working design document — immediate requirement for DevNet 2.0
**Owner:** Umer
**Scope:** Consolidated design for staking, slashing, rewards, scoring/auditing, tokenomics, and fees, organized by network role.
**Roadmap anchors:** P3-4.1/4.2/4.3 (slashing), P3-SCR (scoring), P3-5.1/5.2/5.3 (token utility, emission, fees), P3-DOC2/3/5 (public docs).

---

## 1. Role × Mechanism Matrix

This is the one-page view. Every mechanism below is designed per role — a mechanism that isn't tied to a role and a concrete misbehaviour/contribution is out of scope.

| Role | Stakes? | Slashable? | Earns rewards? | Pays fees? | Scored/audited? |
|---|---|---|---|---|---|
| **Client** | No (data contributor, low barrier) | No | ✅ Yes — proportional to BlockFLow contribution score | No | ✅ Yes — local model updates scored by auditors |
| **Auditor** | ✅ Yes (validator stake) | ✅ Yes — liveness + correctness | ✅ Yes — per-GI evaluation service fee share | No | Indirectly — cross-auditor median exposes outliers |
| **Aggregator** | ✅ Yes (validator stake) | ✅ Yes — liveness + correctness | ✅ Yes — per-GI aggregation service fee share | No | Indirectly — T1/T2 output verifiable against inputs |
| **Model owner** | No (pays instead) | No (loses fees/deposit on abandonment) | Gets the trained model | ✅ Yes — registration fee + per-GI service fee + reward deposit | No |
| **DIN-Representative / DAO** | No | No | Treasury cut of all fees | No | Governance-accountable, not economically |
| **Treasury** | — | — | Receives network fee split + (decision pending) slashed stake | — | — |

Design principle: **clients face zero economic barrier** (staking clients would kill data-contribution supply; Sybil resistance for clients comes from scoring, not stake). **Validators (auditors + aggregators) face full economic accountability** (stake → slash → reward is their loop). **Model owners are the paying customers** whose fees fund validator rewards and the treasury.

---

## 2. Current On-Chain State (what DevNet 1.0 already has)

Grounding: everything below references `foundry/src/` as of `develop`.

| Mechanism | Implemented today | Gap for 2.0 |
|---|---|---|
| **Staking** | `DinValidatorStake`: flat `MIN_STAKE = 10 DIN`, 7-day `UNBONDING_PERIOD`, pending withdrawals remain slashable, blacklist, slasher registry (task contracts authorized via `DinCoordinator`) | No role-specific stake sizing, no stake-weighted selection, single pending withdrawal only, no delegation |
| **Slashing** | Liveness-only, flat `minStake()` amount: `DINTaskAuditor.slashAuditors` (missed vote), `DINTaskCoordinator.slashAggregators` (missed T1/T2 submission). Slashed stake is decremented in place — it stays locked in the stake contract (de facto burn), no redistribution | No correctness-based slashing, no partial/full tiers, no dispute resolution, no explicit destination for slashed stake |
| **Rewards** | `DINTaskAuditor.totalDepositedRewards` + `RewardDeposited` event — deposits are recorded but **there is no distribution or claim logic at all** | Entire reward engine: funding, per-GI settlement, claim flow |
| **Scoring** | On-chain: auditor score submission (`setAuditScorenEligibility`), pass-score eligibility voting, `finalizeEvaluation`, `setTier2Score`. Off-chain: BlockFLow-inspired scoring implemented in Python (WP 2.2 ✅, validation pending P3-SCR) | Median aggregation of auditor scores on-chain, score → reward wiring, score-deviation detection for auditor slashing |
| **Tokenomics** | `DinToken` minted only via `DinCoordinator.depositAndMint` (ETH → DIN at `dinPerEth = 1,000,000`), owner can withdraw deposited ETH. No cap, no burn, no emission | Supply policy, emission schedule, burn sinks, treasury |
| **Fees** | `DINModelRegistry`: ETH registration + manifest-update fees (open-source vs proprietary tiers), `withdrawFees` to owner | Per-GI service fees, treasury routing, fee splits, dynamic fees, storage cost line item |

---

## 3. Staking — auditors & aggregators

**Goal:** every validator action is backed by capital at risk that exceeds the profit from cheating on one GI.

### Design

1. **Who stakes:** auditors and aggregators only. One stake pool (`DinValidatorStake`) covers both roles — a validator's stake backs whichever role(s) it registers for in a GI. Keep the unified pool for 2.0 (simpler accounting, slashers already wired); revisit per-role pools only if role risk profiles diverge materially.
2. **Stake sizing:**
   - Keep a network-wide `minStake` floor (DAO-settable, replacing the `constant`).
   - Add a **per-model stake requirement** settable by the model owner at task deploy (bounded by DAO min/max) so high-value models can demand more skin in the game.
   - Registration for a GI should check `getStake(validator) >= max(networkMin, modelMin)` — today it only checks activity.
3. **Stake-at-risk accounting:** a validator registered in N concurrent GIs has the same stake backing all N. For 2.0, cap concurrent registrations per validator (e.g., stake must cover `k × slashable-amount` across active registrations) to prevent one 10-DIN stake backing 20 tasks.
4. **Unbonding:** keep 7 days, keep unbonding stake slashable (already correct). Fix the single-pending-withdrawal limitation (queue of withdrawals) as a quality-of-life item, not a blocker.
5. **Selection weighting:** for 2.0, registration remains permissionless above min stake; batch assignment stays random/rotational. Stake-weighted selection is deliberately **not** adopted (it concentrates work in whales and weakens the cross-validator median). Document as a rejected idea.
6. **Sybil bound:** minimum stake × validator-to-participant ratio is the Sybil barrier (Roadmap §5). The DAO parameter set must include both.

### Parameters (DAO-settable via P3-5.1 governance hooks)

`minStake`, `unbondingPeriod`, `maxConcurrentRegistrationsPerStakeUnit`, `modelMinStakeBounds[min,max]`.

### Open decisions

- Per-role min stake (auditor vs aggregator) — recommend **no** for 2.0, single floor.
- Delegation — out of scope until P5+.

---

## 4. Slashing — auditors & aggregators (P3-4.1 / 4.2 / 4.3)

**Goal:** misbehaviour is cheaper to punish than to commit; honest-but-offline is punished less than malicious.

### Slashing conditions taxonomy

| # | Condition | Role | Detection | Tier |
|---|---|---|---|---|
| S1 | Missed audit vote in assigned batch | Auditor | On-chain (already implemented) | Partial |
| S2 | Missed T1/T2 aggregation submission | Aggregator | On-chain (already implemented) | Partial |
| S3 | Score deviation beyond threshold from cross-auditor median (per model, per GI) | Auditor | On-chain comparison at `finalizeEvaluation` — requires median computed on-chain | Partial → Full on repeat |
| S4 | Invalid aggregation: submitted T1/T2 CID whose recomputation from inputs fails verification | Aggregator | Off-chain challenge + on-chain dispute (S4 is the main dispute-resolution consumer) | Full |
| S5 | Repeated liveness failures (≥ `r` partial slashes within `w` GIs) | Both | On-chain counter | Full + jail/blacklist |
| S6 | Registration without capacity (registers, never participates, across models) | Both | On-chain counter | Partial, escalating |

### Penalty tiers

- **Partial slash:** fixed fraction of `minStake` (e.g., 25–50%), not the flat `minStake()` used today — today's flat amount fully unstakes a floor-staked validator for one missed vote, which over-punishes liveness faults. Make the fraction a DAO parameter.
- **Full slash:** entire slashable stake (active + unbonding) + blacklist. Reserved for provable malice (S4) and recidivism (S5).
- **Jailing:** `_syncValidatorStatus` already produces a Jailed state below min stake; keep — jailed validators cannot register until they top up.

### Slashed-stake destination (decision required in P3-4.2)

Options: (a) burn, (b) treasury, (c) redistribute to honest validators of the same GI, (d) split.
**Recommendation: split — 50% burn / 50% treasury.** Burning creates a deflationary sink and avoids perverse incentives (validators profiting from peers being slashed encourages false disputes); the treasury half funds dispute adjudication costs. Do **not** redistribute to the reporting validator beyond a fixed dispute bounty (see below). Today's behaviour (tokens stranded in the stake contract) is an accidental burn — make it explicit either way.

### Dispute resolution (P3-4.3)

- Any staked validator can open a dispute against an S3/S4 outcome within a **dispute window** (e.g., 1 GI or fixed time) by posting a **dispute bond** (forfeited if frivolous, returned + fixed bounty from treasury if upheld).
- Upheld dispute → re-evaluation by a **fresh validator subgroup** (reassignment selector excludes accused + original batch).
- Failure modes to document (P3-DOC3): validator offline mid-evaluation, dispute window expiry, all-validator collusion (out of threat scope > ~50%, per Roadmap §5).

### Invariants (feed P3-6.3b fuzz tests)

- Total staked supply never increases after a slash.
- Slashed amount always reaches its declared destination (burn address / treasury), never a third party.
- A slash can never make `activeStake + pendingWithdrawals` negative or leave a validator Active below min stake.

---

## 5. Rewards — clients, auditors, aggregators

**Goal:** every honest contribution in a GI is paid, proportionally to value, from a funded per-GI pool. Today there is **no** payout path — this is the largest 2.0 gap.

### Funding: the per-GI reward pool

Each GI's pool is funded from (in priority order):

1. **Model-owner reward deposit** — the existing `totalDepositedRewards` deposit in `DINTaskAuditor`, made a *precondition of `startGI`* (a GI cannot open unless the pool covers the configured per-GI minimum). Market-set: model owners compete for validator/client attention via pool size (P3-5.1 "market-set pool").
2. **Protocol emission top-up** (bootstrap phase only) — per-GI minted subsidy from the emission contract (P3-5.2), decaying on schedule, so early networks with few paying model owners still reward participation. Steady state: fees fund everything, emission → 0.

### Split across roles (DAO-settable fractions, initial proposal)

| Share | Recipient class | Basis |
|---|---|---|
| **60%** | Clients | Proportional to BlockFLow marginal-gain score among *accepted* models (score ≤ 0 or rejected ⇒ 0) |
| **20%** | Auditors | Equal per completed audit assignment in the GI (correctness enforced by slashing, not reward weighting — mirrors BlockFLow's dropped honesty-score, Roadmap §2) |
| **15%** | Aggregators | Per finalized T1/T2 batch completed |
| **5%** | Treasury | Network cut (see Fees §7) |

### Settlement & claims

- **Settlement cadence:** per-GI, at `endGI`. `endGI` computes each participant's entitlement and credits an on-chain `claimable[address]` balance — **pull-payment claim pattern** (`claimRewards()`), never push transfers in loops (gas + reentrancy).
- **What's on-chain vs off-chain:** scores land on-chain (auditor submissions, already implemented); the median + proportional split must be computed on-chain at settlement so payouts are verifiable. Heavy scoring math stays off-chain in the Python services; the chain only sees submitted scores.
- **Unclaimed rewards:** claimable indefinitely; no expiry for 2.0.
- **Anti-gaming:** duplicate-update discounting is inherent in BlockFLow sequential fold-in (P3-SCR verifies); score inflation by a single auditor is bounded by the median; a client scoring ≤ pass-score threshold earns nothing, so spam costs compute for zero return.

### Open decisions

- Exact split percentages (simulate in P3-5.2 at 10–50 validators / 100–500 clients per model).
- Whether aggregator reward should scale with batch size (recommend yes, linear in models aggregated).
- Denominating pool minimums in DIN vs fiat-oracle terms — recommend plain DIN for 2.0, no oracle dependency.

---

## 6. Scoring & auditing — client local models (WP 2.2 ✅, P3-SCR)

**Goal:** turn each client's submitted update into (a) an accept/reject decision and (b) a contribution score driving reward share — without auditors ever seeing raw data.

### Pipeline (per model, per GI)

1. **Pre-filters (cheap, off-chain, per auditor):** norm-bound check (rejects scaling/garbage), basic sanity (shape, dtype, NaN).
2. **BlockFLow-inspired scoring (off-chain, per auditor):** marginal-gain of the update vs current global model on the auditor's held-out audit test set (assigned via `assignAuditTestDataset`); cosine-to-consensus; sequential fold-in with permutation averaging (discounts duplicates).
3. **On-chain submission:** each auditor in the batch submits score + eligibility vote (`setAuditScorenEligibility`) — already implemented.
4. **Consensus:** **median across the auditor batch** is the canonical score (tolerates < 50% dishonest auditors). 2.0 change: compute the median on-chain at `finalizeEvaluation` so it is the slashing reference (S3) and the reward basis (§5) — today eligibility voting exists but the canonical per-model score isn't derived on-chain.
5. **Eligibility:** median ≥ `passScore` (`updatePassScore`, exists) ⇒ model enters T1 aggregation; else rejected, zero reward.
6. **Auditor accountability:** |auditor score − median| > deviation threshold ⇒ S3 slash candidate. Threshold must be validated empirically in P3-SCR before slashing on it (avoid punishing honest variance from heterogeneous audit test sets — start with a wide threshold + warning-only "shadow mode" for the first weeks of DevNet 2.0, then tighten).

### Threat coverage (per Roadmap §5)

In scope: crude poisoning (label-flip, sign-flip, scaling, garbage — caught by norm bound + marginal-gain gate), Sybil clients (spam costs compute, earns nothing below pass score), score inflation (median-bounded). Out of scope for 2.0: backdoors (RES-2), >50% auditor collusion.

### Aggregator auditing

T1/T2 outputs are deterministic functions of accepted inputs ⇒ verifiable by recomputation. 2.0 mechanism: any validator may recompute and open an S4 dispute; no proactive re-audit of every batch (cost). Proactive spot-checking can come later.

---

## 7. Tokenomics — DIN token (P3-5.1 / 5.2)

**Goal:** DIN is the unit of stake, reward, and fee — with a supply policy that doesn't hyperinflate during bootstrap or starve rewards at steady state.

### Utility (demand sinks)

1. **Staking** — validators must hold and lock DIN (the primary sink).
2. **Fees** — model-owner fees payable in DIN (see migration note in §8; today they're ETH).
3. **Reward-pool deposits** — model owners pre-fund GI pools in DIN.
4. **Governance** — future DAO weight (P5+, design hook only).

### Supply policy

| Flow | Mechanism | 2.0 design |
|---|---|---|
| **Mint — deposit** | `depositAndMint` ETH→DIN at `dinPerEth` (exists) | Keep for devnet as the faucet/on-ramp; the deposited ETH backing should route to treasury, not `owner()` withdrawal. Flag: this is effectively an unlimited mint at a fixed admin-set rate — acceptable for devnet, must be capped or replaced before any real-value network. |
| **Mint — emission** | None today | New emission contract (P3-5.2): per-GI reward subsidy, **diminishing schedule** (recommend geometric decay per epoch), hard `MAX_SUPPLY` cap, inflation guard (per-GI mint ceiling), mint triggers tied to GI lifecycle events only. |
| **Burn — slashing** | Accidental (stranded in stake contract) | Explicit: slashed-stake burn share (§4). |
| **Burn — fees** | None | Optional: burn a fraction of protocol fees (decide in P3-5.3; start at 0%, keep the hook). |
| **Treasury** | None (owner-withdraw patterns) | Dedicated treasury address/contract receiving: network fee split, slashed-stake share, deposit backing. DAO-controlled spend (multisig path per Roadmap §1). |

### Modelling requirement (P3-5.2, before contracts)

Simulate: does the pool + emission produce stable validator income at target / 10× / 0.1× participation? Wrong answers here are expensive post-audit — design time is scheduled ahead of contract code, keep it that way.

---

## 8. Fee mechanism — model owners & network treasury (P3-5.3)

**Goal:** model owners pay for the network services they consume; a slice of every flow sustains the treasury.

### Fee lines

| Fee | Payer | When | Exists today? | Routing |
|---|---|---|---|---|
| **Model registration fee** (open-source vs proprietary tiers) | Model owner | `requestModelRegistration` | ✅ (ETH, in `DINModelRegistry`, owner-withdrawable) | → treasury (change from `withdrawFees(owner)`) |
| **Manifest update fee** | Model owner | `requestManifestUpdate` | ✅ (ETH) | → treasury |
| **Per-GI service fee** | Model owner | Precondition of `startGI` | ❌ — this **is** the reward-pool deposit (§5); fee and pool are one flow | → validator pool (95%) + treasury network fee (5%) |
| **Storage cost line item** | Model owner | Per-GI, alongside service fee | ❌ | Design the routing slot now, keep at 0 until Filecoin migration (RES-1) |
| **Dispute bond** | Disputing validator | Dispute open | ❌ | Returned + bounty if upheld; → treasury if frivolous |

### Routing contract (P3-5.3)

Single fee-router with DAO-settable split fractions: `modelOwner → {validatorPool, treasury, burn, storage}` with fractions summing to 100%. All splits are basis-point parameters behind governance hooks (P3-5.1); nothing hard-coded except sane bounds (e.g., treasury cut ≤ 20%).

### Denomination decision

Registration fees are ETH today; staking/rewards are DIN. **Recommend converging on DIN for all protocol fees in 2.0** (single-asset accounting, reinforces token utility; the `depositAndMint` on-ramp makes acquisition trivial on devnet). Migration: add DIN-denominated fee params alongside, deprecate ETH fees after one release. If ETH fees are kept, the router must handle both assets — added complexity for no devnet benefit.

### Dynamic fees

Admin/DAO-settable base rate + per-role multipliers (P3-5.3). No algorithmic (demand-based) fee logic in 2.0 — parameterize now, automate later.

---

## 9. Consolidated open-decision list

Decisions that must be made (with owner + roadmap slot) before DevNet 2.0 contracts freeze:

1. **Slashed-stake destination** — burn/treasury/split (rec: 50/50). Owner: Umer, P3-4.2.
2. **Partial-slash fraction & S3 deviation threshold** — needs P3-SCR empirical data; shadow-mode first. Owner: Umer, P3-4.1 + P3-SCR.
3. **Reward split percentages across roles** — simulate in P3-5.2. Owner: Umer.
4. **Fee denomination** — DIN-only vs dual-asset (rec: DIN-only). Owner: Umer, P3-5.3.
5. **Emission schedule shape + MAX_SUPPLY** — P3-5.2 simulation. Owner: Umer (design), Robbert (contract).
6. **Per-model stake requirement bounds** — P3-5.1. Owner: Umer.
7. **Dispute bond size & window length** — P3-4.3. Owner: Umer (design), Robbert (contract).
8. **`depositAndMint` cap/retirement plan for testnet** — flag before audit. Owner: Umer.

---

## 10. Cross-references

- [`p3-design-plan.md`](p3-design-plan.md) — coordination page for the P3 design push: mechanism → GitHub issue map, discussion links for the §9 open decisions.
- [`whitepaper-summary.md`](whitepaper-summary.md) — white paper summary + gap/alignment checklist; §8 items feed the designs above.
- `Developer/ROADMAP.md` — WP scheduling (P3-4.x, P3-5.x, P3-SCR, P3-6.x, P3-DOC2/3/5).
- `Documentation/public/workflows/din-workflow.md`, `Documentation/public/workflows/model-workflow.md` — current GI lifecycle these mechanisms attach to.
- `foundry/src/DinValidatorStake.sol`, `DINTaskCoordinator.sol`, `DINTaskAuditor.sol`, `DINModelRegistry.sol`, `DinCoordinator.sol`, `DinToken.sol` — current implementations referenced in §2.
- Roadmap Discussion §2 (BlockFLow over Shapley), §3 (Filebase→Filecoin fee hook), §5 (threat model scope).
- PR #13 upgradeable proxy layer — all new mechanism contracts should follow its Transparent Proxy + `_disableInitializers()` + `__gap` conventions from day one.
