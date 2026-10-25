# Impact and Traction

A snapshot of what InfiniteZero has built, for funders, partners and new contributors. Every figure below can be checked against this repository; see [How to verify](#how-to-verify).

**As of:** 25 October 2026 (`develop` branch). Refresh this page quarterly.

---

## At a glance

| | |
| :--- | :--- |
| **Network** | DevNet 2.0 live on Optimism Sepolia, with validator nodes running 24/7 from Japan to Canada |
| **Working example** | MNIST model trained end to end through full on-chain training rounds |
| **Smart contracts** | 11 contracts covering staking, slashing, rewards, emission, fees and fair-launch distribution |
| **Automated tests** | 500+ Solidity tests and 400+ Python tests, run in CI on every push |
| **Development activity** | 588 commits since April 2025, 369 of them in the last 90 days |
| **Pull requests merged** | 80+, each reviewed by someone other than its author |
| **Code contributors** | 7 GitHub contributors with merged code; the wider team spans 4 continents |
| **Documentation** | 18 participant guides and 55 technical documents |
| **Reach** | Organisation README available in 26 languages |
| **Funding to date** | $50,000 (Edge City SHIFT Grants, Cosmos Institute, University of Oxford) |

---

## Engineering quality

We treat the DevNet as a dress rehearsal for mainnet:

- **Security review** of the smart contracts by a project contributor, with findings fixed or tracked publicly: [`foundry-src-security-review.md`](Documentation/technical/audits/foundry-src-security-review.md).
- **Adversarial threat model** covering Sybil, collusion and other attacks, with each one marked defended or known gap: [`adversarial-threat-model.md`](Developer/design/adversarial-threat-model.md).
- **Privacy review** of the differential-privacy mechanisms by an outside contributor; half the findings are fixed and the rest are tracked as open issues: [`dp-mechanism-review.md`](Documentation/technical/audits/dp-mechanism-review.md).
- **CI gates** on every change: the full Solidity and Python test suites, a contract-size gate, a lint gate and a documentation link check.
- **Two-person rule:** every pull request is reviewed and merged by someone other than its author ([`MAINTAINING.md`](Developer/MAINTAINING.md)).

---

## Recent milestones

- **Cryptoeconomic layer (P3):** staking, slashing tiers and penalties, dispute resolution, a reward engine, fee routing, and a geometric-decay emission schedule, all merged to `develop`.
- **Cross-model penalty escalation (October 2026):** validators can no longer avoid penalties by spreading missed duties across models (#193, merged in #236).
- **Fair-launch distributor contract:** the on-chain foundation for distributing tokens to the people who run the network, with no ICO and no VC allocation.
- **Open contributor programme:** good first issues, a tokenomics open call (#155) and a privacy research call, open to anyone.

See the [roadmap](Developer/ROADMAP.md) for what's next.

---

## Recognition and support

| | |
| :--- | :--- |
| 🎓 **University of Oxford** | Founded in Computer Science, Division of Human-Centered Computing; support and compute |
| 🏅 **Edge City SHIFT Grants** | Developer grant, supported by Vitalik Buterin and co. |
| 🏅 **Cosmos Institute** | Early development grant, supported by Brendan McCord |
| 🎓 **UC Berkeley RDI Summit** | Selected speaker, Summit on Responsible Decentralized Intelligence |
| 🔬 **Decentralized Research Center** | Featured project |

---

## How to verify

From a clone of this repository, on the `develop` branch:

```bash
git rev-list --count HEAD                          # total commits
git rev-list --count --since="90 days ago" HEAD    # recent activity
ls foundry/src/*.sol | wc -l                       # smart contracts
grep -rhoE 'function (test|invariant)[A-Za-z0-9_]*' foundry/test | wc -l   # Solidity tests
grep -rhoE '^\s*def test_[A-Za-z0-9_]*' tests dincli | wc -l             # Python tests
find Documentation/public -name '*.md' | wc -l     # participant guides
find Documentation/technical -name '*.md' | wc -l  # technical documents
```

Merged pull requests and CI results are public on the repository's [Pull requests](https://github.com/InfiniteZeroFoundation/DevNet/pulls?q=is%3Apr+is%3Amerged) and [Actions](https://github.com/InfiniteZeroFoundation/DevNet/actions) tabs.
