# P3 Push-Start: Mechanism Design Plan

**Status:** Active — this is the coordination page for the P3 design push (opened July 19, 2026)
**Owner:** Umer
**GitHub tracking:** [issue #36](https://github.com/InfiniteZeroFoundation/DevNet/issues/36) · [project board 6](https://github.com/orgs/InfiniteZeroFoundation/projects/6)

## Why this document exists

P4 (din-dao, din-sdk, din-daemon, din-indexer — [board 7](https://github.com/orgs/InfiniteZeroFoundation/projects/7)) is the currently active phase, but **P3, the cryptoeconomic layer, is delayed because finalized designs for its mechanisms do not exist yet**. The design *material* exists — [MECHANISM_DESIGN.md](MECHANISM_DESIGN.md), the [white paper summary](whitepaper-summary.md), and the per-mechanism write-ups in [`../issues/`](../issues/) — but the open decisions are unresolved and none of it was tracked on GitHub. This page maps every P3 mechanism to its design sources, its GitHub issue, and the decisions blocking it, so the designs can be closed out and P3 can start.

**Rule:** a mechanism's contract/implementation work starts only after its design is agreed — open decisions closed, discussion threads resolved, and the outcome recorded back into [MECHANISM_DESIGN.md](MECHANISM_DESIGN.md).

## Mechanism map

| Mechanism | Design sources | GitHub issue | Roadmap anchors |
|---|---|---|---|
| **Staking** | **[staking-design.md](staking-design.md)** (entry point) · [MECHANISM_DESIGN §3](MECHANISM_DESIGN.md) · [issues/staking-mechanism.md](../issues/staking-mechanism.md) · [suggested-staking-mechanism.md](suggested-staking-mechanism.md) · current state: [technical/mechanisms/staking-mechanism.md](../../Documentation/technical/mechanisms/staking-mechanism.md) | [#37](https://github.com/InfiniteZeroFoundation/DevNet/issues/37) | P3-5.1, P3-DOC2 |
| **Slashing** | [MECHANISM_DESIGN §4](MECHANISM_DESIGN.md) · [whitepaper-summary §4.5](whitepaper-summary.md) | [#38](https://github.com/InfiniteZeroFoundation/DevNet/issues/38) | P3-4.1/4.2/4.3, P3-DOC3 |
| **Scoring** | [MECHANISM_DESIGN §6](MECHANISM_DESIGN.md) · [issues/scoring-mechanism.md](../issues/scoring-mechanism.md) · [rejected-ideas/tknn-shapley.md](../rejected-ideas/tknn-shapley.md) | [#39](https://github.com/InfiniteZeroFoundation/DevNet/issues/39) | P3-SCR (WP 2.2 shipped) |
| **Auditing** | [issues/auditor-evaluation-mechanism.md](../issues/auditor-evaluation-mechanism.md) · [MECHANISM_DESIGN §6](MECHANISM_DESIGN.md) · [whitepaper-summary §4.4](whitepaper-summary.md) | [#40](https://github.com/InfiniteZeroFoundation/DevNet/issues/40) | P3-4.1, P3-SCR, P3-6.2 |
| **Rewards** | [MECHANISM_DESIGN §5](MECHANISM_DESIGN.md) · [issues/client-reward-mechanism.md](../issues/client-reward-mechanism.md) · [issues/validator-reward-mechanism.md](../issues/validator-reward-mechanism.md) | [#41](https://github.com/InfiniteZeroFoundation/DevNet/issues/41) | WP 3.1/3.2, P3-5.1/5.2 |
| **Tokenomics** | **[tokenomics-design.md](tokenomics-design.md)** (entry point) · [MECHANISM_DESIGN §7](MECHANISM_DESIGN.md) · [issues/tokenomics.md](../issues/tokenomics.md) | [#42](https://github.com/InfiniteZeroFoundation/DevNet/issues/42) | P3-5.1/5.2, P3-DOC5 |
| **Fees & treasury** | [MECHANISM_DESIGN §8](MECHANISM_DESIGN.md) · [issues/tokenomics.md](../issues/tokenomics.md) | [#43](https://github.com/InfiniteZeroFoundation/DevNet/issues/43) | P3-5.3, RES-1 |

Related backlog not opened as GitHub issues yet: [issues/validator_selection.md](../issues/validator_selection.md) (capability-aware selection), [issues/decentralized-governance.md](../issues/decentralized-governance.md) (full DAO migration — P3 ships `onlyOwner` governance hooks only; ties into din-dao).

## Open decisions → where they are being discussed

The consolidated list is [MECHANISM_DESIGN §9](MECHANISM_DESIGN.md). The protocol-shaping subset is open on GitHub Discussions with @abrahamnash cc'd:

| Discussion | Covers (§9 decision numbers) |
|---|---|
| [#44 — Slashing economics](https://github.com/InfiniteZeroFoundation/DevNet/discussions/44) | Slashed-stake destination (1), partial-slash fraction & S3 threshold (2), dispute bond & window (7), white-paper §8.1 delegator/removal semantics |
| [#45 — Tokenomics](https://github.com/InfiniteZeroFoundation/DevNet/discussions/45) | Emission shape & MAX_SUPPLY (5), fee denomination (4), `depositAndMint` retirement (8), burn/public-goods routing |
| [#46 — White paper ↔ DevNet alignment](https://github.com/InfiniteZeroFoundation/DevNet/discussions/46) | Delegation scope, encrypted test data & key mapping, test-set resampling, commit-then-reveal, non-coin voting (whitepaper-summary §8 gap items 1–2, 5–7, 9, 11, 13) |

**Status update (2026-07-21):** all three discussions are **resolved in substance** — Abraham answered every open item above via Slack rather than in-thread. The GitHub Discussion threads themselves still show zero comments; posting Abraham's answers publicly is a separate decision that hasn't been made yet, so treat the threads as formally open until that happens even though the underlying decisions are settled. Outcomes are recorded back into [MECHANISM_DESIGN §9](MECHANISM_DESIGN.md#9-consolidated-open-decision-list), [staking-design.md §5](staking-design.md), and [tokenomics-design.md §6](tokenomics-design.md).

Decisions that stay internal (simulation-driven, no discussion needed): reward split percentages (3, P3-5.2 simulation) and per-model stake bounds (6, P3-5.1).

## White paper alignment

[whitepaper-summary.md](whitepaper-summary.md) §8 is the gap/alignment checklist against the canonical [white paper](https://github.com/InfiniteZeroFoundation/White-Paper). Routing of its 14 items: 1–2 → documentation/verification tasks; 3–4 → #38; 5–6, 11 → #40; 7 → #37 + discussion #46; 8 → #42; 9 → #46 + din-dao; 10 → P4 `dind` design (P3-DOC7); 12–13 → future-phase notes; 14 → already aligned.

## Definition of done

- [ ] Each child issue has an agreed design; decisions recorded back into [MECHANISM_DESIGN.md](MECHANISM_DESIGN.md) — most of §9 is now resolved (see status update above), but reward split %, per-model stake bounds, and dispute bond size/window are still open
- [ ] Discussions #44/#45/#46 resolved — decided in substance via Slack (2026-07-21), but **not yet checked off**: the GitHub threads themselves have zero comments and posting the answers publicly is a separate pending decision. Don't mark this done until the threads reflect it.
- [ ] Issues on [project board 6](https://github.com/orgs/InfiniteZeroFoundation/projects/6) with owners
- [ ] Mechanism spec frozen → contract work starts (P3-4.x, P3-5.x), audit prep per P3-6.3b
