# Model Owner Contract Builder

## Summary

DevNet requires model owners to deploy task-level smart contracts before a training task can run.

Today, the concrete task contracts in the repo are:

- `DINTaskCoordinator`
- `DINTaskAuditor`

Aggregation is currently coordinated through `DINTaskCoordinator`, so there is not yet a separate `TaskAggregator` contract in the codebase. The tooling direction should still be modular enough to support future task-level contracts if the protocol later splits more responsibilities on-chain.

What is missing today is a model-owner-facing tool that can assemble these contracts from selectable options, generate the final contract artifacts, help compile them, and guide deployment once the wallet is connected.

## Problem

The current contract workflow is too static:

- model owners deploy predefined contract artifacts
- behavior is mostly fixed in Solidity rather than selected from explicit task-level options
- constructor inputs and deployment dependencies are handled late in the process
- deployment and manifest wiring are separated from configuration
- extending task behavior can require direct contract edits instead of modular generation

That is workable for a single demo path, but it is not a good long-term model-owner product experience.

## Goal

Provide a contract builder in `dincli` that helps a model owner generate task-level contract artifacts from explicit configuration choices.

The tool should let a model owner:

1. choose which task contracts to generate
2. select protocol options and task-specific parameters
3. generate final Solidity or artifact outputs
4. compile those contracts
5. connect a wallet and deploy them
6. surface the deployed addresses as manifest-ready outputs

The generated workflow should stay compatible with the current deployment path documented in `Documentation/model-owner.md`.

## Current Contract Model

Based on the current repo, the model-owner task flow depends on:

- `DINTaskCoordinator.sol`
- `DINTaskAuditor.sol`
- `DinValidatorStake` as an external dependency already deployed by the protocol

Current deployment logic in `dincli` does the following:

1. deploy `DINTaskCoordinator` with the validator stake contract address
2. deploy `DINTaskAuditor` with the validator stake address and task coordinator address
3. set the deployed auditor address inside the coordinator
4. persist deployed addresses into `.env`
5. later place the task coordinator and task auditor addresses into `manifest.json`

This means a contract builder should generate artifacts that fit the same dependency chain.

## Expected Inputs

The tool should expose task-level configuration instead of forcing contract edits.

Examples:

- validator and staking policy options
- registration and quorum settings
- auditor batch settings
- model submission limits
- pass-score defaults
- reward and deposit rules
- slashing-related toggles or thresholds
- ownership and admin settings
- network-specific deployment configuration

Example configuration shape:

```yaml
task_contracts:
  coordinator:
    enabled: true
    aggregator_registration: validator_only
    t1_aggregators_per_batch: 3
    t1_models_per_batch: 3
    min_t1_models_per_batch: 2

  auditor:
    enabled: true
    auditors_per_batch: 3
    models_per_batch: 3
    min_eligibility_quorum: 2
    min_score_quorum: 2
    pass_score: 50
    min_models_per_batch: 2

deployment:
  network: sepolia_op_devnet
  owner: wallet
  write_env: true
  update_manifest: true
```

## Generated Outputs

The contract builder should be able to produce:

- generated Solidity files, or finalized artifact JSON files
- deployment metadata describing constructor arguments and dependencies
- compile-ready project outputs for Hardhat or Foundry
- deployment commands or deployable build artifacts
- manifest-ready address fields after deployment

Possible output layout:

```text
artifacts/task-contracts/
  DINTaskCoordinator.json
  DINTaskAuditor.json

generated/task-contracts/
  DINTaskCoordinator.sol
  DINTaskAuditor.sol

tasks/<network>/<task_coordinator_address>/
  manifest.json
```

## Core Capabilities

### 1. Modular Contract Composition

The contract builder should treat task contracts as configurable modules rather than one frozen artifact set.

Examples:

- coordinator variants with different registration or aggregation rules
- auditor variants with different quorum or scoring assumptions
- optional feature flags for slashing, deposits, or evaluation policies
- future support for additional task-level contracts beyond coordinator and auditor

### 2. Parameter Injection

Task-level parameters should be selected in config and reflected in the generated contract output.

Examples:

- quorum thresholds
- pass-score defaults
- batch sizing
- submission limits
- ownership defaults
- addresses of required external DIN contracts

### 3. Artifact Generation

The builder should produce outputs that are readable and easy to audit before deployment.

This can be implemented with:

- Solidity templates
- feature fragments merged into base contracts
- code generation from a typed config schema
- a thin wrapper layer over stable base contracts with generated constructor/config values

The exact strategy can vary, but the resulting artifacts should be deterministic and deployable.

### 4. Compile Integration

The tool should help the model owner move directly from configuration to compiled artifacts.

That includes:

- validating source generation before compile
- invoking Hardhat or Foundry compilation
- surfacing ABI and bytecode outputs
- indicating the artifact path expected by existing `dincli model-owner deploy ...` commands

### 5. Wallet And Deployment Integration

After artifacts are generated and compiled, the tool should support the deployment flow:

1. connect wallet
2. choose network
3. deploy coordinator
4. deploy auditor with coordinator dependency
5. run any required post-deploy wiring
6. save deployed addresses

This should align with the existing wallet-based deployment model in `dincli`.

### 6. Manifest Integration

The contract builder should also help wire deployment outputs back into task metadata.

At minimum it should be able to surface:

- `DINTaskCoordinator_Contract`
- `DINTaskAuditor_Contract`

and optionally patch a local `manifest.json` after successful deployment.

## Proposed Workflow

1. Model owner selects a task contract profile.
2. Model owner chooses contract options and parameters.
3. `dincli` generates contract sources or final artifacts.
4. `dincli` compiles the generated contracts.
5. Model owner connects a wallet.
6. `dincli` deploys the task coordinator.
7. `dincli` deploys the task auditor.
8. `dincli` performs any required post-deploy contract wiring.
9. `dincli` writes the deployed addresses to `.env` and optionally into `manifest.json`.

## CLI Direction

One reasonable CLI direction is:

```bash
dincli build contracts \
  --config contract-builder.yaml \
  --output generated/task-contracts
```

Followed by compile and deploy steps such as:

```bash
dincli build contracts --config contract-builder.yaml --compile
dincli system connect-wallet --account 0
dincli build contracts --config contract-builder.yaml --deploy
```

Additional commands could include:

```bash
dincli build contracts --list-profiles
dincli build contracts --describe coordinator
dincli build contracts --config contract-builder.yaml --write-manifest
```

## Architecture Direction

A practical implementation can be split into four layers:

### 1. Contract Module Registry

Defines the supported contract families, variants, and parameters.

### 2. Builder Configuration Schema

Defines the validated user-facing contract configuration.

### 3. Generator And Compiler Layer

Produces sources or artifacts and compiles them into deployable outputs.

### 4. Deployment And Manifest Writer

Handles wallet-based deployment, dependency ordering, environment updates, and manifest wiring.

## Near-Term Scope

A first usable version should stay narrow and align with what the repo already supports:

- generate or parameterize `DINTaskCoordinator`
- generate or parameterize `DINTaskAuditor`
- support a small set of selectable task parameters
- compile with the existing Solidity toolchain
- deploy through existing `dincli` wallet and network flows
- emit manifest-ready contract addresses

Good initial parameters to expose:

- auditor batch sizing
- score quorum
- eligibility quorum
- pass score
- model submission limits
- simple registration-policy toggles

## Why This Matters

This tooling would make contract deployment part of a coherent model-owner workflow instead of a manual Solidity handoff.

It moves DevNet toward:

- configurable task-level contract generation
- safer deployment flows
- clearer task configuration
- better alignment between on-chain behavior and model-owner intent
- easier iteration as task mechanics evolve

In practice, this is the missing layer between fixed demo contracts and a real model-owner contract product.
