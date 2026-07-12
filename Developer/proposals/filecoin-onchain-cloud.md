# Filecoin Onchain Cloud (FOC) Integration Guide

FOC is the Filecoin ecosystem's native cloud layer — verifiable storage, retrieval, and payments running through smart contracts (the Synapse SDK + Filecoin Warm Storage Service) rather than a company's backend. It launched on testnet November 18, 2025, and on mainnet January 31, 2026.

This guide leads with **Filecoin Pin** — the `filecoin-pin` CLI/library, an IPFS-persistence layer built on top of FOC's core Synapse SDK — since it's the closer match to how `dincli` already thinks about storage (CID-referenced artifacts, CI/CD-friendly), rather than the lower-level Synapse SDK directly. Same three-part structure as the Storacha guide, since that's what's being replaced: Web UI, CLI, Authentication.

## 1. Web — setting up access and managing data

There's no account/email/console model the way Storacha has one. "Setting up an account" here means: get a wallet, fund it, and everything else happens through the CLI or SDK talking directly to the contracts. The web surfaces that do exist are narrower and split by purpose:

- **A demo upload site** (`pin.filecoin.cloud`) exists for trying Filecoin Pin in the browser, but per Filecoin Pin's own glossary it runs on "a hardcoded wallet and session key on the Calibration network" — a shared demo credential, not your own. For kicking the tires only, not real usage.
- **`filecoin.cloud/service-providers`** — directory of storage providers with live performance stats, if you want to pick one manually instead of letting the SDK auto-select (auto-select is the recommended default).
- **PDP Explorer** (`https://pdp.vxb.ai/calibration/dataset/{datasetID}` on testnet) — proof-status viewer for a given Data Set: confirms your storage provider hasn't faulted on its onchain proofs. Closest thing to a "view my files" page, except it shows cryptographic proof state, not a file browser. `filecoin-pin data-set <id>` (or its alias `filecoin-pin dataset show <id>`) is the CLI equivalent, querying the chain directly rather than a cache.
- **No general management console exists yet.** Filecoin Pin's own README lists this as "Planned" (tracked in [issue #74](https://github.com/filecoin-project/filecoin-pin/issues/74)). Right now it's CLI/Explorer only — worth knowing if anyone on the team expects a GUI.

### Setting up access (the actual "account setup" step)

```bash
# Node.js 24+ required
node --version

npm install -g filecoin-pin
filecoin-pin --version
```

Then get a wallet and fund it:

- **Calibration testnet** (for testing — data isn't permanent, infra resets regularly): fund with [test FIL](https://faucet.calibnet.chainsafe-fil.io/funds.html) (gas) and [test USDFC](https://forest-explorer.chainsafe.dev/faucet/calibnet_usdfc) (storage payments, a stablecoin).
- **Mainnet** (real usage): fund the wallet with real FIL and USDFC.

**Important, and the opposite of what an earlier pass at this research assumed: the CLI defaults to Mainnet.** `filecoin-pin add myfile.txt` with no flags spends real money. Pass `--network calibration` explicitly to test first. This is worth being deliberate about — there's no "safe by default" here the way Storacha's free tier was.

## 2. CLI — upload/retrieve workflow

```bash
# 1. One-time payment setup — approves the Warm Storage contract and seeds a
#    USDFC deposit sized from current on-chain pricing.
filecoin-pin payments setup --auto --network calibration

# 2. Upload (defaults to 2 storage-provider copies for redundancy; --copies <n> to change)
filecoin-pin add ./local-model.bin --network calibration
```

Output:
```
Root CID: bafybeibh422kjvgfmymx6nr7jandwngrown6ywomk4vplayl4de2x553t4
Piece CID: bafkzcibcfab4grpgq6e6rva4kfuxfcvibdzx3kn2jdw6q3zqgwt5cou7j6k4wfq
Transaction: 0xc85e49d2ed745cc8c5d7115e7c45a1243ec25da7e73e224a744887783afea42b
```

Two CIDs, and the distinction matters:
- **Root CID** — the actual IPFS content identifier. What you'd reference on-chain and what any IPFS gateway/tool retrieves by.
- **Piece CID** — Filecoin's cryptographic commitment for the whole stored CAR file. Not for retrieval; it's what storage providers get proof-challenged on. `/piece` on a provider's endpoint returns the exact stored bytes; `/ipfs` (the same trustless-gateway protocol public gateways use) resolves by Root CID.

Directories work the same way (`filecoin-pin add ./my-data/`). Multiple uploads under one payment configuration group into a **Data Set**, each file a numbered **Piece** inside it.

There's also `filecoin-pin import ./archive.car` for uploading a pre-built CAR directly instead of packing a path.

### Retrieve

```bash
curl https://<Root CID>.ipfs.dweb.link/
# or, in a browser: https://inbrowser.link/ipfs/<Root CID>
#   (dweb.link/ipfs.io now redirect browser navigations to inbrowser.link,
#   a verifiable Service Worker gateway that checks blocks against the CID
#   client-side before rendering; curl and other non-browser clients are
#   served directly by dweb.link)
```

No credentials needed to read — matches the retrieval requirement that ruled out Lighthouse. One real difference from "instant": **retrieval only works once IPNI (their content-routing indexer) has propagated the advertisement.** The CLI itself waits for this before it prints the retrieval URL, so you won't get a CID back that isn't yet fetchable — but it means "upload returns" and "third party can fetch it" aren't the exact same instant, worth knowing for round-timing assumptions. `filecoin-pin`'s own content-routing FAQ describes indexer propagation in the seconds-to-low-minutes range for index updates.

By default, retrieval is CDN-accelerated through **FilBeam** (`--egress-provider beam`, the CLI default — `none` is the other option), with egress cost drawn from the *uploader's* lockup, not charged to the reader. That's the "model owner pays, readers don't" property directly, out of the box, without needing a separate paid tier the way Storacha needed Forge for it.

## 3. Authentication — wallet keys and Session Keys, not accounts or UCANs

No account system: identity is your wallet (private key). But there's a real delegation mechanism here too, closer to Storacha's UCAN model than it might first look — **Session Keys**, registered on-chain in a Session Key Registry and used by the Filecoin Warm Storage Service as an alternative to signing every operation with the owner's raw key.

A session key:
- has **scoped permissions** (e.g. `CREATE_DATA_SET`, `ADD_PIECES` — explicitly *not* fund transfer)
- has an **expiration** (`--validity-days`, default 10, max 365)
- is **revocable** by the wallet owner before expiry

That's a genuinely close parallel to a Storacha UCAN delegation: a narrow, time-boxed, revocable capability grant to a different keypair, rather than handing out the account's full authority.

### The pattern for a backend/CI environment

Two-party flow, mirroring Storacha's "generate a key locally, get it delegated" shape:

```bash
# On the CI/consumer side — generate a keypair locally, no chain interaction:
filecoin-pin session generate
# → outputs a session address + private key

# Send the session address to whoever owns the wallet/funds. They run, on their machine:
filecoin-pin session authorize <session-address> --validity-days 30

# Back in CI, use the session key instead of the owner's raw private key:
export WALLET_ADDRESS=0x...      # the owner's wallet
export SESSION_KEY=0x...         # the session key generated above
filecoin-pin add ./artifact.bin --network calibration
# (or --wallet-address / --session-key flags instead of env vars)

# Revoke when done / if it leaks:
filecoin-pin session revoke <session-address>
```

There's also a single-party shortcut (`filecoin-pin session create`) if the same party both generates and authorizes the key — less relevant for a backend/CI split where the CI environment shouldn't hold owner-level authority in the first place.

**This materially changes the risk picture from a raw private key.** Using `PRIVATE_KEY` directly in CI means a leak drains whatever's in that wallet, full stop. Using a session key means a leak is bounded: scoped to storage operations, time-limited, and revocable — much closer to the blast radius of a leaked Storacha delegation than "leaked wallet key," as long as session keys are actually used instead of the raw key.

### Official CI/CD support: GitHub Action

```yaml
- name: Upload to Filecoin
  # Pin to a release tag or commit SHA for production — floating @v1 tags
  # are not maintained, and @master tracks whatever's newest.
  uses: filecoin-project/filecoin-pin/upload-action@v1.1.0
  with:
    path: dist
    walletPrivateKey: ${{ secrets.FILECOIN_WALLET_KEY }}
    network: calibration
    minRunwayDays: 30      # security checklist: always hardcode this
    maxBalance: "100"      # and this, in trusted workflows
```

The action's own security checklist (worth taking as seriously as it's presented — it's specific, not boilerplate):
- Pin to a version tag or commit SHA, not `@master`, for production.
- Always hardcode `minRunwayDays` and `maxBalance` in trusted workflows.
- Never use `pull_request_target`; use the documented two-workflow pattern instead.
- Consider GitHub Environments with required manual approval before a workflow can make deposits.
- Fork PRs are blocked entirely by design (rejected before wallet input validation) specifically to prevent non-maintainer PR actors from draining funds.

Note the Action's `walletPrivateKey` input is exactly that — a raw private key, not a session key (the Action doesn't currently expose the session-key flow). So the Action's own checklist about a dedicated, minimally-funded CI wallet matters more here than it would if session keys were an option at that layer; the session-key delegation pattern above is CLI-only for now.

Telemetry is on by default (`FILECOIN_PIN_TELEMETRY_DISABLED=true` or the standard `DO_NOT_TRACK=1` to opt out) — no PII collected per their docs, but per-upload outcome metrics are sent to a third-party ingestion endpoint by default, worth a policy check before this runs in DIN's CI.

## What this means for `dincli`

The genuinely good find here: **`filecoin-pin` implements the standard [IPFS Pinning Service API specification](https://ipfs.github.io/pinning-services-api-spec/)** directly — confirmed from the repo's own description ("IPFS Pinning Service API implementation that pins to Filecoin's PDP service"), not just inferred. That's the same API shape Filebase-style adapters are typically built against.

```bash
filecoin-pin server
# runs a localhost IPFS Pinning Service API server backed by Filecoin PDP
```

If `dincli`'s existing Filebase adapter in `ipfs.py` really does speak that standard API, pointing it at a locally-run `filecoin-pin server` could be closer to a config change than a rewrite — worth checking the adapter code against the spec before assuming a full rewrite. That said, don't lean on this for production yet: the server mode is explicitly labeled **Beta, not intended for production use** in Filecoin Pin's own README, with specifics that go beyond "less tested" —
- **state is held in memory and lost on restart** (no persistence across a crash/redeploy)
- no enforced rate limits, per-user quotas, max DAG size, or concurrency caps — a single caller can exhaust disk/CPU/network with one oversized CID
- requires a bearer token (`ACCESS_TOKEN`) on every request; running with `ALLOW_NO_AUTH=true` outside local dev isn't recommended
- `delegates` in pin responses is always empty (each pin spins up a short-lived Helia node, stopped when the pin finishes — no long-lived node to advertise)

The CLI, GitHub Action, and JS library are all separately labeled **production-ready** in the same README — it's specifically the server/daemon affordance that isn't there yet. For a first integration, driving the CLI directly (or the JS library, which is what powers the CLI) is the safer path; treat `filecoin-pin server` as a promising shortcut to revisit once it's out of beta, not something to point at DIN's real round artifacts today.

## Sources

- https://github.com/filecoin-project/filecoin-pin — canonical repo (README, `src/` command source, `documentation/` — retrieval.md, content-routing-faq.md, glossary.md)
- https://github.com/filecoin-project/filecoin-pin/tree/master/upload-action — GitHub Action README (security checklist, versioning, egress-provider default)
- https://registry.npmjs.org/filecoin-pin — package metadata (confirmed active: v1.1.1, published 2026-06-26, 41 versions)
- https://filecoin.io/blog/posts/introducing-filecoin-onchain-cloud-verifiable-developer-owned-infrastructure/ — FOC launch (testnet, Nov 18 2025)
