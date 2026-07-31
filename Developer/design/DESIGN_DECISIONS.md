# Design Decisions Log

**Status:** Living document — tracks cross-cutting design decisions that don't have a single natural home in an existing `design/`/`issues/` doc, starting with DIN-DAO (issue #23, PR #27 `feat/din-dao`).
**Owner:** Umer

## Why this document exists

Some design questions surface mid-review (PR comments, contributor follow-ups) rather than at design-doc-writing time, and don't belong to one mechanism doc alone. This log tracks them from first surfacing through to a merged decision, so the rationale isn't only reconstructable from PR comment archaeology. Each row is a single decision; full option write-ups live in their own section below the table.

**Status vocabulary:** `new` (just logged, no discussion yet) → `pending` (options laid out, awaiting a call) → `resolved` (decision made, not yet in code) → `implemented` (code written on a branch) → `merged` (landed on `develop`).

**Raised By** is whoever first surfaced the question (a PR reviewer, a contributor, etc.) — not necessarily who logs or resolves it. **Resolved By** holds the *creator* of the log entry while status is `new`/`pending`, then switches to whoever actually made the call once status moves to `resolved` or later.

## Decision log

| No | Name | Raised By | Description | Options | Status | Phase | Branch | Chosen | Resolved By | Why | Links | Date |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DD-1 | Validator governance voting power | robertocarlous | Validators already lock DIN in `DinValidatorStake`. Stage C (`DinGovernanceStaking`/stDIN) requires a *separate* DIN lock to get governance voting power — should that be a second lock, or should voting power derive from existing validator stake? | A. Double-lock (current) · B. Stake-bridge · C. Hybrid | pending | P4 (din-dao, Stage C) | `feat/din-dao` | — | umeradl | — | [PR #27](https://github.com/InfiniteZeroFoundation/DevNet/pull/27), [issue #23](https://github.com/InfiniteZeroFoundation/DevNet/issues/23) | 2026-07-31 |
| DD-2 | DAO voting power model | umeradl | White paper §8 calls for "non-coin-based voting credits" (anti-plutocracy/DPPs); `decentralized-governance.md` recommends token-weighted (locked/staked DIN) and explicitly rejects raw quadratic voting; PR #27 Stage C implements plain coin-weighted voting (stDIN, 1:1). The three don't currently agree. | A. Coin-weighted (current) · B. Quadratic · C. Non-coin-based credits | pending | P4 (din-dao, Stage C) | `feat/din-dao` | — | umeradl | — | [PR #27](https://github.com/InfiniteZeroFoundation/DevNet/pull/27), [issue #23](https://github.com/InfiniteZeroFoundation/DevNet/issues/23), [decentralized-governance.md](../issues/decentralized-governance.md), [whitepaper-summary.md §8](whitepaper-summary.md) | 2026-07-31 |

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
- **Cons:** couples governance power to a balance that can shrink via slashing mid-proposal (checkpoint/snapshot semantics get more complex); blurs the "no free-balance voting" boundary the design already drew for the general case since validator stake wasn't designed with vote-checkpointing in mind; more contract surface to audit before Stage C activation.

### Option C — Hybrid

Allow both paths to contribute to voting power: a validator can rely on stake-bridged votes *and/or* lock stDIN like any other participant; a non-validator token holder can still only use the stDIN path.

- **Pros:** flexible; doesn't force validators to choose.
- **Cons:** most complex option to specify and audit — two independent power sources feeding one quorum invites double-counting or gaming edge cases (e.g., unstake-then-relock timing around snapshots) that need explicit design before any code is written.

### Status

Open. Not addressed in `Developer/design/whitepaper-summary.md` or Abraham's Slack answers (`discuss-44-45-46.md`, `araham_slack_reply.md`) — those cover slashing economics, tokenomics, and white-paper scope calls, not this. This is a new decision, and moot in the very near term since Stage C is trailing PR #27 into its own follow-up (nothing activates before devnet 3.0 / testnet 1.0 regardless).

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

Open. `decentralized-governance.md`'s existing recommendation (Option A) and the white paper/Abraham ask (leaning toward C, with B explicitly weighed and rejected in the same doc) are not currently reconciled anywhere in writing. Minimum near-term action per Abraham's instruction: document *why* Stage C chose coin-weighted over non-coin-based (Sybil resistance, no DID system yet) rather than leaving the conflict implicit — this doesn't require resolving the full question now, since Stage C is trailing PR #27 into a follow-up and nothing activates before testnet 1.0.
