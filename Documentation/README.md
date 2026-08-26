# DIN Protocol Documentation

Documentation for the DIN Protocol DevNet as implemented on the `develop` branch.

> **Scope rule:** everything in this folder describes **what exists in the code on `develop`** — not the live deployment on Optimism Sepolia (which may lag `develop`), and not planned or proposed designs. Plans, designs, proposals, and process docs live in [`Developer/`](../Developer/README.md). If a change to the code would make a document here wrong, the document belongs here; if it would still be valid, it belongs in `Developer/`.

## Layout

- **[`public/`](public/)** — for network participants (validators, clients, model owners). Assumes you operate the network through `dincli`; never requires reading source code.
- **[`technical/`](technical/)** — internal documentation for people modifying or auditing the code.

## Public documentation

| Document | Purpose |
|---|---|
| [Getting Started](public/getting-started.md) | Onboarding guide for Model_0 on the live devnet (`sepolia-op-devnet`) |
| [Setup Guide](public/setup.md) | Installing and configuring `dincli`: venv, wallet, network, logging, demo mode, IPFS |
| [CLI Reference](public/cli-reference.md) | Common `dincli` reference across all roles |
| [Manifest](public/manifest.md) | The per-model `manifest.json`: metadata, services, contract addresses |
| [Services](public/services.md) | Service files a model owner must provide (model, client, auditor, aggregator logic) |

### Role guides — [`public/roles/`](public/roles/)

One guide per network role: [Clients](public/roles/clients.md) · [Auditors](public/roles/auditors.md) · [Aggregators](public/roles/aggregators.md) · [Model Owners](public/roles/model-owner.md) · [DIN-Representative (dindao)](public/roles/dindao.md)

### Workflows — [`public/workflows/`](public/workflows/)

- [DIN Workflow](public/workflows/din-workflow.md) — platform-level contracts and how they relate (deployed once, by the DIN-Representative)
- [Model Workflow](public/workflows/model-workflow.md) — task-contract lifecycle per model: deploy → slasher authorization → genesis model → registration → Global Iterations

### Guides — [`public/guides/`](public/guides/)

- [Wallet Setup](public/guides/wallet-setup.md) — burner wallet and encrypted keystore setup
- [Keystore Migration](public/guides/keystore-migration.md) — migrating from plaintext `.env` keys to encrypted keystores
- [IPFS](public/guides/ipfs.md) — configuring the IPFS backend (node, Filebase, or custom provider)
- [Client Onboarding](public/guides/client-onboarding.md) — model-owner-to-client onboarding instructions

## Technical documentation

| Area | Contents |
|---|---|
| ARCHITECTURE.md | System architecture reference (first complete draft tracked as P3-DOC1) |
| [`contracts/`](technical/contracts/) | Per-contract references: `DinCoordinator`, `DinToken`, `DinValidatorStake`, `DINModelRegistry`, `DINTaskCoordinator`, `DINTaskAuditor`, `DINShared` |
| [`mechanisms/`](technical/mechanisms/) | Currently implemented protocol mechanisms (e.g. [staking](technical/mechanisms/staking-mechanism.md)) |
| [`services/`](technical/services/) | Reference service internals (e.g. [client service](technical/services/clients.md)) |
| [`testing/`](technical/testing/) | [dincli testing guide](technical/testing/dincli-testing-guide.md), [containerization guide](technical/testing/containerization-guide.md) |
| [`upgradable-contracts/`](technical/upgradable-contracts/) | Transparent Proxy deployment architecture and upgrade test documentation |
| [manifest.md](technical/manifest.md) | Manifest runtime resolution and service loading internals |
| [requirements.md](technical/requirements.md) | Pinned pip requirements reference |
