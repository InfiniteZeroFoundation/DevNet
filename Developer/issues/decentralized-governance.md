# Decentralized Governance

## Summary

This issue covers how DIN should move from an admin-owned platform to decentralized governance through one or more DAOs.

Today, important platform actions are still controlled by:

- `daoAdmin` in `DINModelRegistry`
- `owner()` on platform-level contracts such as `DinCoordinator`
- direct owner or coordinator-controlled flows around staking, slasher management, fees, and registry decisions

That is acceptable for an early devnet, but it is not the right long-term governance model for production.

The broader goal is to replace centralized control over platform-level actions with a DAO-driven proposal, voting, and execution system.

This should cover actions such as:

- fee updates
- model approval and rejection policy
- manifest update approval policy
- slasher authorization
- validator blacklisting and unblacklisting
- treasury withdrawals
- exchange-rate or token-policy changes if those remain governable
- future platform-contract upgrades

## Why This Matters

DIN is not just a set of task contracts. It is a protocol with shared rules, shared incentives, shared security assumptions, and shared state.

If those rules are controlled by a single admin key or a small operator set forever, then:

- governance becomes centralized even if execution is decentralized
- participants must trust operators to act fairly
- economic policy can be changed unilaterally
- blacklist and slashing authority can be abused
- upgrade authority becomes a centralization and security risk

A DAO does not remove all governance risk, but it can make authority:

- transparent
- rule-bound
- auditable
- contestable

## Current State

The current platform contracts already expose governance-sensitive actions.

Examples include:

### `DinCoordinator.sol`

- withdraw ETH treasury balance
- add slasher contracts
- remove slasher contracts
- update validator stake contract reference
- update DIN-per-ETH rate

### `DinValidatorStake.sol`

- blacklist and unblacklist validators through direct owner authority
- control slasher authorization indirectly via the coordinator

Important note:

- there is currently a blacklist path
- there is now a matching unblacklist path in the contract
- both are currently centralized under the stake contract owner and should later move under DAO governance by ownership transfer or equivalent governance control

If DIN wants governance around validator rehabilitation or appeal, that should be added deliberately rather than assumed.

### `DINModelRegistry.sol`

- approve model registration requests
- reject model registration requests
- approve manifest update requests
- reject manifest update requests
- disable models
- enable models
- set registration and manifest-update fees
- withdraw accumulated fees
- transfer DAO admin authority

## Governance Scope

The cleanest long-term direction is:

- platform-level governance should be DAO-controlled
- task-level operations should remain more local and task-owner-driven unless there is a strong protocol reason to centralize them

For this document, the scope is the platform layer.

At minimum, decentralized governance should eventually cover everything currently done by:

- `daoAdmin` in `DINModelRegistry`
- `owner()` of `DinCoordinator`
- any owner-like authority used for future platform contract upgrades

## Governance Domains

DIN governance should distinguish between different classes of decisions instead of putting everything through one identical process.

### 1. Parameter Governance

Examples:

- open-source registration fee
- proprietary registration fee
- manifest update fees
- DIN-per-ETH rate if retained
- future staking thresholds
- future unbonding periods

These are structured numeric or config changes.

### 2. Policy Governance

Examples:

- approve or reject a change in slashing rules
- approve new registry rules
- define who can be a slasher
- define blacklist and appeal policy
- decide whether certain platform modules are upgradeable

These are broader rule changes, not just parameter tweaks.

### 3. Operational Governance

Examples:

- approve model requests in the current registry design
- approve manifest updates in the current registry design
- disable or re-enable a model
- blacklist or unblacklist a validator
- authorize or deauthorize a slasher contract

These are case-by-case decisions about live protocol state.

### 4. Treasury Governance

Examples:

- withdraw accumulated fees
- fund grants
- fund audits
- fund protocol development
- route treasury assets

### 5. Upgrade Governance

Examples:

- approve platform contract upgrades
- migrate to new implementations
- update proxy admins or timelock executors

This is the highest-risk governance domain and should usually have the strongest safeguards.

## Should DIN Use Voting?

Yes. Platform-level governance should ultimately go through voting rather than unilateral admin action.

But not every action needs the same vote type, quorum, delay, or execution path.

The important design question is not only "should there be voting?" It is:

- who votes
- with what voting power
- for which proposal classes
- with what thresholds
- with what execution delay

## Should DIN Use Quadratic Voting?

Quadratic voting is attractive in theory because it reduces the dominance of very large holders relative to linear token voting.

But DIN should be careful here.

### Why quadratic voting is attractive

- gives smaller holders more influence per token
- may better reflect intensity of preference
- can reduce simple whale dominance

### Why raw on-chain quadratic voting is dangerous

- transferable tokens make Sybil splitting easy
- one large holder can split balances across many wallets
- flash-loan and temporary-balance attacks become harder to reason about
- implementation complexity increases
- the economics can become unclear and gameable

### Recommendation

DIN should **not** start with raw quadratic voting on freely transferable DIN balances.

A better near-term governance default is:

- binding governance based on **snapshot voting power from staked or locked DIN**
- optional delegation
- quorum and proposal thresholds
- timelocked execution

If the protocol wants quadratic behavior later, it should only be considered after DIN has:

- clear identity or anti-Sybil assumptions
- locked or non-transferable voting power
- tested governance demand for that complexity

A reasonable compromise is:

- use token-weighted voting for binding governance
- optionally use quadratic or reputation-weighted **signaling** for non-binding sentiment

## Basis Of Voting Power

The most natural basis is DIN-based governance power, but not raw wallet balances.

Recommended direction:

- voting power should come from **staked DIN**, **locked DIN**, or **vote-escrowed DIN**
- voting power should be measured at a snapshot block
- delegated voting should be supported

This is better than free-balance voting because it:

- makes governance participation more intentional
- reduces short-term manipulation
- aligns governance with long-term protocol commitment

Possible options:

### Option 1. Staked DIN

Pros:

- aligned with network participation
- easier to justify economically

Cons:

- favors validators and active operators
- may underrepresent model owners or long-term token holders who do not stake

### Option 2. Locked DIN

Pros:

- cleaner governance commitment signal
- easier to separate governance from validator economics

Cons:

- requires additional locking mechanics

### Option 3. Hybrid

Pros:

- can combine staking and governance participation
- more flexible long-term

Cons:

- more complex to reason about

### Recommendation

Start with one of these two:

- locked DIN governance power, or
- staked DIN governance power with explicit delegation

Raw transferable-balance voting is likely too weak for production.

## Who Can Make Proposals?

DIN should not allow unrestricted zero-cost proposal spam.

Proposal creation should be gated by at least one of:

- minimum voting power threshold
- proposal bond or deposit
- delegated sponsorship
- reputation or role requirements for some proposal categories

### Recommended baseline

Allow proposals from addresses that satisfy one of:

- hold at least a minimum threshold of governance power
- receive delegation above the proposal threshold
- are sponsored by another address that does

For high-risk proposal categories, DIN may require stricter gating.

Examples:

- treasury withdrawals above a threshold
- contract upgrades
- blacklist or unblacklist actions

## Who Is Allowed To Vote?

Voting eligibility should be determined by governance power at a snapshot.

Recommended rules:

- snapshot taken when proposal becomes active
- only addresses with governance power at that snapshot can vote
- delegation fixed by snapshot rules

This prevents votes from shifting mid-proposal in unstable ways.

## Proposal Lifecycle

DIN should define an explicit proposal lifecycle instead of ad hoc admin execution.

One reasonable lifecycle is:

1. Proposal draft
2. Discussion period
3. On-chain proposal creation
4. Voting delay
5. Voting period
6. Queueing if passed
7. Timelock delay
8. Execution
9. Finalization as accepted or rejected

### 1. Draft

The proposer defines:

- proposal type
- rationale
- target contracts
- function calls
- parameter values
- risk level

### 2. Discussion

This can happen off-chain first to reduce noisy on-chain spam.

Examples:

- forum discussion
- GitHub issue or RFC
- Snapshot-style temperature check

### 3. Creation

The formal proposal is submitted on-chain with:

- proposer identity
- proposal metadata URI
- executable actions or action hash
- snapshot block

### 4. Voting

Voters cast:

- `for`
- `against`
- optionally `abstain`

Proposal success should depend on:

- quorum
- majority rule or supermajority rule depending on proposal type

### 5. Queueing

If a proposal passes, it should usually be queued into a timelock rather than executed immediately.

### 6. Execution

After the timelock delay:

- accepted proposals can be executed
- rejected proposals expire without execution

### 7. Finalization

Proposal state becomes one of:

- executed
- rejected
- expired
- canceled

## Proposal Types And Thresholds

Not every proposal should use the same thresholds.

One reasonable model is:

### Low-Risk Parameter Changes

Examples:

- fee changes within bounded ranges
- small exchange-rate updates if that policy remains active

Possible governance settings:

- normal quorum
- simple majority
- standard timelock

### Medium-Risk Operational Actions

Examples:

- add or remove a slasher contract
- disable or re-enable a model
- blacklist or unblacklist a validator

Possible governance settings:

- higher quorum
- stronger review requirements
- maybe a shorter emergency path for protective actions but not for restorative ones

### High-Risk Treasury Or Upgrade Actions

Examples:

- large treasury withdrawals
- platform contract upgrades
- governance-contract upgrades
- transfer of critical protocol authority

Possible governance settings:

- higher proposal threshold
- higher quorum
- supermajority
- longer timelock

## Accepting, Rejecting, And Executing Proposals

DIN should separate these clearly.

### Accepted

A proposal is accepted if it:

- reaches quorum
- gets the required majority or supermajority
- passes category-specific checks

### Rejected

A proposal is rejected if it:

- fails quorum
- loses the vote
- is canceled due to invalidity or proposer failure

### Executed

An accepted proposal is only finalized after execution succeeds.

That matters because:

- a passed vote can still fail at execution if the action is malformed
- contracts may have changed state during the timelock period
- execution should be explicit and observable

## Example Governance Scope Mapping

The current centralized actions can be mapped roughly as follows:

### Registry Governance

- approve or reject model requests
- approve or reject manifest updates
- disable or enable models
- update fees
- withdraw fees

### Coordinator Governance

- add or remove slasher contracts
- update validator stake contract reference
- update DIN-per-ETH rate
- withdraw ETH treasury balance

### Stake Governance

With future contract changes, governance may also cover:

- blacklist validator
- unblacklist validator
- future staking parameter changes
- future jailing or appeal logic

### Upgrade Governance

- upgrade platform contracts
- replace governance executors
- change timelock parameters

## Emergency Governance

DIN likely needs an emergency path, but it should be narrow.

Possible emergency-only actions:

- disable a malicious model
- pause or freeze a dangerous slasher contract
- emergency blacklist subject to later review

Emergency powers should not bypass governance permanently.

Reasonable safeguards:

- emergency action expires unless ratified
- emergency council scope is narrow
- emergency actions are transparent and reviewable
- restorative actions such as unblacklisting may require normal governance or appeal flow

## Recommended Governance Architecture

One practical direction is a layered architecture:

### Layer 1. Token / Voting Power Layer

- DIN locked or staked for governance power
- delegation supported
- snapshot-based accounting

### Layer 2. Proposal Layer

- proposal thresholds
- proposal metadata
- typed proposal categories

### Layer 3. Voting Layer

- quorum rules
- majority or supermajority rules
- per-category thresholds

### Layer 4. Timelock / Execution Layer

- queue successful proposals
- enforce execution delay
- execute approved contract calls

### Layer 5. Emergency Layer

- narrowly scoped emergency authority
- post-action ratification or review

## Suggested Phased Rollout

### Phase 1. DAO-Controlled Platform Admin

Replace direct admin or owner actions with a DAO executor or timelock that controls:

- `DINModelRegistry` admin functions
- `DinCoordinator` owner functions

This is the smallest meaningful decentralization step.

### Phase 2. Governance Process Standardization

Introduce:

- proposal thresholds
- quorum rules
- voting periods
- timelocks
- delegation

### Phase 3. Expanded Governance Scope

Add governance control over:

- treasury routing
- blacklist and unblacklist logic
- platform upgrades
- staking parameter changes

### Phase 4. Advanced Governance

Only later, if justified:

- quadratic signaling
- reputation overlays
- bicameral governance by role
- specialized committees for appeals or emergency review

## Open Design Questions

- Should model approval and manifest approval remain direct DAO votes, or should governance delegate those to a smaller elected committee?
- Should validator blacklisting and unblacklisting require the same threshold?
- Should treasury proposals and contract-upgrade proposals require supermajority?
- Should DIN governance power come from staked DIN, locked DIN, or a hybrid?
- Should quadratic voting be used anywhere beyond non-binding signaling?
- Should model owners, validators, and token holders all vote in one chamber, or should DIN eventually separate roles?

## Good Contribution Directions

- define the minimum DAO scope for platform-level admin replacement
- design governance contracts and timelock flow
- propose a voting-power model based on DIN commitment rather than raw balance
- design blacklist and unblacklist appeal mechanics
- compare token-weighted and quadratic voting for DIN specifically
- prototype proposal categories with different thresholds
- document off-chain discussion plus on-chain execution workflow

## Conclusion

DIN should move the authority currently held by `dinDAO` admin keys and platform-contract owners into a DAO-based governance system for production.

The recommended default is not raw quadratic voting on transferable DIN. A stronger first step is:

- snapshot-based governance power from staked or locked DIN
- proposal thresholds
- quorum rules
- category-specific voting requirements
- timelocked execution

`DINModelRegistry` fee updates and validator blacklisting are good examples, but the broader scope is all platform-level authority that should eventually be governed by the DAO rather than a centralized admin.
