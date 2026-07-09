# Storacha Integration Guide

Quick reference for how Storacha (rebranded `web3.storage`) works, for wiring into DIN's storage layer. Sourced from `storacha/docs` on GitHub and their live Terms of Service page — the rendered docs site is Cloudflare-gated in a way that blocks some fetchers, so raw GitHub source pages are linked below for anyone hitting the same wall.

## 1. Web UI

- Console: **console.storacha.network**
- First visit prompts for an email address → sends a confirmation link → clicking it lands you on a plan-selection page.
- **A payment method is required to store anything at all, even on the free tier** — it's in their Terms of Service directly: "In order to begin storing files via the Services, you will need to provide us with one or more Payment Methods." No charge expected at DIN's scale, but budget-holders should know this up front rather than get surprised mid-setup.
- Free tier is called **"Mild"** ($0/mo): **5GB storage + 5GB egress**, overage billed at $0.15/GB/month for either. The next tier up, **"Medium"** ($10/mo), is 100GB storage + 100GB egress at $0.05/GB/month overage. (Sourced from a May 2026 snapshot of `storacha.network`'s pricing section via the Wayback Machine — the live pricing page is Cloudflare-gated and my IP is blocked from it. Need to Re-check `storacha.network/#pricing` directly before this goes into a planning doc, since tier pricing is exactly the kind of thing that changes without a changelog entry.)
- One hard limit that *is* documented: the maximum size of a single registered upload is **750GB**. Anything larger may not register properly against your account even if the underlying data does get stored — worth knowing if any DIN artifact (aggregated model, full checkpoint) could ever approach that.
- Spaces (upload namespaces) can be created from the console UI too, but Storacha's own docs recommend the CLI for anything beyond basic account setup — the CLI is the more complete/scriptable surface.
- Plan/billing management: Console → "Plan settings" (view current plan, change plan, update payment method, see invoices).
- Deleting a file from the console removes it from your account's file *listing* only — Storacha's ToS is explicit that you may still be billed for at least 30 days of storage on deleted files, and that IPFS network nodes may retain copies indefinitely regardless. Don't treat "delete" as a compliance/privacy control.

## 2. CLI — upload/retrieve workflow

```bash
npm install -g @storacha/cli

# 1. Login (sends a confirmation-link email, same identity as the web UI)
storacha login you@example.com

# 2. Create a Space — a namespace for uploads, backed by a local keypair (did:key).
#    You'll be shown a recovery phrase once; save it, you need it to confirm space creation.
storacha space create din-artifacts

# 3. Upload
storacha up ./local-model.bin
# ⁂ Stored 1 file
# ⁂ https://storacha.link/ipfs/bafybeiaad.../local-model.bin

# 4. Retrieve — as a genuine third party, no account/credentials needed:
curl -L 'https://storacha.link/ipfs/bafybeiaad.../local-model.bin' -o out.bin
# or any other public IPFS gateway (ipfs.io, dweb.link, etc.) — content is on the
# public IPFS network, not gated behind storacha.link specifically.
# or, with a local IPFS node: ipfs get bafybeiaad.../local-model.bin
```

Notes relevant to DIN:
- `storacha.link`'s own gateway is rate-limited to **200 requests/min per IP** (confirmed in their docs — matches what's already in the Filecoin-storage discussion thread).
- Uploads are wrapped in a directory by default (preserves filename in the gateway URL); `--no-wrap` skips that if we want the CID to point straight at the file — matters if `dincli` is going to reference CIDs directly on-chain without a directory layer in between.
- `storacha up --json` gives machine-readable output (`.root."/"` for the CID) — what a Python adapter should parse instead of scraping stdout.
- **All uploaded data is public by default.** Storacha's ToS states it plainly: "All data uploaded to storacha.network is available to anyone who requests it using the correct CID." This matches how DIN already works — model artifacts are meant to be readable by other participants — but it means a CID functions as a bearer token for that content. Fine here; would not be fine for raw training data, which DIN already keeps off Storacha entirely by design.
- If Storacha ever shuts down or transfers the service, their ToS commits to 30 days' notice by email before termination, specifically to give users time to migrate to their own IPFS node or another pinning service. Worth knowing as a worst-case timeline if this becomes a load-bearing dependency.

## 3. Authentication — UCANs, not static API keys

A genuinely different mental model from a Filebase/Lighthouse-style bearer token.

**Core concepts:**
- **Agent** — a local keypair (Ed25519) that signs requests. Every CLI install / client instance has one.
- **Space** — the upload namespace, also just a keypair (`did:key:...`).
- **Delegation** — a signed UCAN token where one keypair grants specific *capabilities* (e.g. `upload/add`, `space/blob/add`) on a resource to another keypair (the "audience"), without sharing the private key itself. A scoped, signable capability token, not a password.
- **Proof** — the delegation, serialized (base64) so it can travel with an agent that wasn't the one the Space was created by.

There is no static "API key" concept at all — the closest equivalent is: generate an Agent keypair, then delegate it a narrow set of capabilities via a Proof.

### The pattern for a backend/CI environment (no interactive email-click step)

Storacha's docs have a dedicated guide for exactly this (`how-to/ci.mdx`). Two steps, done once, locally/interactively:

```bash
# On your own machine, with the CLI already logged in and a Space selected:

# 1. Generate a new signing key for the backend/CI agent — this becomes its permanent identity.
storacha key create --json > ci-key.json
AUDIENCE=$(jq -r .did ci-key.json)     # the new agent's public DID
KEY=$(jq -r .key ci-key.json)          # its private key — this is the CI secret

# 2. Delegate ONLY the capabilities the backend needs (not full account access):
storacha delegation create $AUDIENCE \
  -c space/blob/add -c space/index/add -c filecoin/offer -c upload/add \
  --base64 > ci-proof.b64
```

Optionally add `--expiration <unix_ts>` to that second command if you want the delegation to lapse on its own rather than stay valid indefinitely — worth considering for anything longer-lived than a one-off CI job, since DIN's rounds are ongoing and rotating credentials shouldn't require hunting down every place a proof got pasted.

Then, in the backend/CI environment (no login, no email click, fully non-interactive):

```bash
npm install -g @storacha/cli   # or @storacha/client for the JS SDK path

export STORACHA_PRINCIPAL="$(cat ci-key.json | jq -r .key)"   # secret: the agent's private key
storacha space add "$(cat ci-proof.b64)"                       # imports the proof
storacha up ./artifact.bin --json                              # uploads, scoped to just those 4 capabilities
```

`STORACHA_PRINCIPAL` and the proof are the two secrets to store (e.g. as CI secrets / env vars) — equivalent in practice to an API key + scope, but cryptographically revocable and narrowly scoped rather than an all-or-nothing account credential.

Revocation note: there's no single "delete this key" button the way there is for a static API key. Two options — let the delegation expire (if `--expiration` was set), or issue a fresh Agent + delegation and stop referencing the old proof anywhere. Didn't dig into the formal on-chain/service-side revocation API for this pass since it wasn't part of the original ask — flag if we need it before this goes to production, since "just stop using it" isn't the same guarantee as actual revocation if the key ever leaks.

**JS/Node equivalent** (for wiring into a Python-adjacent service via a small Node shim, or if `dincli` ever grows a JS-side helper):

```javascript
import * as Client from '@storacha/client'
import { StoreMemory } from '@storacha/client/stores/memory'
import * as Proof from '@storacha/client/proof'
import { Signer } from '@storacha/client/principal/ed25519'

const principal = Signer.parse(process.env.STORACHA_PRINCIPAL)
const client = await Client.create({ principal, store: new StoreMemory() })
const proof = await Proof.parse(process.env.STORACHA_PROOF)
const space = await client.addSpace(proof)
await client.setCurrentSpace(space.did())
// client.uploadFile(...) / client.uploadDirectory(...) from here
```

This is the pattern Storacha's docs recommend for any backend, including non-persistent/serverless environments — as opposed to the email-click login flow, which only really works for a persistent, interactive environment (a human's laptop, a browser session).

### What this means for `dincli`

`dincli`'s current provider adapters (`_upload_via_filebase`, `upload_via_lighthouse` in `dincli/services/ipfs.py` / `ipfs_lighthouse.py`) all follow a "static bearer token in a header" shape. A Storacha adapter needs to diverge from that pattern in two ways:

1. **Credential shape** — ship/generate a per-operator (or per-DIN-broker, depending on how far the sponsored-upload design in the Filecoin-storage discussion goes) Agent key + Proof pair, not a single API key field. This probably means a new config shape in whatever loads provider credentials today, not just a new env var.
2. **No first-party Python UCAN client** — as of this research there's no native Python SDK for the w3up/UCAN protocol, only JS (`@storacha/client`) and the CLI. Practical options: shell out to the `storacha` CLI (simplest, matches the existing pattern of loading an external tool for the `custom` provider path), or vendor the JS client behind a small subprocess bridge. Shelling out to the CLI is probably the lower-effort path for a first pass.

Also worth deciding early, per the role-scoping point above: clients need upload capabilities, but auditors and aggregators reading artifacts back need **no delegation at all**, since retrieval is unauthenticated (see §2). Minting one shared `STORACHA_PRINCIPAL` for every role is the easy path but means a compromised auditor node would also be able to upload/overwrite — worth scoping per-role from the start rather than retrofitting later.

Not attempting the actual adapter code here — this is reference documentation for whoever picks up the integration, per the original ask.

## Sources

- https://github.com/storacha/docs — canonical source (rendered site blocked some fetchers during this research; raw GitHub content worked fine)
- https://docs.storacha.network/terms/ — Terms of Service (payment method requirement, 750GB upload cap, public-data and deletion behavior, 90-day termination notice)
- `src/pages/quickstart.md`, `how-to/create-account.md`, `how-to/create-space.mdx`, `how-to/upload.mdx`, `how-to/retrieve.mdx`, `how-to/ci.mdx`, `how-to/plan.md`, `concepts/ucan.md`