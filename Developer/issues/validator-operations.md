# Validator Operations and Onboarding Readiness

## Summary

This issue captures the operational baseline that external validators are likely to expect before bringing DIN nodes online.

The feedback is not a demand to implement everything immediately. It is a useful checklist for shaping the roadmap so validator onboarding does not depend on improvised local setup, plaintext secrets, unclear resource needs, or fragile restart behavior.

The near-term goal is to define a practical operator path for clients, aggregators, and auditors, with validators as the first production-readiness target.

## Why This Matters

DIN validators will eventually run long-lived services that:

- hold or use signing authority
- download untrusted task artifacts
- run aggregation or audit workloads
- maintain local task state
- face slashing or missed-reward risk if they fail incorrectly

For production-oriented operators, the minimum bar is not only "the command works." It is:

- the node can be started, stopped, upgraded, and monitored predictably
- key material is not stored in plaintext `.env` files
- resource requirements are known before joining
- shutdown does not corrupt local state
- failure modes and slashing risks are understandable

These are standard hygiene requirements for validator networks and will make future onboarding smoother.

## Current State

DIN is still early, and the current CLI/devnet path is intentionally lightweight.

Current gaps include:

- no standard Docker Compose run path for validators — **Addressed for devnet by `din-node`; see `dincli/docker/node/` (PR #12).**
- no documented one-command start, stop, and upgrade flow
- no clear production key-management guidance beyond local wallet configuration
- no published resource ceilings per role
- no daemon-level `/health` endpoint
- no structured logging contract
- no `systemd` or `launchd` service examples
- incomplete public documentation for slashing rules and known validator failure modes

This issue should evolve alongside `dind`, containerization, staking, slashing, and validator selection.

## Blocking Requirements

These are the items most likely to block serious external validator onboarding.

### 1. Containerized Run Path

DIN should provide a documented containerized path for validator operation.

Minimum target:

- Docker image for the validator-capable runtime
- Docker Compose file for local operation
- one-command start
- one-command stop
- one-command upgrade
- documented volume layout
- log access instructions
- clear distinction between trusted host code and untrusted task execution containers

This overlaps with [Containerization and Sandboxed Execution](containerization.md), but this issue tracks the operator-facing runbook.

### 2. Secure Key Handling

DIN should not recommend plaintext private keys in `.env` for validator operation.

Acceptable early approaches:

- passphrase-protected keystore files
- host-side signing process outside untrusted containers
- operator-managed secret injection
- 1Password CLI for local secret retrieval

Future approaches:

- vault-backed setup
- hardware wallet or remote signer support
- key rotation and emergency key disablement workflows

Important default:

- untrusted task code must never receive wallet files, decrypted private keys, or signing environment variables.

### 3. Resource Ceilings

DIN should publish expected and maximum resource profiles for each validator role.

At minimum, document:

- RAM
- CPU
- disk
- network bandwidth
- expected model artifact/cache growth
- optional GPU requirements
- per-role differences between aggregators and auditors

These ceilings should connect to capability-aware validator selection so operators are not assigned work their machines predictably cannot complete.

### 4. Graceful Shutdown

Long-running DIN services should handle `SIGTERM` cleanly.

Shutdown behavior should:

- stop accepting new work
- finish or checkpoint safe in-progress work where possible
- avoid corrupting local state files
- mark incomplete job state clearly
- release locks
- exit with a meaningful status code

This is required for Docker, `systemd`, `launchd`, Kubernetes-style runtimes, and ordinary operator restarts.

## Strong Preferences

These are not necessarily hard launch blockers, but they are high-value for validator trust and operations.

### HTTP Health Endpoint

Add a basic `/health` endpoint for long-running daemon or validator service modes.

Useful checks:

- process alive
- config loaded
- network/RPC reachable
- wallet signer available without exposing secrets
- disk space above threshold
- current role state
- last successful job or sync timestamp

### Structured Stdout Logs

Validator services should emit structured logs to stdout.

Recommended default:

- JSON logs for daemon/container mode
- human-friendly logs for interactive CLI mode
- fields for timestamp, level, role, network, model/task id, GI, job id, and error code

### Network Isolation Guidance

DIN should document recommended network isolation for:

- host validator process
- untrusted task execution containers
- IPFS access
- RPC access
- optional outbound internet access

Default stance:

- trusted host process gets only the network access it needs
- untrusted task containers get no network access unless explicitly required by task policy

### Service Manager Units

Provide examples for:

- `systemd` on Linux
- `launchd` on macOS

These should cover:

- restart policy
- environment/config location
- stop timeout
- log collection
- working directory
- Docker Compose integration if relevant

### Slashing and Failure-Mode Documentation

Publish operator-facing docs for:

- what can cause slashing
- what causes missed rewards but not slashing
- what happens if a validator goes offline
- what happens during restart or upgrade
- how jailing, blacklisting, and tombstoning differ if implemented
- known risky misconfigurations
- safe recovery steps

This should link back to staking and slashing contract behavior as it matures.

### Public Validator Presence

Before encouraging external validators to join, DIN should be able to show that at least one other validator is publicly online.

This can be satisfied by:

- a public status page
- explorer/indexer view
- documented devnet validator addresses
- signed operator announcement

The goal is to avoid asking early validators to join an empty or opaque network.

## Phased Implementation

### Phase 1: Devnet Operator Baseline

- Add Docker Compose for local validator operation. — **Status (2026-06):** Addressed for devnet by `din-node` — see `dincli/docker/node/` (PR #12).
- Document start, stop, upgrade, logs, and volume cleanup. — **Status (2026-06):** Covered by `dincli/docker/node/README.md`.
- Replace plaintext private-key guidance with passphrase-protected keystore guidance. — **Scheduled:** P3 WP 0.2 (July 6–10, 2026).
- Implement graceful SIGTERM handling for validator services. — **Scheduled:** P3 WP 0.2 (July 6–10, 2026).
- Publish initial resource guidance for aggregator and auditor roles. — **Scheduled:** P3 WP 0.2 (July 6–10, 2026).
- Add a basic slashing and failure-mode document. — **Scheduled:** P3 WP 4.3 (July 6–10, 2026).

### Phase 2: Daemon Operations

- Add `/health` for `dind`.
- Add structured stdout logging in daemon/container mode.
- Add graceful `SIGTERM` handling.
- Add `systemd` and `launchd` examples.
- Add local preflight checks before registration or assignment acceptance.

### Phase 3: Hardened Validator Operations

- Add vault or remote-signer integration options.
- Add stronger network isolation profiles.
- Add resource usage reporting per job.
- Add public validator status visibility.
- Add upgrade playbooks and rollback guidance.

## Related Issues

- [Containerization and Sandboxed Execution](containerization.md)
- [Staking Infrastructure](staking-mechanism.md)
- [Validator Selection and Capability Matching](validator_selection.md)
- [Validator Reward Mechanism](validator-reward-mechanism.md)

## Recommended Near-Term Decision

Start with the operator basics that unblock trust:

- Docker Compose run path
- no plaintext private-key recommendation
- resource ceiling documentation
- graceful shutdown behavior
- initial slashing and known-failure-mode docs

Health endpoints, structured logs, service-manager units, and public validator status can follow shortly after, but they should remain visible roadmap items rather than being left implicit.
