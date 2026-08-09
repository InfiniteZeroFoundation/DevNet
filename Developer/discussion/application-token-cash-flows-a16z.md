---
title: "a16z: Application Tokens, Economic Models, and Cash Flows"
date: 2026-08-08
status: reference
participants:
  - Abraham Nash (CEO, white paper author)
  - Robert Carlos (@robertocarlous)
  - Santiago
related-discussion: https://github.com/InfiniteZeroFoundation/DevNet/discussions/73
related-backlog: ../BACK_LOG.md#bl-17
---

## Background

Abraham shared this article with Robert and Santiago as context for DIN's infrastructure and fee-tracing work:

> [Application Tokens: Economic Models and Cash Flows](https://a16zcrypto.com/posts/article/application-tokens-economic-model-cash-flows/) — a16z crypto

This is the piece referenced as "the a16z tokenomics piece Abraham shared" in [BL-17](../BACK_LOG.md#bl-17) (curated per-model staking & fee attribution), and predates Robert's [Discussion #73](https://github.com/InfiniteZeroFoundation/DevNet/discussions/73) follow-up. Kept here as the source-context doc for that discussion thread.

## Article summary

**Central thesis:** application-layer tokens need different economic structures than infrastructure (L1) tokens, because apps are *users*, not *providers*, of block space — an L1 has embedded supply/demand dynamics (gas markets) that an application token doesn't get for free. Application tokens need custom mechanisms to generate and route cash flow.

**Problems identified with naive approaches** (e.g. DAO-controlled treasury paying pro-rata dividends, or simple buy-and-burn):

1. **Governance risk** — a DAO directly controlling and distributing protocol revenue reads as a security/investment contract in more jurisdictions, particularly U.S.-facing.
2. **Value-distribution complexity** — simple dividend or buyback mechanisms trigger securities-law concerns more readily than usage-based or curated mechanisms.
3. **Compliance exposure** — tokenholders can end up passively profiting from frontend/integrator activity that's illicit in some jurisdiction, without any way to opt out of that exposure.

**Proposed framework — fee traceability & curation**, instead of one pooled treasury with pro-rata payout:

- **Frontend registration** — integrating frontends/domains cryptographically register a key pair, so fees can be attributed back to the specific frontend that generated them (not pooled blind).
- **Tiered staking pools** — fees route through pools keyed to a frontend's compliance status, rather than one undifferentiated pool.
- **Curator-based filtering** — independent curators assemble baskets of compliant frontends; tokenholders choose which basket(s) to stake toward, opting into the compliance profile they're willing to hold.

**Core mechanical idea:** this lets a protocol collect fees from activity in any jurisdiction where that activity is legal, without the DAO itself having to adjudicate compliance per-jurisdiction — the curation/staking layer absorbs that judgment call instead of governance.

## Relevance to DIN

This is the framing behind Robert's BL-17 proposal: route validator staking and `DinFeeRouter` fee flows *per-model* (via `DINModelRegistry`, using the `modelMinStakeBounds` storage from the P3 staking work) rather than through one shared network-wide pool. The a16z "frontend → curated pool → tokenholder" structure maps roughly onto a DIN "model → per-model stake → validator" structure — traceable fee attribution instead of a passive, network-average dividend. See [BL-17](../BACK_LOG.md#bl-17) for the concrete proposal and current phase status (P4/P5, undecided).

No open decision is being made in this doc — it's a reference/context capture only. Follow-up design work belongs in Discussion #73 and, once triaged, a `design/` doc.
