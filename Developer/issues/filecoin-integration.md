# Filecoin Integration For Model Artifacts

## Summary

This issue covers whether DIN should move model artifact storage from Filebase to Filecoin-backed storage and what that would require operationally.

Today the system already treats storage artifacts as IPFS CIDs, which is good. However, the default hosted path is still Filebase, which is a third-party centralized provider. That is convenient in early development, but it does not fully match the long-term goal of a decentralized training network.

The key design questions are:

- should DIN keep Filebase as a short-term convenience layer but design for Filecoin long term
- how should Filecoin-backed uploads work in practice for clients, aggregators, and model owners
- can the model owner pay for storage without exposing a raw storage API key to every uploader
- how should DIN prevent abuse if third parties are allowed to upload artifacts against a model owner's storage budget

## Current State

Relevant code paths today:

- `dincli/services/ipfs.py`
  - provider abstraction for `env`, `filebase`, and `custom`
  - upload and retrieval already flow through one shared interface
- `dincli/cli/utils.py`
  - runtime IPFS configuration and Filebase endpoints
- `dincli/services/client.py`
  - client training produces a local artifact and uploads it to IPFS
- `dincli/services/aggregator.py`
  - aggregator retrieves client artifacts and uploads aggregated artifacts
- `dincli/services/auditor.py`
  - auditor retrieves artifacts by CID
- on-chain task flows
  - contracts and CLI submission logic already treat model artifacts as CIDs rather than provider-specific URLs

This is an important architectural advantage. DIN is not deeply coupled to Filebase at the contract layer. The main coupling is operational:

- Filebase is the built-in hosted provider
- Filebase access depends on a long-lived API key in config
- the current default model assumes the same trusted operator controls upload credentials

That trust model is too weak for a production decentralized network where:

- model owners
- clients
- aggregators
- auditors

may all be distinct parties.

## Why Filebase Is Not Enough Long Term

Filebase is useful because:

- it is easy to adopt
- it has an S3-style operator experience
- it provides a simple IPFS-compatible API
- it is fast enough for development and demos

But Filebase also creates long-term concerns:

- it is a centralized service provider
- it is a trust bottleneck and operational dependency
- it is not native Web3 settlement or storage verification
- a compromised or unavailable provider can disrupt artifact availability
- the API key model does not map cleanly to permissionless uploads by untrusted network participants

For DIN, that matters because training artifacts are not just convenience files. They are part of protocol execution and disputeability.

## Why Filecoin Is A Better Long-Term Fit

Filecoin is better aligned with DIN's architecture because it offers:

- decentralized storage providers instead of one hosted operator
- cryptographic storage guarantees rather than trust in one vendor
- configurable storage duration for artifacts that must survive across rounds
- a cleaner philosophical match for a trust-minimized ML coordination network

For DIN-specific workloads, Filecoin is especially attractive because model updates are usually:

- write-once
- content-addressed
- referenced by CID
- relatively small compared with typical archival datasets
- more sensitive to durability and auditability than ultra-low-latency retrieval

## Main Practical Tradeoff

The strongest argument against direct Filecoin adoption is not cost. It is operational behavior.

The main drawbacks are:

- retrieval can be slower than a centralized pinning provider
- deal lifecycle and storage orchestration are more complex
- direct integration usually requires more infrastructure than a single API call
- pinning and retrieval consistency can vary by provider or gateway strategy

That means DIN should not treat "move to Filecoin" as "replace one upload URL with another." The provider model needs to support storage sponsorship, quotas, and upload authorization.

## The Real Design Problem

The hardest question is not whether Filecoin can store DIN artifacts.

It can.

The harder question is:

- how can a model owner pay for storage
- while clients and aggregators upload artifacts
- without leaking the model owner's storage credentials
- and without allowing those uploaders to spam or misuse the storage budget

That is the real production issue.

## Recommended Architecture

DIN should separate:

- who funds storage
- who is allowed to upload
- who verifies the uploaded artifact
- who is allowed to finalize storage spend

The recommended direction is a sponsored upload model, not a shared API key model.

### 1. Storage sponsor

The model owner funds a storage budget for a task or training job.

That budget can eventually come from:

- a task creation fee
- a per-round network fee
- a prepaid storage allowance
- FIL or a service-layer billing account abstracted away from end users

### 2. Upload broker or delegated capability layer

Clients and aggregators should not receive the raw Filecoin service API key.

Instead, DIN should introduce a broker or delegated upload layer that issues short-lived upload permissions scoped to a specific task.

Examples of what that delegated permission should bind to:

- `modelId` 
- stakeholder role such as client or aggregator
- round index
- maximum file size
- artifact type such as local model, aggregated model, or audit dataset
- expiration timestamp
- optional expected content hash or manifest identifier

This can be implemented through:

- a DIN-operated upload broker
- a custom provider adapter behind `dincli/services/ipfs.py`
- provider-native delegated capabilities if the chosen Filecoin-backed service supports them

The important point is that DIN clients receive a scoped upload grant, not the billing secret.

### 3. Verification and accounting

After upload, DIN should record enough metadata to verify that the artifact matches the intended protocol action.

That includes:

- CID
- uploader address
- task identifier
- round index
- artifact type
- size
- timestamp

This metadata can live partly:

- on-chain for minimal canonical references
- off-chain in an indexer or coordinator service for richer auditing

### 4. Settlement

Actual storage spend should be charged against the model owner's task budget only after the upload is accepted as protocol-valid.

That means an upload should not automatically become billable just because someone obtained a temporary token.

Instead, billing should happen only if:

- the upload is within quota
- the artifact type is allowed
- the artifact is submitted during the valid round window
- the protocol accepts the artifact as structurally valid

This avoids paying for obvious garbage uploads.

## How To Prevent Misuse

If DIN allows third parties to upload against a sponsored storage budget, abuse prevention must be explicit.

Recommended controls:

- per-task storage budget caps
- per-round upload count caps
- per-role quotas
- maximum object size limits
- short-lived upload authorizations
- one authorization per expected artifact
- role-bound permissions so a client cannot upload aggregator artifacts
- round-bound permissions so expired rounds cannot continue consuming budget
- content-type and extension checks where useful
- optional hash commitment or manifest commitment before upload
- acceptance gating so invalid uploads do not settle against sponsor funds
- indexer visibility for all sponsored uploads and rejected attempts

For stronger deterrence, DIN can also use protocol-level economic controls:

- require stake or bonded participation for upload-capable actors
- slash or penalize repeated invalid submissions
- rate-limit untrusted participants before they become billable

## Recommended Integration Strategy

DIN should not jump straight from Filebase to direct raw Filecoin integration everywhere.

A staged approach is safer.

### Phase 1: Keep CID abstraction, add Filecoin-backed custom provider

Use the existing `custom` provider path in `dincli/services/ipfs.py` to integrate with:

- Lighthouse
- Web3.Storage
- Storacha
- another Filecoin-backed service

This keeps the contract layer unchanged and limits the first migration to the storage adapter.

### Phase 2: Introduce sponsored uploads

Add a DIN-controlled upload authorization service or delegated capability flow so:

- model owner funds storage
- clients and aggregators upload without seeing the billing credential
- each upload is scoped and auditable

### Phase 3: Add protocol-level storage accounting

Extend task creation or round execution logic so storage is a first-class cost item.

That likely belongs closer to task-level coordination than in the global token minting flow.

In practice this may require:

- per-task storage budget fields
- storage sponsorship events
- accepted-artifact accounting
- indexer support for storage usage dashboards

## Contract Impact

A basic Filecoin-backed migration does not require changing how DIN stores artifacts on-chain, because DIN already passes CIDs around.

The likely contract work is economic and accounting work, not CID-format work.

Potential future additions:

- task-level storage budget configuration
- sponsor address for storage
- events for sponsored upload usage
- limits on billable artifact classes per round
- fee routing so a portion of task fees covers storage

This should probably live in task-level coordination and fee-routing logic rather than overloading `DinCoordinator` directly.

## Recommendation

The practical recommendation is:

- keep Filebase for now as a development default
- design the production architecture around Filecoin-backed storage
- use the existing custom provider abstraction as the migration bridge
- do not distribute long-lived storage API keys to clients or aggregators
- introduce sponsored, short-lived, scoped upload authorization
- treat storage abuse prevention as a protocol concern, not just an infrastructure concern

This gives DIN a credible path from:

- centralized convenience in dev

to:

- decentralized, auditable, sponsor-funded artifact storage in production

without forcing a contract rewrite just to change providers.

## Open Questions

- Which Filecoin-backed service should DIN target first for the custom provider path?
- Does DIN want fast retrieval via a managed gateway, durable storage via Filecoin deals, or both?
- Should storage sponsorship be handled by an off-chain broker first, with on-chain accounting later?
- Which artifacts truly need long-lived durable storage versus short-lived retrieval caching?
- Should rejected or unused uploads ever be billable to the model owner?
- What is the minimum stake or identity requirement before a participant can consume sponsored storage?

## Proposed Outcome

DIN should open follow-up implementation work for:

- a Filecoin-backed custom IPFS provider
- sponsored upload authorization
- storage quota and abuse controls
- fee-model integration for task-funded storage
