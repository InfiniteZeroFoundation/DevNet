# DIN DAO — Architecture & Staged Rollout

> **Spec status:** Initial design. Decisions recorded here supersede open questions in
> `Developer/issues/decentralized-governance.md`.
> **Branch:** `feat/din-dao`
> **Roadmap ref:** P3-5.1 · ROADMAP Discussion §1

---

## 1. Purpose

The DIN platform is currently governed by a single DIN-Representative admin key that
holds `owner()` on `DinCoordinator`, `DinValidatorStake`, and `DINModelRegistry`, and
will hold ownership of the `ProxyAdmin` created in PR #13. This document specifies how
that authority is progressively transferred to a DAO-governed contract stack.

DIN does **not** need live DAO governance today. The activation schedule is:

| Network milestone   | DAO stage active    |
|---------------------|---------------------|
| Devnet 1.0          | None (admin key)    |
| Devnet 2.0          | Stage A shadow-only |
| Devnet 3.0          | Stage B live        |
| Testnet 1.0         | Stage C live        |
| Testnet 2.0 / audit | Stage D live        |

Contracts ship behind `feat/din-dao` now so the architecture can be reviewed and
hardened before any network milestone requires them.

---

## 2. Stage Overview

```
Stage A  ──────────────────────────────────────────────────────────────
  DinMultisig
  N-of-M typed-proposal multisig. Replaces single admin key.
  Shadow-operates in devnet 2.0 (no on-chain authority yet).

Stage B  ──────────────────────────────────────────────────────────────
  DinTimelockShort  (24 h delay)   ← parameter + operational proposals
  DinTimelockLong   (48 h delay)   ← treasury + upgrade proposals
  DinMultisig → PROPOSER_ROLE + CANCELLER_ROLE on both timelocks.
  Timelocks receive owner() of platform contracts + ProxyAdmin.
  Live at devnet 3.0.

Stage C  ──────────────────────────────────────────────────────────────
  DinGovernanceStaking  (stDIN)   ← lock DIN → non-transferable votes
  DinGovernor                     ← OZ Governor executing through timelocks
  Token-vote governance replaces multisig as primary proposer.
  DinMultisig retains CANCELLER_ROLE as safety brake.
  Live at testnet 1.0.

Stage D  ──────────────────────────────────────────────────────────────
  DinGuardian   ← narrow, time-limited emergency authority
  Guardian role held by DinMultisig; revocable by DinGovernor.
  Live alongside Stage C at testnet 1.0 → 2.0.
```

---

## 3. Contract Architecture

### 3.1 Deployed contracts (foundry/src/dao/)

| Contract               | Stage | Description                                               |
|------------------------|-------|-----------------------------------------------------------|
| `DinMultisig.sol`      | A     | N-of-M multisig with per-category typed proposals         |
| `DinTimelock.sol`      | B     | Thin OZ `TimelockController` wrapper; deployed twice      |
| `DinGovernanceStaking` | C     | Lock DIN → stDIN voting power (non-transferable, IVotes)  |
| `DinGovernor.sol`      | C     | OZ Governor executing through DinTimelockLong/Short       |
| `DinGuardian.sol`      | D     | Narrow emergency authority with ratification window       |

### 3.2 Governance flow at each stage

**Stage A / B** (multisig-led)
```
Signer → DinMultisig.propose()
       → confirm × threshold
       → DinMultisig.execute()
           → DinTimelockShort.schedule() or DinTimelockLong.schedule()
           → (delay elapses)
           → DinTimelock.execute()
               → platform contract call
```

**Stage C / D** (token-vote-led, multisig as safety brake)
```
Proposer → DinGovernor.propose()
         → voting delay
         → token holders vote
         → DinGovernor.queue()  → DinTimelockShort or DinTimelockLong
         → (delay elapses)
         → DinGovernor.execute()
             → platform contract call

Emergency path (Stage D only):
DinMultisig → DinGuardian.performAction()
            → (ratification window: 7 days)
            → DinGovernor ratifies or action is reversed
```

### 3.3 Role wiring

```
                    ┌──────────────────────────┐
                    │       DinMultisig         │
                    │  (3-of-5 for v1)          │
                    └────────┬─────────┬────────┘
                             │         │
               PROPOSER_ROLE │         │ CANCELLER_ROLE (retained at Stage C+)
                             ▼         ▼
              ┌──────────────────────────────────┐
              │  DinTimelockShort  DinTimelockLong│
              │  (24 h delay)      (48 h delay)   │
              └──────────┬───────────────┬────────┘
                         │               │
              owner() ───┴───────────────┘
                         │
         ┌───────────────┼──────────────────┐
         ▼               ▼                  ▼
  DinCoordinator  DinValidatorStake  DINModelRegistry  ProxyAdmin
```

At Stage C, `DinGovernor` is added as `PROPOSER_ROLE` on both timelocks alongside
`DinMultisig`. The multisig retains `CANCELLER_ROLE` to veto a proposal before its
delay elapses.

---

## 4. Proposal Categories & Thresholds

### 4.1 DinMultisig (Stage A / B)

| Category      | Examples                                           | Confirmations required |
|---------------|----------------------------------------------------|------------------------|
| `Parameter`   | fee updates, dinPerEth, stake thresholds           | 2-of-N                 |
| `Operational` | slasher auth, model disable/enable, blacklisting   | 2-of-N                 |
| `Treasury`    | ETH/fee withdrawal, grant disbursement             | 3-of-N                 |
| `Upgrade`     | platform contract upgrade, ProxyAdmin transfer     | N-of-N (unanimous)     |

N = number of signers at deployment (v1: 3 signers).

### 4.2 DinGovernor (Stage C)

| Category      | Quorum | Threshold        | Timelock       |
|---------------|--------|------------------|----------------|
| `Parameter`   | 4 %    | Simple majority  | Short (24 h)   |
| `Operational` | 10 %   | Simple majority  | Short (24 h)   |
| `Treasury`    | 15 %   | Supermajority ≥66%| Long (48 h)   |
| `Upgrade`     | 20 %   | Supermajority ≥66%| Long (48 h)   |

DinGovernor is single-track (one Governor instance). Routing to the correct timelock
is handled by the proposer encoding the timelock address as the execution target of the
queued operation. This avoids two Governor instances while preserving the two-delay
model.

All governance parameters (`votingDelay`, `votingPeriod`, `proposalThreshold`,
`quorumNumerator`) are `GovernorSettings`-settable by governance itself after
deployment.

---

## 5. Voting Power Model

**Decision: locked DIN (stDIN).**

`DinGovernanceStaking` locks DIN and mints a non-transferable ERC-20 (stDIN) that
implements OZ `IVotes` via `ERC20Votes`. Voting power is checkpointed at the block the
proposal becomes active.

### Rationale

- Free-balance DIN voting is rejected because DIN is a freely transferable ERC-20;
  snapshot-at-proposal without a locking commitment invites flash-loan and last-minute
  purchase attacks.
- Validator stake in `DinValidatorStake` is **not** counted toward governance power in
  v1. Hybrid stake-voting would create a conflict of interest when governance votes on
  slashing conditions or blacklisting appeals. Validators can participate by separately
  locking DIN in `DinGovernanceStaking`.
- Quadratic voting is explicitly excluded. Non-binding signaling off-chain only, if
  ever introduced.

### Delegation

Full OZ `ERC20Votes` delegation is supported. An address must call `delegate(self)` to
activate its own voting power; undelegated stDIN does not count toward quorum. This
matches the OZ Governor standard expectation.

### Ossification path

Because `DinGovernanceStaking` mints the stDIN that governs DinGovernor, governance can
vote to lock the upgrade path permanently by:
1. Removing `UPGRADER_ROLE` from all addresses on the ProxyAdmin (if UUPS) or
   renouncing ProxyAdmin ownership.
2. Removing the `PROPOSER_ROLE` from itself on the timelocks.

This is a one-proposal endgame — no migration required.

---

## 6. Own Multisig vs. Gnosis Safe

### 6.1 Build our own (chosen for devnet)

`DinMultisig` is an in-tree, in-scope contract written to DIN's conventions (solc
0.8.28, custom errors, NatSpec, events-first). This gives:

- full auditability alongside the contracts it governs
- typed proposals with per-category thresholds not available out of the box in Safe
- no external deploy dependency for devnet self-containment

### 6.2 Gnosis Safe for mainnet treasury

For mainnet, the multisig signers should migrate to a Gnosis Safe for:
- battle-tested security and audits
- existing tooling (Safe UI, SDK, transaction service)
- hardware-wallet signing support

The migration path: `DinMultisig` transfers `PROPOSER_ROLE` and `CANCELLER_ROLE` on
both timelocks to a Safe address via a normal `Upgrade`-category proposal. No platform
contracts change.

### 6.3 Recommendation

Run `DinMultisig` for devnet 2.0 through testnet 1.0. Begin Safe migration planning
during testnet 2.0 alongside Stage D activation and the audit preparation window.

---

## 7. Timelock Delay Rationale

Two delay tiers rather than per-operation salt conventions because:
- the timelock delay is set globally on `TimelockController` and cannot be overridden
  per-operation without a custom extension
- two independent `DinTimelock` instances each with a fixed delay is simpler to reason
  about, deploy, and audit than a single instance with conditional delay logic

Short delay (24 h): bounded parameter changes whose blast radius is limited. A wrong
fee can be corrected in the next proposal.

Long delay (48 h): treasury withdrawals and upgrade proposals. On Optimism Sepolia the
execution gas is nearly free; 48 h gives DIN participants (validators, clients,
aggregators) adequate time to observe a pending upgrade and exit if they disagree. A
compromised multisig cannot swap in malicious logic silently — there is a 48 h window
to observe and cancel.

---

## 8. CLI Command Mapping (dincli dindao)

Current `dincli dindao ...` commands map to DAO flows as follows. CLI implementation
is out of scope for this issue but must be documented here so DIN-SDK (#20) and
DIN-daemon (#21) can plan for it.

| Current dincli command                     | DAO equivalent (Stage B+)               |
|--------------------------------------------|-----------------------------------------|
| `dindao approve-model-request`             | `propose` + `confirm` + `execute` via multisig → timelock |
| `dindao reject-model-request`              | Same                                    |
| `dindao approve-manifest-update`           | Same                                    |
| `dindao add-slasher-contract`              | `Operational` proposal through multisig |
| `dindao remove-slasher-contract`           | Same                                    |
| `dindao withdraw-eth`                      | `Treasury` proposal through multisig    |
| `dindao update-din-per-eth`                | `Parameter` proposal through multisig   |
| `dindao blacklist-validator`               | `Operational` or guardian emergency     |
| `dindao unblacklist-validator`             | Full governance proposal only (Stage C) |
| Contract upgrade (no current CLI command)  | `Upgrade` proposal; unanimous multisig  |

---

## 9. Integration Points

### 9.1 PR #13 (upgradeable contracts)

The `ProxyAdmin` created in PR #13 is the handle for upgrade governance. Its ownership
transfers to `DinTimelockLong` at Stage B. No changes to the four platform contracts are
required for Stages A or B; Stage D requires platform contracts to expose an
`onlyGuardian` path for emergency protective actions (tracked separately).

### 9.2 P3-5.x (token utility, emission, fees)

`DinCoordinator.updateDinPerEth`, `DINModelRegistry` fee setters, and future emission
rate setters (P3-5.2) are `onlyOwner` parameter setters. They are the primary `Parameter`
and `Treasury` category targets for DAO proposals. No signature changes are required if
they follow the plain-setter convention; any setter that bundles side effects beyond the
parameter update should be flagged before Stage B activation.

### 9.3 Slashing / dispute resolution (P3-4.x)

The blacklisting and confiscation-of-blacklisted-stake path (described in
`Developer/issues/staking-mechanism.md`) must execute via accepted governance proposal
in the long run. `DinGuardian` covers the emergency-blacklist case at Stage D; the
confiscation path goes through `DinGovernor` as a `Treasury` category proposal.

### 9.4 Indexer (P4-IDX)

All DAO contracts emit events on every state transition. No on-chain enumeration helpers
are added — proposal lists, voter histories, quorum checks, and guardian action
dashboards are indexer responsibilities. Refer to `Developer/issues/indexer.md`.

---

## 10. Open Design Questions — Resolved

Answers to the open questions from `Developer/issues/decentralized-governance.md`:

| Question | Decision |
|----------|----------|
| Model approval / manifest approval — direct DAO vote or elected committee? | Direct multisig proposal (Stage B). Move to Governor (Stage C) with `Operational` threshold. No elected committee in v1. |
| Validator blacklisting and unblacklisting — same threshold? | Different. Blacklisting is `Operational` (lower threshold; also available as guardian emergency action). Unblacklisting is `Operational` via full governance only — no emergency path. Restorative actions always go through normal governance. |
| Treasury and upgrade proposals — supermajority? | Yes. ≥66 % of participating votes, higher quorum (15–20 %). See §4.2. |
| Voting power: staked DIN, locked DIN, or hybrid? | Locked DIN (stDIN). Validator stake not counted in v1. See §5. |
| Quadratic voting anywhere? | No. Non-binding signaling off-chain only, if ever introduced. |
| One chamber or separated by role? | One chamber for v1. Bicameral governance (validators vs. token holders) is a Phase 4 consideration per `decentralized-governance.md`. |

---

## 11. Non-Goals (this issue)

- Quadratic voting (on-chain or off-chain)
- Task-level governance — task contracts remain model-owner-driven
- On-chain proposal enumeration helpers (indexer responsibility)
- Mainnet treasury custody decisions (Safe migration documented but not committed)
- Cross-layer governance (L1 ↔ L2 bridge-routed upgrades) — out of scope for v1

---

## 12. Ownership-Transfer Runbook

See `Documentation/dindao.md §5` (to be updated). The exact ordered steps to transfer
`owner()` of each platform contract to the appropriate timelock, with rollback notes,
will be added there once Stage B contracts are finalized and reviewed.
