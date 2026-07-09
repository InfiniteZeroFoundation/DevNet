# Upgradeable Contracts

## Summary

This issue covers how DIN should approach upgradeable smart contracts across the contracts in `hardhat/contracts/`.

The main conclusion is that upgradeability should not be treated uniformly across every contract type.

For production, the platform-level contracts should be upgradeable at minimum:

- `DinCoordinator.sol`
- `DinToken.sol`
- `DinValidatorStake.sol`
- `DINModelRegistry.sol`

By contrast, task-level contracts such as:

- `DINTaskCoordinator.sol`
- `DINTaskAuditor.sol`

do not necessarily need the same upgradeability guarantees in the first production architecture. They can be redeployed if needed because their state is tied to task execution and global iteration flow, which can be shifted operationally. For example, if a task contract is replaced, what was supposed to be global iteration 3 in one deployment can become global iteration 1 in the next deployment as long as the transition is handled explicitly.

So the real design question is not "should every DIN contract be upgradeable?" The better question is:

- which contracts are part of long-lived platform state
- which contracts are task-scoped and replaceable
- what governance and storage guarantees are required for each group

## Why This Matters

DIN has two different contract layers:

### 1. Platform-Level Contracts

These define shared protocol infrastructure and network-wide state.

Examples:

- token minting and token supply logic
- validator staking and slasher permissions
- model registry and manifest governance
- coordinator-level control over protocol wiring

These contracts are expensive to replace once the network is live because they hold persistent state and act as shared dependencies for the rest of the system.

### 2. Task-Level Contracts

These define execution for a specific model or training task.

Examples:

- task-specific aggregation workflow
- task-specific auditor workflow
- global iteration lifecycle for one model

These contracts are more replaceable because their scope is narrower and their state is operational rather than foundational.

That distinction matters because a production DIN deployment should protect long-lived platform state from forced redeployments, while still allowing more flexibility for task-level experimentation.

## Current Contract Set

Current contracts under `hardhat/contracts/` include:

- `DinCoordinator.sol`
- `DinToken.sol`
- `DinValidatorStake.sol`
- `DINModelRegistry.sol`
- `DINTaskCoordinator.sol`
- `DINTaskAuditor.sol`
- `DINShared.sol`
- `MockUSDT.sol`

Not every file needs the same treatment.

Reasonable categorization:

### Platform-Level

- `DinCoordinator.sol`
- `DinToken.sol`
- `DinValidatorStake.sol`
- `DINModelRegistry.sol`

### Task-Level

- `DINTaskCoordinator.sol`
- `DINTaskAuditor.sol`

### Support / Non-Production / Shared

- `DINShared.sol`
- `MockUSDT.sol`

## Production Direction

The production default should be:

- platform-level contracts should be upgradeable
- task-level contracts may remain redeployable
- support and mock contracts do not drive the upgradeability policy

That does not mean task-level contracts can never be made upgradeable. It means they are lower priority because redeployment is operationally feasible there, while it is much more disruptive for the platform layer.

## Why Platform Contracts Should Be Upgradeable

### DinCoordinator

`DinCoordinator` is protocol infrastructure. It controls token minting flow, slasher management, and validator stake wiring.

If this logic needs to change in production, replacing the contract by redeployment can break:

- minting flow assumptions
- ownership and admin flows
- integrations with the validator stake system
- references used by operators and tooling

### DinToken

`DinToken` is part of the platform’s monetary layer.

Even if the token remains simple, production systems usually need a careful answer for:

- token ownership and mint authority
- future monetary policy changes
- integration stability

If DIN intends the token contract itself to remain fixed forever, that should be a deliberate decision. Otherwise, the platform should plan for an upgradeable token path or a very clearly constrained non-upgradeable token design.

### DinValidatorStake

`DinValidatorStake` holds economically critical validator state:

- active stake
- pending withdrawals
- validator status
- slasher authorizations

This is one of the strongest cases for upgradeability because redeploying it would disrupt staking continuity and validator trust assumptions.

### DINModelRegistry

`DINModelRegistry` holds long-lived protocol metadata and governance state:

- registered models
- pending requests
- manifest update history
- task coordinator and auditor mappings
- model disable state
- fee settings

This is another strong case for upgradeability because registry continuity matters once the network is in use.

## Why Task-Level Contracts Can Be Redeployed

Task contracts are different because they are scoped to one training lifecycle.

If a task contract needs major logic changes, it is often acceptable to:

1. deploy a new task contract
2. register or reference the new contract set
3. continue the task under a fresh local iteration numbering scheme

Operationally, that can mean:

- a previous deployment ended at GI 3
- the replacement deployment starts again at GI 1
- the network treats that as a new task epoch or replacement task flow

This is not free of complexity, but it is still much easier to reason about than redeploying core platform contracts that hold shared economic and governance state.

## Example: DINModelRegistry

`DINModelRegistry.sol` is a useful example, but it should be treated as one member of the broader platform-contract set, not the only upgradeability concern.

The registry is currently a normal constructor-based contract with direct state storage. That means it is not upgradeable by architecture, even though parts of its governance logic are already mutable.

For example:

- `daoAdmin` is mutable storage and can already be changed with `setDAOAdmin(...)`
- but the contract is still not proxy-based
- so logic upgrades would still require redeployment unless the deployment model changes

The same broader architectural issue also appears elsewhere in the platform layer.

## Current Upgradeability Obstacles

Several platform contracts currently use patterns that are not directly compatible with the standard proxy-based upgrade flow.

### 1. Constructor-Based Initialization

Multiple contracts rely on constructors rather than initializers.

That is common in simple deployments, but upgradeable contracts usually need initializer-based setup.

### 2. Immutable References

Some platform contracts currently use `immutable` state for critical references.

Examples in the current codebase include:

- `DinToken` uses immutable `OWNER`
- `DinCoordinator` uses immutable `dinToken`
- `DinValidatorStake` uses immutable `DIN_TOKEN`
- `DinValidatorStake` uses immutable `DIN_COORDINATOR`

Those patterns are fine for non-upgradeable deployments, but they are a major constraint if the platform wants standard proxy-based upgradeability.

### 3. Direct Deployment Coupling

Platform contracts are wired to one another through constructor-time assumptions and direct address binding.

That makes deployment straightforward today, but increases migration complexity if upgradeability is added later.

### 4. Storage Layout Discipline

Contracts like `DinValidatorStake` and `DINModelRegistry` maintain meaningful persistent state in mappings, arrays, and structs.

That state can be preserved through proxy upgrades, but only if storage layout rules are treated seriously.

## Broader Upgradeability Strategy

DIN should define an upgradeability policy at the architecture level, not contract by contract in isolation.

One reasonable policy is:

### Platform Layer

- use proxy-based upgradeability
- use initializer-based deployment
- use governance-controlled upgrade authorization
- document storage layout rules
- test upgrades explicitly

### Task Layer

- allow normal redeployment by default
- treat contract replacement as a task lifecycle event
- provide tooling and documentation for task migration

This keeps production guarantees focused where they matter most.

## Proxy Pattern Options

The platform-level contracts do not all have to use the exact same proxy pattern, but they should follow a coherent operational model.

### Option 1. UUPS

Good fit when the team wants a lean proxy approach.

Advantages:

- smaller proxy overhead
- widely used pattern
- implementation controls authorization

Tradeoffs:

- stricter implementation discipline required
- upgrade logic lives in the implementation path

### Option 2. Transparent Proxy

Good fit when the team wants a clearer admin/logic separation.

Advantages:

- easier operational separation for governance
- familiar upgrade model

Tradeoffs:

- more proxy/admin surface area
- slightly heavier setup

### Option 3. Mixed Strategy

DIN could also choose a pragmatic mixed model:

- one standard proxy approach for all four platform contracts
- no proxy requirement for task-level contracts initially

That is likely simpler than trying to make every contract category behave identically.

## Recommendation

The most practical near-term direction is:

1. define the four platform contracts as production-upgradeable
2. keep task contracts redeployable unless a strong reason appears to make them upgradeable too
3. refactor constructor and immutable patterns in the platform layer
4. add deployment and upgrade tests before treating the architecture as production-ready

This preserves flexibility without forcing upgrade complexity everywhere.

## Required Changes For Platform Contracts

If DIN adopts proxy-based upgradeability for the four platform contracts, contributors should expect refactors such as:

- replace constructors with initializers
- remove or redesign immutable dependency references where needed
- move to upgrade-safe base contracts
- define explicit upgrade authorization
- preserve storage layout in append-only fashion
- document cross-contract wiring during initialization

This work is larger than a `DINModelRegistry` patch. It is a platform architecture refactor.

## Contract-Specific Concerns

### DinCoordinator

Questions to resolve:

- should `DinToken` continue to be created internally, or should it be deployed and wired externally?
- how should coordinator upgrades interact with token ownership and mint flow?
- should rate logic remain mutable through governance?

### DinToken

Questions to resolve:

- should mint authority remain tightly bound to the coordinator?
- should token ownership be upgrade-governed or intentionally fixed?
- if token logic stays simple, is a non-upgradeable token acceptable while the rest of the platform is upgradeable?

This is one place where the team should challenge assumptions rather than accept upgradeability by default.

### DinValidatorStake

Questions to resolve:

- how should stake continuity be preserved through upgrades?
- how should slasher permissions be migrated or preserved?
- should minimum stake and unbonding rules remain constants or become configurable state?

### DINModelRegistry

Questions to resolve:

- what upgrade authority should control registry logic?
- should `dinValidatorStake` remain fixed after initialization or be governable?
- how should long-term request history be handled if storage grows significantly?

## Testnet Vs Production

For testnet, redeployment is often enough.

For production, the platform layer should assume upgrades are necessary over time for:

- security patches
- governance changes
- economics changes
- staking rule changes
- registry logic evolution

That makes upgradeability a production requirement for the platform layer even if task-level contracts remain redeployable.

## Suggested Implementation Plan

### Phase 1. Policy Definition

- define which contracts are platform-level
- define which contracts are task-level
- choose the proxy model for platform contracts

### Phase 2. Platform Refactor

- convert `DinCoordinator`
- convert `DinToken` or deliberately justify a fixed-token exception
- convert `DinValidatorStake`
- convert `DINModelRegistry`

### Phase 3. Deployment Tooling

- add platform proxy deployment scripts
- add initializer-safe wiring flow
- document canonical proxy addresses

### Phase 4. Upgrade Testing

For each platform contract, prove:

- state persists across upgrades where state exists
- authorization remains correct
- integrations with other platform contracts still work

### Phase 5. Task-Level Operational Guidance

- document how to redeploy task contracts safely
- document how GI transitions should be handled operationally
- document how manifests and registry references should be updated when task contracts are replaced

## Suggested Tests

Contributors should add upgrade tests for the platform layer.

Examples:

- stake validators, upgrade `DinValidatorStake`, then verify balances and statuses remain intact
- register models, upgrade `DINModelRegistry`, then verify all lookups and request state remain intact
- verify `DinCoordinator` still manages slasher configuration correctly after upgrade
- verify token mint flow remains valid across coordinator and token changes
- verify only the intended governance authority can execute upgrades

Contributors should also add operational tests or simulations for task-level redeployment paths.

Examples:

- replace task contracts and confirm a model owner can continue the task under a new GI sequence
- verify manifest and contract references can be updated coherently after task contract replacement

## Open Design Questions

- Should all four platform contracts use the same proxy pattern?
- Should `DinToken` be upgradeable, or should it remain deliberately fixed with the rest of the platform adapting around it?
- Should platform upgrades be controlled by a multisig, DAO executor, or timelock?
- Should any task contracts become upgradeable later, or is redeployment enough long-term?
- How should task-level replacement be represented in manifests and model lifecycle metadata?

## Good Contribution Directions

- define a formal platform-vs-task contract policy
- prototype upgradeable versions of the four platform contracts
- remove immutable constructor-coupled references where necessary
- write deployment and upgrade tests
- document safe task-level redeployment procedures
- propose governance-safe upgrade authority patterns

## Conclusion

DIN should not treat upgradeability as an all-or-nothing property across every contract in `hardhat/contracts/`.

The better production architecture is:

- platform-level contracts are upgradeable
- task-level contracts are redeployable by default
- upgrade complexity is concentrated where long-lived economic and governance state must be preserved

`DINModelRegistry` is a useful example of the problem, but the broader scope is the four platform contracts that anchor DIN itself.
