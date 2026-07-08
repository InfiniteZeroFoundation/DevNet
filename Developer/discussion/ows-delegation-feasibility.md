# OWS (Open Wallet Standard) delegation — feasibility spike

**Author:** Santiago Rodriguez Cetran
**Date:** 2026-07-07
**Context:** `task_300626_3` §1c ("OWS integration exploration") · PR #16 review follow-up
**Status:** Hands-on spike complete. Supersedes the earlier desk-research write-up.
**Versions exercised:** `ows` CLI **1.4.2** (`76c8c67`), Python SDK `open-wallet-standard` **1.4.2**
(importable module name: **`ows`**), on Linux x86_64. Note: the bundled agent skill doc is
**v1.3.2** and is stale relative to the 1.4.2 package — this explains two discrepancies below
(import name and vault layout).

---

## Why this exists

The task asked whether `dincli` can use OWS as an account backend — enumerate accounts and
request a **signed transaction without ever handling the raw key** — and what the failure
modes are. The first pass answered from documentation only; the PR #16 review flagged that as
a gap. This document records an actual spike: OWS installed, wallets created and inspected on
disk, a real Optimism Sepolia transaction signed and cryptographically verified.

**Method:** local-verify (no on-chain broadcast, no funds). A signature is proven correct by
recovering the signer address from it — no funds and no private key required.

## Verdict — scoped precisely

- **CONFIRMED:** OWS can sign an EVM (Optimism Sepolia, chainId 11155420) transaction and
  return a signature that recovers to its own account, **without exposing the private key** to
  the caller. `dincli` can enumerate accounts and drive this via CLI subprocess or the
  in-process Python SDK. No daemon required.
- **NOT yet proven (do not ship on this basis):** the stronger production claim — *"`dincli`
  can safely support OWS delegation with a mandatory, scoped signing policy."* The verified
  path is **unscoped local vault signing by wallet name**, which appears to bypass the
  policy/API-key layer entirely, and (see below) is **not even passphrase-gated**. Policy-
  enforced signing (the `key`/`policy` "agent access layer", and any REST/MCP transport) was
  **not exercised**. Until that is tested end-to-end — plus passphrase behavior and adapter
  compatibility — OWS delegation is a **follow-up**, not a production recommendation.

## What OWS is (verified from the running binary + on-disk vault)

`ows` 1.4.2 — a local, multi-chain wallet manager (Rust core). Keys live in an encrypted vault
under `~/.ows/wallets/<uuid>.json` (flat file per wallet; `ows_version: 2`. The v1.3.2 skill
doc's `~/.ows/wallets/<uuid>/wallet.json` layout is stale). **Crypto confirmed by reading the
keystore file directly** (not just docs): `crypto.cipher = "aes-256-gcm"`, `crypto.kdf =
"scrypt"` (cost params in `crypto.kdfparams`; `auth_tag`, `cipherparams`, `ciphertext`
present). One mnemonic derives addresses for 12+ chains via BIP-44.

Access surfaces: **CLI**, **Node SDK** (`@open-wallet-standard/core`), **Python SDK**
(`open-wallet-standard`, PyO3 — Rust core in-process; import as `ows`). Install:
`curl -fsSL https://docs.openwallet.sh/install.sh | bash` (global `npm install -g
@open-wallet-standard/core` also provides the CLI). Command surface:
`wallet {create,import,export,delete,rename,list,info}`, `sign {message,tx,send-tx}`,
`key {create,list,revoke}`, `policy {create,list,show,delete}`, `mnemonic`, `fund`, `pay`
(x402), `config show`.

## The four task questions, answered with evidence

### 1. What interface does OWS expose?
CLI subprocess **and** an in-process Python SDK (`import ows`). Both produced a byte-identical
signature for the same input; no daemon/socket. A `key`/`policy` "agent access layer" with
scoped tokens exists in the command surface but its enforcement path (and any REST/MCP
transport) was **not exercised in this spike**.

### 2. Can `dincli` enumerate accounts?
Yes. `ows wallet list` (CLI) and `ows.list_wallets()` (SDK) return structured data; each wallet
lists per-chain accounts, e.g. `{"chain_id":"eip155:1","address":"0x…","derivation_path":
"m/44'/60'/0'/0/0"}`.

### 3. Can `dincli` request a signed tx without holding the raw key?
Yes (for EVM, unscoped local signing). `ows sign tx --wallet <name> --chain 11155420 --tx
<unsigned>` and `ows.sign_transaction(<name>,"11155420",<unsigned>)` both return a 65-byte
compact signature (`r‖s‖recovery_id`) — **not** an assembled tx, so the caller reassembles it
(or uses `sign send-tx --rpc-url …` to broadcast). Verified two independent ways (recover from
the signing hash via `eth_keys`, and `Account.recover_transaction()` on the reassembled raw
tx): both recover exactly the wallet's own address. See the transcript under **Reproduction**.

### 4. Chain / account mapping (verified)
For EVM, OWS derives **one** secp256k1 account (`m/44'/60'/0'/0/0`) shared across all `eip155:*`
chains, so the enumerated `eip155:1` address **is** the signer for `--chain 11155420`. Proven:
the address recovered from a chainId-11155420 signature equalled the enumerated `eip155:1`
address byte-for-byte. The chainId only affects the signed payload (it is embedded in the tx
bytes). `dincli` would map its network → OWS `--chain <evm-chain-id>` (e.g. `sepolia_op_devnet`
→ `11155420`). Note: `ows config show` ships **no RPC for `eip155:11155420`** — irrelevant for
offline `sign tx` (which `dincli` broadcasts itself via its own `w3`), but `sign send-tx` would
need an explicit `--rpc-url`.

### 5. Failure modes (all exercised)

| Scenario | Observed |
|---|---|
| OWS not installed | exit **127**, `No such file or directory` — clean `FileNotFoundError` for fallback |
| Unknown wallet name | exit **1**, `error: wallet not found: '<name>'` |
| Wrong chain (EVM bytes, `--chain solana`) | exit **1**, cryptic: `invalid transaction: transaction too short for declared signature slots` |
| Malformed tx bytes (`0xdeadbeef`) | ⚠️ exit **0** — **signed blindly** (see caveat 1) |
| Wrong passphrase (via SDK) | `RuntimeError: decryption failed: aead::Error` (clean failure) |
| "OWS not running" | N/A — no daemon; CLI/SDK are one-shot/in-process |

## Passphrase / authentication of local signing — material finding

In v1.4.2 there is **no CLI or env way to create a passphrase-protected wallet**: `ows wallet
create`/`import` expose no passphrase option, and `OWS_PASSPHRASE` at creation was **ignored**
(the resulting wallet signed with no secret and rejected `passphrase="secret"` with
`aead::Error`). Consequences for the verified flow:

- A CLI-created OWS wallet is encrypted at rest but effectively **empty-passphrase**: `ows sign
  tx`/`sign_transaction()` decrypt and sign with **no secret from the caller**. Protection
  reduces to **filesystem permissions on `~/.ows/wallets/`**.
- This is **weaker** than `dincli`'s own encrypted keystore, which *requires* a passphrase to
  decrypt. So the "highest security / dincli never sees the key" framing is only half-true: the
  key isn't exposed to `dincli`, but neither is it passphrase-gated in the path we verified.
- The passphrase param *is* the KDF input (a wrong one fails with `aead::Error`), so a
  passphrase-protected mode presumably exists via some path we did not find — that, plus
  non-interactive credential passing without leaking through args/env/shell history, is
  **untested and part of the follow-up**.

## Security caveats

1. **Blind signing.** `ows sign tx` (EVM) signs arbitrary bytes without validating they decode
   as a well-formed tx (`0xdeadbeef` → exit 0 + signature). The caller owns payload correctness.
2. **Unscoped API keys, and policy enforcement unverified.** `ows key create --name X --wallet
   Y` succeeds with **no `--policy`**, minting a token that can sign anything for that wallet.
   Whether attaching a policy actually blocks a disallowed tx was **not tested** — the verified
   local-signing path does not go through the key/policy layer at all.
3. **Unauthenticated local signing** (see the passphrase section) — filesystem-permission-only
   protection in the verified flow.

## Integration seam (for a future opt-in — larger than a drop-in)

Every signature funnels through `DinContext.account`, used at `dincli/cli/utils.py:881`
(`signed_tx = account.sign_transaction(tx)`) and `dincli/cli/system.py:589`, followed by
`w3.eth.send_raw_transaction(signed_tx.raw_transaction)`. So an `OwsAccount` adapter must be
**eth-account-compatible**, not a thin shim — it has to:

1. expose `.address` (from `list_wallets`, the `eip155:*` account);
2. accept a **web3 transaction dict** (as produced by `contract_function.build_transaction(...)`
   / the ETH-transfer dict), including EIP-1559 fee fields;
3. **serialize** it to unsigned typed (EIP-1559) transaction bytes;
4. call `ows.sign_transaction(...)` to get `r/s/recovery_id`;
5. **reassemble** the signed raw tx (`0x02 || rlp([...,y_parity,r,s])`);
6. return a result object exposing **`.raw_transaction`** (and ideally `.hash`, `.r`, `.s`, `.v`)
   so the existing `send_raw_transaction(signed_tx.raw_transaction)` call sites are unchanged.

Gate on `ows`/`open-wallet-standard` being importable; fall back to the keystore path.

## Recommendation

- **Ship named multi-keystore as the default production path** (merged, self-contained, no
  external dependency, passphrase-gated).
- **Treat OWS delegation as a follow-up, not production-ready as described.** EVM signing
  without key exposure is genuinely feasible and low-integration-cost via the Python SDK — but
  before recommending it for production the follow-up must verify end-to-end: (a) **policy-
  enforced** signing (create a policy, scope an API key to it, confirm a disallowed tx is
  rejected); (b) **passphrase-protected** wallets and non-interactive credential passing without
  leaking secrets; (c) the eth-account-compatible **adapter** above. OWS remains an operator
  tool we should **not vendor** (per the task).
- The `wallet-setup.md` corrections in this PR are independent of that follow-up and land now.

## Reproduction

```
# versions
$ ows --version
ows 1.4.2 (76c8c67)
$ python -m pip install open-wallet-standard        # 1.4.2; import module is `ows`

# create + enumerate (no passphrase prompt)
$ ows wallet create --name ev
  eip155:1 → 0xaDdA6AEe49109DbB1e87Fe4948Cf075df4C68c5B
$ ows wallet list                                    # -> eip155:1 address above

# unsigned EIP-1559 OP-Sepolia tx (chainId 11155420, nonce 0, to …dEaD, value 1e15, empty data/accessList):
UNSIGNED=0x02f083aa37dc80830f4240843b9aca0082520894000000000000000000000000000000000000dead87038d7ea4c6800080c0

$ ows sign tx --wallet ev --chain 11155420 --tx $UNSIGNED
87839cda2ce3434678d591fc7c8dfbc279109013567c9ef153093bc36a5707db685878656e2ba3879874b6a0128f88f3f2744fee3f827b22727d05ab138a1dbd01
# (r‖s‖recovery_id; recovery_id=1)

# verify (no key needed): recover signer from the signing hash and assert == enumerated address
#   eth_keys.Signature(vrs=(1,r,s)).recover_public_key_from_msg_hash(TypedTransaction.from_dict(tx).hash())
# observed -> 0xaDdA6AEe49109DbB1e87Fe4948Cf075df4C68c5B  (== enumerated eip155:1 address)  ✓
```

The unsigned-tx construction uses `eth_account.typed_transactions.TypedTransaction` +
`_unsigned_transaction_serializer` (EIP-1559 fields RLP-encoded, prefixed with `0x02`). Address
values above are from one spike run; the mnemonic is random per `wallet create`, so a fresh run
yields a different address/signature but the same verification (recovered signer == enumerated
`eip155:1` address). Spike wallets and the API key created during testing were deleted
afterward (`ows wallet delete`, `ows key revoke`).
