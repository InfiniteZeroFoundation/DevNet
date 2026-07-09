---
title: "Should DIN add Filecoin storage support?"
date: 2026-06-30
status: open
participants:
  - Umer Majeed (Principal Engineer)
  - Abraham Nash (Protocol Founder)

related-issue: Developer/issues/filecoin-integration.md
decision-target: P3 fee design (before August 2026)
---

## Background

DIN currently uses Filebase as its default IPFS pinning provider — a centralised S3-compatible service that wraps IPFS. All model artifacts (client updates, aggregated models, manifests, service files) flow through `dincli/services/ipfs.py` and are referenced on-chain by CID. The contract layer is already provider-agnostic; the coupling is entirely operational.

This discussion evaluates whether and when to add Filecoin-backed storage support, and what the practical architecture should look like.

## Should we add it?

**Yes — but not immediately as the primary path.**

Filecoin is the right long-term storage layer for DIN. The philosophical alignment is strong: a trust-minimised ML coordination network should not depend on a centralised IPFS pinning vendor. Filebase should remain the development default while Filecoin-backed support is designed and phased in alongside P3 fee work.

The question is not *whether* but *how* and *when*.

---

## Why Filecoin is the right fit

### Structural fit with DIN's architecture

DIN already treats all artifacts as IPFS CIDs — at the contract layer, nothing references Filebase directly. This is the critical architectural advantage: adding a Filecoin-backed provider requires only an adapter in `dincli/services/ipfs.py` using the existing `custom` provider path. No contract changes, no CID format changes.

### Storage properties match DIN's artifact characteristics

| Property | Filecoin | Filebase |
|---|---|---|
| Decentralised providers | Yes | No — single vendor |
| Cryptographic storage proof | Yes (PoRep + PoST) | No |
| Configurable storage duration | Yes — deal lifecycle | No |
| Write-once, read-occasionally | Excellent fit | Works but over-engineered for permanency |
| Single point of failure | No | Yes |
| Trustless | Yes | No |

DIN's model weight updates are write-once, content-addressed, and referenced across multiple training rounds. Permanency and auditability matter more than ultra-low read latency. Filecoin is structurally better for this workload than a centralised pin service.

### Cost is negligible

At roughly **$0.19 per TB per month**, Filecoin is the cheapest decentralised storage option available.

Estimate for a typical DIN training round:
- 100 validators × 10MB updates = 1GB per round
- Storage cost ≈ **$0.0002 per round**

At this scale, Filecoin storage costs are effectively a rounding error within any network fee structure. They can be absorbed into model-owner task fees without being a meaningful burden.

### Alignment with InfiniteZero's decentralisation goal

A production DIN should not have a centralised infrastructure dependency at the storage layer. Filebase is fine for development and early devnet. It is not acceptable as a long-term dependency for a network that makes trustlessness a core property.

---

## Blockers

### 1. Retrieval latency

Filecoin retrieval can be slower than Filebase, particularly for data not served by a fast retrieval gateway. This matters during aggregation when an aggregator fetches client model updates.

**Mitigation:** Use a Filecoin-backed service that includes a fast IPFS retrieval gateway (Lighthouse, Web3.Storage, Storacha all provide this). The storage layer is Filecoin; the retrieval layer uses IPFS gateway infrastructure with acceptable latency.

### 2. Upload credential model

The current Filebase path assumes a single API key held by the operator. In a decentralised setting, clients and aggregators need to upload artifacts without seeing a raw billing credential. This is the most significant design challenge — see the sponsored upload section below.

### 3. Deal lifecycle complexity

Direct Filecoin integration requires managing storage deal state, deal renewal, and provider selection. This is non-trivial to operate.

**Mitigation:** Avoid raw Filecoin deal management entirely. Use a managed Filecoin-backed pinning service (Lighthouse, Storacha) that handles deal orchestration behind an API. DIN gets Filecoin's storage guarantees without managing deals directly.

### 4. Timing relative to P3

The sponsored upload architecture (see below) requires on-chain storage budget accounting and fee routing. That work belongs in P3 tokenomics. Implementing Filecoin storage before the fee model exists means the economic layer is incomplete. The right sequence is:

1. Add the Filecoin provider adapter (can be done now via `custom` path)
2. Design the sponsored upload flow in P3 alongside fee routing
3. Extend contracts for per-task storage budget in P3 or P4

---

## Best Filecoin-backed providers

Three services offer Filecoin-backed storage with IPFS-compatible APIs that would slot into DIN's existing `custom` provider path with minimal friction:

### Lighthouse
- Filecoin storage with fast IPFS retrieval via gateway
- Supports end-to-end encryption for stored files
- Simple SDK and REST API
- Per-account billing; no raw FIL management required
- **Strong candidate** for DIN's first Filecoin integration

### Web3.Storage / Storacha
- W3C UCAN-based delegated upload capabilities natively supported
- UCAN delegation is precisely the scoped credential model DIN needs for sponsored uploads (see below)
- Multi-provider Filecoin storage
- **Strongest fit** for the sponsored upload architecture because delegated upload permissions are a first-class protocol primitive, not a custom workaround

### Filebase (Filecoin bucket option)
- Filebase offers a Filecoin-backed storage option alongside its IPFS pin option
- Zero migration friction — same API, same credential model
- Less decentralised than Lighthouse or Storacha (Filebase is still the intermediary)
- **Lowest-risk migration path** if the goal is just switching the backing layer without changing operational model

**Recommendation:** Lighthouse for a clean provider swap; Storacha/Web3.Storage if delegated upload capabilities are a P3 priority.

---

## Model-owner API credits and per-model usage budgets

This is both feasible and the correct design direction. The core idea: the model owner funds a storage allocation for a task, and DIN mediates upload access without distributing the model owner's billing credential.

### How it would work

**1. Model owner funds storage at task creation**

When a model owner creates a task (calls `DINTaskCoordinator`), they include a storage budget as part of the task fee. A portion of the network fee is earmarked for storage spend for that task's lifetime.

This could be:
- a fixed per-round allocation
- a total per-task cap
- dynamically priced based on expected client count and model size

The storage budget is held by the protocol (in DIN token or ETH) and is drawn down as artifacts are accepted.

**2. DIN issues scoped upload credentials, not raw API keys**

Clients and aggregators receive short-lived, task-scoped upload authorisations from a DIN-controlled broker or delegated capability layer — not the model owner's storage API key.

Each authorisation is bound to:
- `modelId`
- participant role (client / aggregator / auditor)
- round index
- maximum file size
- artifact type (local model, aggregated model, audit dataset)
- expiration timestamp

**3. Upload is brokered, not direct**

Uploads are routed through a DIN upload broker that:
- validates the scoped credential
- checks quota and round validity
- forwards to the Filecoin-backed provider
- records the CID, uploader, artifact type, size, and timestamp

If using Storacha/Web3.Storage, UCAN delegation handles this natively: the model owner's account delegates a scoped upload capability to the broker, which sub-delegates to participants. No custom broker service is needed for the credential flow.

**4. Storage spend settles only for accepted artifacts**

An upload does not consume storage budget until the protocol accepts the artifact as structurally valid (submitted within the round window, within size limits, correct artifact type). Garbage uploads or expired-round submissions are rejected before becoming billable.

This requires:
- acceptance gating in `DINTaskCoordinator` or a new storage accounting contract
- events for accepted artifact storage spend
- indexer visibility for per-task storage usage

---

## Abuse prevention

If third parties can upload against a model owner's storage budget, explicit controls are required.

### Protocol-level controls

| Control | Purpose |
|---|---|
| Per-task storage budget cap | Hard limit on total spend per task |
| Per-round upload count cap | Prevent flooding a single round |
| Per-role quotas | Clients cannot upload aggregator-sized artifacts |
| Maximum object size | Reject oversized uploads before storage is consumed |
| Short-lived upload authorisations | Expired tokens cannot be replayed |
| One authorisation per expected artifact | Each round produces one known upload per participant |
| Round-bound permissions | Closed rounds cannot generate new billable uploads |
| Content-type checks | Reject obviously wrong file types |
| Acceptance gating | Invalid uploads do not settle against sponsor funds |
| Indexer visibility | All sponsored uploads and rejections are auditable |

### Economic deterrence (P4 or later)

- Require stake from participants before they can consume sponsored storage
- Slash or penalise repeated invalid or oversized submissions
- Rate-limit upload authorisation issuance for new or unverified participants

---

## Recommended implementation sequence

### Now (P3 — can start independently)
- Add a Lighthouse or Storacha provider adapter behind `dincli/services/ipfs.py` using the existing `custom` provider path
- This enables Filecoin-backed storage for operators who configure it, with no contract changes

### P3 fee design (before August 2026)
- Design per-task storage budget as a line item in the task creation fee
- Design the sponsored upload credential flow (UCAN delegation via Storacha, or a lightweight DIN broker)
- Add upload acceptance gating logic to `DINTaskCoordinator`

### P3/P4 boundary
- Add on-chain storage accounting: per-task budget fields, storage spend events, accepted-artifact settlement
- Indexer support for storage usage dashboards
- Economic deterrence controls for upload-capable participants

---

## Open questions

1. Which provider first — Lighthouse (simpler) or Storacha (native UCAN delegation)?
2. Should the storage broker be an off-chain DIN-operated service initially, with on-chain accounting added in P4?
3. What is the minimum per-task storage budget, and how is it priced relative to expected model size and round count?
4. Should audit datasets require Filecoin storage, or is short-lived IPFS pinning sufficient for the auditor path?
5. Which artifacts truly need long-lived durable storage vs. short-lived retrieval availability?

---

## Summary

| Question | Answer |
|---|---|
| Should DIN add Filecoin support? | Yes — it is the correct long-term storage layer |
| When? | Adapter now; sponsored upload in P3 fee design |
| Primary blocker? | Sponsored upload credential architecture, not technical integration |
| Best provider? | Storacha for UCAN delegation; Lighthouse for simplicity |
| Can model owner pay per model? | Yes — per-task storage budget funded at task creation |
| Can abuse be prevented? | Yes — through scoped credentials, quotas, acceptance gating, and economic controls |
| Contract changes required? | Not for provider swap; yes for per-task budget accounting (P3/P4) |
