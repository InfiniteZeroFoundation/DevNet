# DIN Tokenomics

## Summary

This issue defines the token-economic work needed to turn DIN from a devnet utility and staking token into a credible protocol asset.

Today DIN exists and is used as validator collateral, but its issuance, reserve policy, fee routing, reward flows, and slash settlement are still incomplete or overly administrative.

## Scope Boundary

This issue assumes the current `hardhat` staking flow already includes:

- unbonding in `DinValidatorStake.sol`
- slashability across active stake and pending withdrawals
- implemented auditor slashing

The focus here is not validator lifecycle mechanics. It is DIN itself:

- what DIN represents
- how DIN is issued
- why participants should demand it
- how DIN is sunk, redistributed, or burned
- how DIN treasury policy is governed

## Why This Matters

If DIN is the security asset for validators, protocol security depends on DIN's real economic properties, not only on the existence of staking code.

Without a coherent token model:

- stake thresholds do not map cleanly to cost of corruption
- slashing may punish on paper without creating a real sink or redistribution
- protocol usage may not create sustained DIN demand
- treasury flows can become disconnected from validator incentives
- governance can change core economics too easily

## Current State

### 1. DIN issuance

- `DinCoordinator.sol` deploys `DinToken.sol`.
- Any user can call `depositAndMint()` to mint DIN from ETH at `dinPerEth`.
- `owner()` can update `dinPerEth` at any time.
- `owner()` can withdraw the full ETH balance from `DinCoordinator.sol`.

### 2. DIN token contract

- `DinToken.sol` is a plain ERC-20 with 18 decimals.
- Mint authority is permanently bound to `DinCoordinator.sol` through the immutable `OWNER`.
- There is no cap, no burn path, no vesting logic, and no built-in governance power.
- Because mint authority is immutable, major issuance redesigns may require coordinator and token migration instead of a simple ownership handoff.

### 3. DIN utility today

- The implemented on-chain use of DIN is mainly validator staking in `DinValidatorStake.sol`.
- `MIN_STAKE` is fixed at `10 DIN`.
- Validators can be slashed across both active stake and pending withdrawals.

### 4. Fee and treasury flows

- `DINModelRegistry.sol` charges protocol fees in ETH, not DIN.
- `DinCoordinator.sol` also receives ETH from DIN minting and can withdraw it to the owner.
- The current protocol therefore collects ETH while asking validators to secure the network with DIN.

### 5. Rewards and settlement

- Slashing reduces validator balances, but there is still no explicit burn, insurance, treasury, or redistribution path for slashed DIN.
- Reward distribution is not implemented.
- `DINTaskAuditor.sol` contains reward-related placeholders, but there is no live DIN reward accounting or claim flow.

## What DIN Currently Is

- a mintable ERC-20 issued against ETH deposits
- a staking collateral token for validators
- not yet a fee token
- not yet a complete reward token
- not yet a fully specified governance asset

## Main Gaps

### 1. DIN is administratively priced

`dinPerEth` is an owner-controlled issuance parameter. That means the amount of DIN required to become a validator can be diluted or tightened administratively rather than through a clear monetary policy.

### 2. ETH-backed issuance has no explicit reserve policy

Users mint DIN by depositing ETH, but the contract owner can withdraw all ETH. If DIN is not redeemable or reserve-backed, that should be explicit in the design. If it is supposed to carry any notion of backing, the reserve policy is incomplete.

### 3. Slashing is not economically finalized

A slash that only updates staking balances is not enough. The protocol still needs a defined destination for confiscated DIN:

- burn
- insurance fund
- treasury
- validator reward redistribution

Without that, total supply, treasury balances, and slash economics remain hard to reason about.

### 4. DIN demand is weakly tied to protocol usage

Current model registration and manifest fees are paid in ETH. That means protocol activity does not automatically create DIN demand or DIN-denominated revenue.

### 5. Rewards are missing

Validators currently face penalties but no implemented DIN reward flow. Production tokenomics needs both:

- a source of rewards
- a rule for distributing rewards
- a claim and accounting path
- anti-manipulation rules around performance-linked rewards

### 6. The stake floor is not economically grounded

A fixed `10 DIN` minimum is suitable for devnet bootstrapping, but not as a serious security threshold unless DIN value, validator count, and corruption assumptions make that threshold meaningful.

### 7. Governance over token policy is still highly centralized

DIN issuance rate, ETH treasury withdrawal, and fee parameters still rely on owner or DAO-admin style controls. That is acceptable for a devnet, but it is not a durable token-policy governance model.

## The Core Design Decision

Before DIN tokenomics is production-ready, the protocol needs to choose what DIN actually is.

### Option A: DIN is a pure utility and staking token

If so:

- remove any implied reserve-backed framing
- treat DIN issuance as emissions or treasury policy, not quasi-redemption
- design validator rewards, fee sinks, and governance explicitly around DIN

### Option B: DIN is an ETH-backed or treasury-backed asset

If so:

- define reserve custody rules
- define whether DIN is redeemable
- define collateral ratios and treasury restrictions
- define what happens when backing and supply diverge

### Option C: DIN is a market-acquired security asset

If so:

- remove direct mint-on-ETH-deposit issuance
- let DIN trade externally
- use protocol revenues to buy back, reward, or subsidize validators instead of administratively pricing DIN

DIN can support governance and utility in any of these models, but the protocol should not mix them implicitly.

## Recommended Direction

### 1. Decide DIN's asset model

Pick one primary model for DIN and write it down in protocol docs and contracts:

- emission token
- backed asset
- market-collateral token

### 2. Formalize issuance policy

Replace ad hoc issuance with a governed policy such as:

- fixed emission schedule
- capped supply plus treasury releases
- formula-based issuance with bounded change rules
- timelocked governance updates for any rate changes

### 3. Complete slash settlement

Choose one explicit destination for slashed DIN and implement it on-chain:

- burn address
- insurance reserve
- protocol treasury
- reward pool

### 4. Add validator reward mechanics

Define:

- reward source
- accounting unit
- distribution frequency
- performance criteria
- claim flow
- treatment of jailed, exiting, or slashed validators

### 5. Align fees with DIN utility

Either:

- denominate some protocol fees in DIN, or
- keep fees in ETH but define how ETH revenue strengthens DIN demand or validator rewards

### 6. Replace nominal stake floors with economic targets

The minimum validator stake should be derived from a target security budget or cost-of-corruption model, not just a constant chosen for testing.

### 7. Put token policy behind stronger governance

At minimum:

- timelock rate changes and treasury withdrawals
- move owner powers to DAO execution
- define proposal classes for issuance, rewards, and treasury policy

## Proposed Work Packages

### WP 5.1: DIN Issuance and Reserve Policy

Scope:

- choose DIN's asset model
- define supply policy
- define reserve semantics for ETH collected by `DinCoordinator.sol`

Deliverables:

- DIN tokenomics spec
- coordinator redesign or parameter-governance spec
- tests for issuance and treasury invariants

### WP 5.2: DIN Staking Economics

Scope:

- finalize slash settlement
- define real validator stake thresholds
- model attack cost versus validator rewards and penalties

Deliverables:

- staking economics spec
- updated slashing settlement implementation
- simulation inputs for cost-of-corruption analysis

### WP 5.3: Rewards, Fees, and Treasury Routing

Scope:

- define validator rewards
- connect model-owner fees, treasury revenue, and validator incentives
- decide whether DIN or ETH is the settlement asset for each fee class

Deliverables:

- reward accounting design
- fee routing design
- treasury policy document

## Minimum Exit Criteria

DIN tokenomics should not be considered production-candidate until the protocol has:

- a written DIN asset model
- a bounded and governable issuance policy
- completed slash settlement semantics
- implemented validator rewards
- a clear fee-routing model
- a stake threshold tied to real economic security
- governance controls over treasury and token policy
- simulations for dilution, Sybil cost, validator profitability, and slash scenarios

## Bottom Line

The current DIN design is acceptable for a devnet where staking exists mainly to gate validator participation. It is not yet a finished token-economic system.

The next step is not another small contract patch. It is a deliberate DIN policy design that connects issuance, staking, slashing, rewards, fees, treasury, and governance into one coherent economic model.
