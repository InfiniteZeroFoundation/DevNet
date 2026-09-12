# Design Decisions Log

**Status:** Living document — tracks cross-cutting design decisions that don't have a single natural home in an existing `design/`/`issues/` doc, starting with DIN-DAO (issue #23, PR #27 `feat/din-dao`).
**Owner:** Umer

## Why this document exists

Some design questions surface mid-review (PR comments, contributor follow-ups) rather than at design-doc-writing time, and don't belong to one mechanism doc alone. This log tracks them from first surfacing through to a merged decision, so the rationale isn't only reconstructable from PR comment archaeology. Each row is a single decision; full option write-ups live in their own section below the table.

**Status vocabulary:** `new` (just logged, no discussion yet) → `pending` (options laid out, awaiting a call) → `deferred` (question doesn't need resolving yet — the feature it belongs to is out of scope until a later phase) → `resolved` (decision made, not yet in code) → `implemented` (code written on a branch) → `merged` (landed on `develop`).

**Raised By** is whoever first surfaced the question (a PR reviewer, a contributor, etc.) — not necessarily who logs or resolves it. **Resolved By** holds the *creator* of the log entry while status is `new`/`pending`, then switches to whoever actually made the call once status moves to `resolved` or later.

## Decision log

| No | Name | Raised By | Description | Options | Status | Phase | Branch | Chosen | Resolved By | Why | Links | Date |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DD-1 | Validator governance voting power | robertocarlous | Validators already lock DIN in `DinValidatorStake`. Stage C (`DinGovernanceStaking`/stDIN) requires a *separate* DIN lock to get governance voting power — should that be a second lock, or should voting power derive from existing validator stake? | A. Double-lock (current) · B. Stake-bridge · C. Hybrid | deferred | Post-mainnet (din-dao, Stage C) | `feat/din-dao` | A (leaning, open for input) | umeradl | Branch's own architecture doc (§5) already documents a conflict-of-interest rationale against B/C: validators voting with slashable-stake-derived power on `Operational`-category proposals (slasher auth, blacklisting) would be voting on rules that could slash them. A avoids this; B/C would need a category-scoped carve-out or per-proposal recusal mitigation, both non-trivial on stock OZ `Governor`. Opened for team input on A vs. B/C-with-mitigation; moot for now — see DD-3's resolution, all of din-dao (Stages A–D) moved out of active P4 scope to post-mainnet. | [PR #27](https://github.com/InfiniteZeroFoundation/DevNet/pull/27), [issue #23](https://github.com/InfiniteZeroFoundation/DevNet/issues/23), [discussion #69](https://github.com/InfiniteZeroFoundation/DevNet/discussions/69) | 2026-07-31 |
| DD-2 | DAO voting power model | umeradl | White paper §8 calls for "non-coin-based voting credits" (anti-plutocracy/DPPs); `decentralized-governance.md` recommends token-weighted (locked/staked DIN) and explicitly rejects raw quadratic voting; PR #27 Stage C implements plain coin-weighted voting (stDIN, 1:1). The three don't currently agree. | A. Coin-weighted (current) · B. Quadratic · C. Non-coin-based credits | deferred | Post-mainnet (din-dao, Stage C) | `feat/din-dao` | — | umeradl | — | [PR #27](https://github.com/InfiniteZeroFoundation/DevNet/pull/27), [issue #23](https://github.com/InfiniteZeroFoundation/DevNet/issues/23), [decentralized-governance.md](../issues/decentralized-governance.md), [whitepaper-summary.md §8](whitepaper-summary.md) | 2026-07-31 |
| DD-3 | Initial `DinMultisig` signer composition (Stage A) | robertocarlous | Architecture doc says "3-of-5 for v1" but names no signers. `DinMultisig`'s signer list + per-category thresholds are immutable after construction (changing signers means deploying a new multisig and migrating timelock roles) — if all five keys are held by the same team, Stage A provides no real governance legitimacy despite being "live." Who are the initial signers, and what's the selection process? | A. All-internal (team-held) · B. Mixed internal + external · C. Fully external/community-selected · D. No Stage A multisig — off-chain governance | resolved | Post-mainnet (din-dao, Stage A) | `feat/din-dao` | D | abrahamnash | Following Ethereum's off-chain governance model: no `DinMultisig` controlling protocol roles (`PROPOSER_ROLE`/`CANCELLER_ROLE`) during Stage A/Devnet 2.0; a multisig (simple Gnosis Safe) is scoped to treasury/fund management only, never governance or upgrade authority; on-chain governance (security councils, role-based multisigs, token voting) gets revisited post-mainnet, when actually needed. Avoids locking an immutable signer set before there's real demand or a legitimate selection process (per Robert's own point on discussion #70). | [PR #27](https://github.com/InfiniteZeroFoundation/DevNet/pull/27), [issue #23](https://github.com/InfiniteZeroFoundation/DevNet/issues/23), [discussion #70](https://github.com/InfiniteZeroFoundation/DevNet/discussions/70) | 2026-08-04 |

---

## DD-1 — Validator governance voting power: double-locking vs. stake-bridge

### Problem

`DinValidatorStake` already holds a validator's slashable DIN stake. Stage C's `DinGovernanceStaking` (stDIN) is a separate contract: lock DIN → mint non-transferable, checkpointed voting power (OZ `ERC20Votes`). As shipped in PR #27, these two locks are entirely independent — a validator who wants governance voting power must lock a *second*, distinct pool of DIN into `DinGovernanceStaking`, on top of what's already locked (and slashable) in `DinValidatorStake`.

Flagged by Robert on PR #27: either validators need 2× their DIN (one set staked for validation, one set locked for governance), or they get zero governance power despite being the most economically committed participants on the network.

### Option A — Double-locking (current PR #27 behavior)

Keep the two contracts fully independent. Validators who want a governance voice lock additional DIN into `DinGovernanceStaking`, same as any other token holder.

- **Pros:** simplest to build and audit — `DinGovernanceStaking` has zero coupling to `DinValidatorStake`; no risk of governance and slashing logic interfering with each other; matches the commit-message framing already in PR #27 ("validator stake excluded from governance in v1").
- **Cons:** capital-inefficient for validators specifically; likely under-weights the most committed participants in governance relative to passive DIN holders who lock once.

### Option B — Stake-bridge

Derive governance voting power directly from a validator's `DinValidatorStake` balance — e.g., a read-only adapter that reports validator stake as `IVotes`-compatible voting power, with no second lock.

- **Pros:** no double-locking; governance power tracks actual protocol commitment (slashable stake) rather than a parallel, unslashable pool.
- **Cons:** couples governance power to a balance that can shrink via slashing mid-proposal (checkpoint/snapshot semantics get more complex); blurs the "no free-balance voting" boundary the design already drew for the general case since validator stake wasn't designed with vote-checkpointing in mind; more contract surface to audit before Stage C activation; **conflict of interest** — see below.

### Option C — Hybrid

Allow both paths to contribute to voting power: a validator can rely on stake-bridged votes *and/or* lock stDIN like any other participant; a non-validator token holder can still only use the stDIN path.

- **Pros:** flexible; doesn't force validators to choose.
- **Cons:** most complex option to specify and audit — two independent power sources feeding one quorum invites double-counting or gaming edge cases (e.g., unstake-then-relock timing around snapshots) that need explicit design before any code is written; inherits B's conflict of interest on its bridged-vote component.

### Conflict-of-interest argument for Option A

`Documentation/technical/din-dao/README.md` §5 (Voting Power Model), already on the `feat/din-dao` branch, records this rationale from when Stage C was designed:

> Validator stake in `DinValidatorStake` is not counted toward governance power in v1. Hybrid stake-voting would create a conflict of interest when governance votes on slashing conditions or blacklisting appeals.

`DinGovernor`'s `Operational` proposal category (§4.1) covers exactly this — slasher authorization, blacklisting, model disable/enable. A validator voting with stake-derived power on those proposals is voting on rules that could slash them. B and C both inherit this wherever bridged stake can vote on `Operational` proposals.

**Possible mitigations if bridging is still wanted:**
1. **Category-scoped carve-out** — bridged voting power counts for `Parameter`/`Treasury`/`Upgrade` only, zero weight on `Operational`. Requires a custom voting/weight module; stock OZ `Governor`/`GovernorVotes` doesn't support per-category voter weight.
2. **Per-proposal recusal** — a validator who is the explicit subject of a pending slashing/blacklist proposal has their bridged votes excluded from that proposal only. Finer-grained, more engineering (Governor needs to cross-reference proposal calldata against voter identity).

Both add real scope on top of B/C's already-larger audit surface.

### Status

**Deferred, 2026-08-04.** Abraham's decision on DD-3 (below) moves all of din-dao — Stages A through D, including Stage C — out of active P4 scope and post-mainnet: DevNet governs off-chain (team coordination + public discussion, Ethereum-ACD-style) through mainnet, with on-chain governance layers revisited only once actually needed. Robert confirmed on [discussion #70](https://github.com/InfiniteZeroFoundation/DevNet/discussions/70) (comment, 2026-08-04) that this matches the team-call decision to move DIN-DAO to post-mainnet. This question (double-lock vs. stake-bridge) is therefore not resolved on its merits — it's shelved along with the rest of Stage C, to be picked back up when governance work resumes. Umer's leaning going into the deferral was still **Option A**, given the conflict-of-interest argument above; that stands as the starting point whenever this is revisited. Not addressed in `Developer/design/whitepaper-summary.md` or Abraham's earlier Slack answers (`discuss-44-45-46.md`, `araham_slack_reply.md`).

---

## DD-2 — DAO voting power model: coin-weighted vs. quadratic vs. non-coin-based

### Problem

Three sources disagree on the shape of DIN governance voting power:

- **White paper §8** (`whitepaper-summary.md` item 9): "non-coin-based voting credits for most decisions (anti-plutocracy)."
- **`Developer/issues/decentralized-governance.md`**: recommends token-weighted voting power from staked or locked DIN at a snapshot, and explicitly argues *against* raw quadratic voting (transferable-token Sybil-splitting risk).
- **PR #27 Stage C** (as built): plain coin-weighted voting — lock DIN 1:1 into non-transferable, checkpointed stDIN (`ERC20Votes`). No quadratic dampening, no non-coin credit system.
- **Abraham** (`araham_slack_reply.md` line 81, discussion #46 item 5): "Non-coin-based voting credits (DPPs, §8): Note early in din-dao design. P3 ships `onlyOwner`. Full DAO later. But the stance should be documented early." — a scope/timing instruction to flag the principle, not a specific mechanism choice.

### Option A — Coin-weighted (current PR #27 behavior)

Locked/staked DIN → linear voting power via checkpointed `ERC20Votes`. This is what `decentralized-governance.md` recommends and what Stage C already implements.

- **Pros:** simple, auditable, well-trodden OZ pattern; avoids quadratic voting's Sybil-splitting problem entirely since power is linear (no advantage to splitting balance across wallets); matches production governance patterns DIN can point to (Compound/Uniswap-style).
- **Cons:** does not address plutocracy — largest DIN holders still dominate proportionally; explicitly in tension with the white paper's anti-plutocracy framing and Abraham's ask to "document the [non-coin-based] stance early."

### Option B — Quadratic voting

Voting power scales as `sqrt(locked DIN)` rather than linearly.

- **Pros:** dampens whale dominance somewhat versus linear weighting; still coin-based so no new Sybil-resistance infrastructure needed beyond what locking already provides.
- **Cons:** already evaluated and rejected in `decentralized-governance.md` for DIN specifically — locked balances can still be split across many wallets pre-lock to farm the sqrt bonus, and the doc's recommendation is to defer any quadratic behavior to non-binding signaling only, after DIN has identity/anti-Sybil assumptions in place. Doesn't actually satisfy the white paper's "non-coin-based" ask either — it's still a function of token amount.

### Option C — Non-coin-based voting credits

Voting power decoupled from DIN holdings entirely — e.g., one-identity-one-vote, role/participation-based credits, or reputation earned through network activity (validating, auditing, contributing).

- **Pros:** the only option that actually satisfies the white paper's DPP framing and Abraham's anti-plutocracy ask as literally stated.
- **Cons:** requires its own Sybil-resistance mechanism (identity/verifiable credentials — white paper gap item #13, not yet built for DIN); no existing design for how credits would be earned, capped, or revoked; substantially more scope than anything currently drafted in PR #27 or `decentralized-governance.md`.

### Status

**Deferred, 2026-08-04** — same basis as [DD-1](#dd-1--validator-governance-voting-power-double-locking-vs-stake-bridge) and [DD-3](#dd-3--initial-dinmultisig-signer-composition-stage-a): Abraham's decision moves all of din-dao, Stage C included, out of active P4 scope to post-mainnet. `decentralized-governance.md`'s existing recommendation (Option A) and the white paper/Abraham ask (leaning toward C, with B explicitly weighed and rejected in the same doc) remain unreconciled in writing, but resolving that is no longer near-term work — it waits until Stage C is actually picked back up. The one action that still stands whenever that happens: document *why* Stage C chose coin-weighted over non-coin-based (Sybil resistance, no DID system yet) rather than leaving the conflict implicit.

---

## DD-3 — Initial `DinMultisig` signer composition (Stage A)

### Problem

`Documentation/technical/din-dao/README.md` §4.1 sets `DinMultisig` at "3-of-5 for v1" but never names the five signers or how they're chosen. Per `foundry/src/dao/DinMultisig.sol`'s own NatSpec, the signer list and per-category thresholds are **immutable after construction** — changing signers later means deploying an entirely new `DinMultisig` and migrating `PROPOSER_ROLE`/`CANCELLER_ROLE` on both timelocks via an Upgrade-category proposal through the existing instance. That makes the initial choice unusually costly to get wrong.

Flagged by Robert on PR #27: if all five keys are held by the same team, Stage A is technically "live" (per the activation schedule, shadow-only at Devnet 2.0) but provides no real governance legitimacy — it's the existing admin key in a 3-of-5 costume. Before the PR is marked ready, who are the initial signers, or what's the process for selecting them?

### Option A — All-internal (team-held)

All five keys held by DIN core team / DIN-Representative-adjacent individuals.

- **Pros:** fastest to bootstrap; no external coordination or vetting needed; matches where the project actually is pre-Devnet-3.0 (Stage A is shadow-only, no on-chain authority yet).
- **Cons:** exactly the centralization Robert flagged — no real legitimacy gain over the current single admin key, just more keys held by the same trust set.

### Option B — Mixed internal + external

Some seats held by the core team, remainder by external contributors/community members (e.g., active contributors or trusted community figures).

- **Pros:** meaningfully reduces single-party control while still being achievable before Devnet 3.0; external signers have visible skin in the project already.
- **Cons:** needs a real vetting/trust process for who qualifies; key management overhead for people outside the core team; still has to answer "who picks the external half," which just pushes the legitimacy question down one level.

### Option C — Fully external / community-selected

All five signers selected via some open nomination + selection process, none held by the core team by default.

- **Pros:** most legitimate reading of "decentralized" for Stage A.
- **Cons:** chicken-and-egg — there's no DAO or voting mechanism yet to run a legitimate selection (that's what Stages B–D are for); realistically too slow/heavy for where the project is now; risk of selecting signers with no actual stake in DIN's success.

### Option D — No Stage A multisig; off-chain governance (chosen)

Don't deploy `DinMultisig` for protocol-role governance at all during Stage A/Devnet 2.0. Follow Ethereum's model instead: governance runs off-chain (team coordination, public discussion, forums — Ethereum's All Core Devs-call equivalent), with no multisig sitting between the community and protocol upgrades. If a multisig is needed at all in the near term, it's a plain Gnosis Safe scoped to treasury/fund management only — never `PROPOSER_ROLE`/`CANCELLER_ROLE` or other protocol authority. On-chain governance structures (security councils, role-based multisigs, token voting) get progressively revisited post-mainnet, once the project is past testing and there's real demand for them.

- **Pros:** sidesteps the immutable-signer-set problem entirely — nothing to get wrong on first deploy, no redeploy/migration cost later; doesn't pretend Stage A is decentralized when, per Robert's own point, an all-internal 3-of-5 wouldn't be; matches a proven reference model (Ethereum) rather than inventing DIN-specific governance theater before there's a live mainnet to govern.
- **Cons:** DIN-DAO (`feat/din-dao`, PR #27, issue #23) — Stages A through D, not just Stage A's multisig — moves out of active P4 scope; DD-1/DD-2 (Stage C, voting power design) go with it and stay unresolved until governance work resumes post-mainnet; loses whatever "technically live (shadow-only)" governance-legitimacy signal Stage A was meant to send at Devnet 2.0/3.0.

### Status

**Resolved, 2026-08-04.** Abraham: no `DinMultisig` for Stage A, full stop — governance stays off-chain (team-coordinated, transparent discussion) until well past testing, and any near-term multisig is treasury-only. Robert confirmed on [discussion #70](https://github.com/InfiniteZeroFoundation/DevNet/discussions/70) (comment, 2026-08-04) that this is the same decision reached on a prior team call — DIN-DAO as a whole moves to post-mainnet, with forums as the interim off-chain venue. This resolves DD-3 by removing its premise (Option D) rather than picking among A/B/C's signer compositions; it also pulls DD-1 and DD-2 (Stage C) out of active scope along with it — see their Status sections.
