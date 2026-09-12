# DIN-SDK — Public Interface & JSON Output Conventions (proposal v0.3)

**Issue:** #20 · **Branch:** `feat/din-sdk` · **Status:** proposal for review (candidate seed for P3-DOC7)

Proposes the public interface and output conventions for `dincli/sdk/`, extracted from the existing
`dincli` code. Concrete before/after from the current code so it can be reviewed against DOC7 and, if
accepted, become its seed. Nothing here is built yet.

> **v0.2** incorporated a code-audit of v0.1: plan/apply as the *default* for irreversible ops;
> wallet/session non-interactive *by contract*; typed amounts stringified only at the JSON boundary;
> `meta` gains `schema_version`/`chain_id`/`correlation_id`; `error.details` sanitization; finer tx/rpc
> subcodes; summary/detail request objects; golden-CLI + import-boundary tests; tx retry-state.
>
> **v0.3** incorporates a second code-audit against real call sites. Changes: `TxReceiptInfo` now
> carries `contract_address` + raw receipt/decoded events (deploy flows read `tx_receipt.contractAddress`;
> registry flows call `process_receipt`); plan/apply for CID-producing ops is a **three-phase**
> prepare→upload→on-chain split (register uploads the manifest mid-flow today, so a "pure" plan can't
> yield a CID); `SignerProvider` given an explicit Protocol; `sanitize_details()` is allowlist-oriented
> (per-code schema); import-boundary test runs in a fresh subprocess; fixed an invalid illustrative
> snippet.

---

## 1. Design principles

1. **Return data, don't print.** SDK functions return dataclasses. Never `console.print`, `rich`
   tables, or stdout.
2. **Raise, don't exit.** SDK functions raise typed domain exceptions (`DinError` subclasses). Never
   `typer.Exit` / `sys.exit`.
3. **Non-interactive by contract.** SDK functions never perform interactive I/O — not `typer.confirm`,
   **and not `getpass()` or any hidden prompt**. A missing password/signer/decision raises (§2, §6)
   rather than blocking on input. This is what makes the SDK safe for `dind`.
4. **JSON-serializable by construction.** Every returned dataclass serializes to the envelope in §3 via
   the shared encoder only (bytes→hex, wei→string, enums→name).
5. **Importable standalone.** `dincli/sdk/` imports without `typer`, `rich`, or any `dincli.cli.*`
   module (enforced by a test — §7). The CLI depends on the SDK, never the reverse.

The CLI keeps its exact current behavior; it becomes a thin layer that calls the SDK, renders the
result, and maps exceptions to exit codes (§7).

---

## 2. The session object

Replaces the runtime-resolution parts of `DinContext`, minus console/exit — and minus prompting.

```python
# dincli/sdk/session.py
class DinSession:
    """Lazily resolves network, web3, account, config. No printing, no exit, no prompts."""
    def __init__(self, network: str | None = None, wallet: str | None = None,
                 signer: SignerProvider | None = None): ...

    @property
    def network(self) -> str: ...
    @property
    def w3(self) -> Web3: ...            # raises NetworkError if RPC unreachable

    @property
    def account(self) -> LocalAccount:
        """Resolve the signing account via the configured SignerProvider.

        NEVER calls getpass or any interactive prompt. Raises SignerUnavailable
        if no non-interactive credential is available, WalletError if the
        keystore is malformed or missing.
        """

    @property
    def config(self) -> dict: ...
```

Today `load_account` can fall back to an interactive `getpass` prompt; the SDK must not. The consumer
supplies the `SignerProvider`: the CLI's adapter *may* prompt; the daemon's is backed by a configured
secret/agent. The SDK core only ever sees the provider result — or a raised error.

```python
# dincli/sdk/session.py — the signing contract (no prompts inside the SDK)
@runtime_checkable
class SignerProvider(Protocol):
    def address(self) -> str: ...
        # checksummed address for this signer; raises SignerUnavailable if none resolvable
    def can_decrypt(self) -> bool: ...
        # True if this provider holds/points to a usable key without further input
    def sign_transaction(self, tx: dict) -> SignedTransaction: ...
        # raises SignerUnavailable (no credential), WalletError (bad keystore/decrypt failure)
```

- **CLI adapter** wraps the existing keystore flow; it *is* allowed to prompt (that's the interactive
  boundary), then hands a resolved signer to the session.
- **Daemon adapter** is backed by a configured password source / signing agent and **must never**
  prompt — on any missing credential it raises `SignerUnavailable`, which the daemon turns into a job
  error rather than a hang.

Contract getters and tx-param building move to `sdk/contracts.py` and `sdk/tx.py`, taking a `DinSession`.

---

## 3. JSON output convention (the contract)

SDK functions **return dataclasses with typed fields** (`int` for wei, `bool`, enums, etc.). The JSON
*envelope* — with amounts stringified — is produced only at the consumer boundary (daemon always; CLI
on `--json`). Python consumers keep numeric ergonomics; JS consumers get precision-safe strings.

```jsonc
{
  "status": "ok",                         // "ok" | "error"
  "data": { /* dataclass, serialized */ },// null on error
  "error": null,                          // null on success; object below on error
  "meta": {
    "schema_version": "din-sdk-envelope/v1",  // bump on breaking envelope changes
    "sdk_version": "0.1.0",
    "network": "sepolia_op_devnet",
    "chain_id": 11155420,
    "correlation_id": "…"                 // optional for CLI, first-class for daemon jobs/logs
  }
}
```

Error shape:

```jsonc
{
  "status": "error",
  "data": null,
  "error": {
    "code": "tx_reverted",                              // stable machine string (§4)
    "message": "T1 aggregation submission reverted",    // human-readable
    "details": { "tx_hash": "0x…", "gi": 3, "nonce": 42 }  // structured, sanitized (§4a)
  },
  "meta": { "schema_version": "din-sdk-envelope/v1", "network": "sepolia_op_devnet", "chain_id": 11155420 }
}
```

**Serialization rules** (shared encoder, `sdk/serialize.py`):
- **Amounts are typed `int` inside SDK dataclasses**; the encoder emits wei/token/`uint256` values as
  decimal **strings** (JS `Number` precision). Fields opt in via metadata, e.g.
  `fee_wei: int = field(metadata={"json": "uint256_string"})`. Small counts (GI number, indices, enum
  ints) stay JSON numbers.
- `bytes` / `HexBytes` → `0x` hex string. Addresses → checksummed string. `Decimal` → string.
- Enums (e.g. GI state) → name string; include the int in `details` where useful.

---

## 4. Exception hierarchy

```python
# dincli/sdk/errors.py
class DinError(Exception):
    code: str                 # stable, machine-readable (goes into error.code)
    def __init__(self, message: str, *, details: dict | None = None): ...

class ConfigError(DinError):          code = "config_error"
class NetworkError(DinError):         code = "network_unreachable"   # rpc subcodes below
class WalletError(DinError):          code = "wallet_error"
class SignerUnavailable(DinError):    code = "signer_unavailable"    # no non-interactive credential (§2)
class ManifestError(DinError):        code = "manifest_error"
class IpfsError(DinError):            code = "ipfs_error"
class ContractError(DinError):        code = "contract_error"
class NotFoundError(DinError):        code = "not_found"
class ValidationError(DinError):      code = "validation_failed"     # e.g. wrong GI/state
class TransactionError(DinError):     code = "tx_failed"             # stable subcodes below
class ConfirmationRequired(DinError): code = "confirmation_required" # see §6
```

**Reserved stable subcodes** (set as `code` on the raised error; daemon retry policy keys off these):
- Transaction: `tx_estimation_failed`, `tx_reverted`, `tx_timeout`, `tx_nonce_conflict`,
  `tx_replacement_underpriced`, `receipt_missing`.
- RPC/network: `rpc_unreachable`.
Contract revert reasons stay optional inside `details`; the top-level `code` must be stable enough to
drive retry decisions on its own.

### 4a. `error.details` sanitization rules

`details` is structured context, never a secret sink — critical once daemon logs are JSON and
long-lived. Sanitization is **allowlist-oriented**, not a generic scrubber (a generic scrubber misses
secrets nested in arbitrary values). Each error `code` declares a **schema of allowed detail keys**,
each with a type and bound; `sanitize_details(code, raw)` drops anything not in that code's allowlist:

- Free-form / unlisted keys are **discarded**, not passed through.
- String values are length-bounded (e.g. revert reasons capped; `stdout`/`stderr` truncated to a
  bounded tail).
- URLs are explicitly sanitized to host + path, stripping any embedded API keys / credentials.
- Never allowlisted anywhere: private keys, wallet passwords, mnemonic/seed material, raw env secrets.

Example: `tx_reverted` allows `{tx_hash: hex, nonce: int, gi: int, reason: str<=256}`; a stray
`raw_signed_tx` or `password` key simply never survives `sanitize_details`.

---

## 5. Function interface patterns — real before/after

### 5a. Reads: compute-and-print → return data (summary vs detail)

**Before** (`dindao.py::list_pending_requests`): loops contracts, `console.print`s each row, returns
nothing; fields by raw tuple index (`req[6]`).

**After** — list endpoints return lightweight *summaries*; single-item lookups return *detail* objects:

```python
# dincli/sdk/registry.py
@dataclass
class ModelRequestSummary:
    request_id: int
    requester: str                 # checksummed address
    open_source: bool
    fee_wei: int = field(metadata={"json": "uint256_string"})
    processed: bool

@dataclass
class ModelRequestDetail(ModelRequestSummary):
    manifest_cid: str | None
    task_coordinator: str | None
    task_auditor: str | None
    approved: bool
    approved_model_id: int | None
    created_at: int | None         # block timestamp if available

@dataclass
class PendingRequests:
    model_requests: list[ModelRequestSummary]
    manifest_requests: list[ManifestUpdateRequestSummary]

def list_pending_requests(session: DinSession, req_type: str | None = None) -> PendingRequests: ...
    # raises ValidationError if req_type not in {None,'model','manifest'}

def get_model_request(session: DinSession, request_id: int) -> ModelRequestDetail: ...
    # raises NotFoundError if absent (replaces explore_request's broad except→Exit)
```

CLI renders the tables it prints today; daemon reads `.model_requests` for its job queue. This is also
the call site P4-IDX2 later swaps for an indexed query — extracting it now gives Robbert a clean seam.

### 5b. Transactions: the keystone `build_and_send_tx`

**Before** (`utils.py::build_and_send_tx`): takes `ctx` + three human strings, prints progress + tx
hash, and `raise typer.Exit(1)` on estimation/revert.

**After** — returns retry-informative state; raises with stable subcodes:

```python
# dincli/sdk/tx.py
@dataclass
class TxReceiptInfo:
    tx_hash: str                   # 0x hex
    status: int                    # 1 success, 0 revert
    block_number: int
    gas_used: int
    nonce: int
    contract_address: str | None   # set for deployment txs (deploy flows read this)
    logs: list[dict]               # raw, JSON-serializable log entries
    _raw: "TxReceipt" = field(repr=False, metadata={"json": "omit"})
        # web3 AttributeDict receipt, kept for in-SDK event decoding; NOT serialized

def send(session: DinSession, contract_function, *, tx_params: dict | None = None,
         on_event: Callable[[str, dict], None] | None = None) -> TxReceiptInfo:
    """Estimate → build → sign → send → wait. Returns receipt info.
    Raises TransactionError with subcode tx_estimation_failed | tx_reverted | tx_timeout |
    tx_nonce_conflict | tx_replacement_underpriced | receipt_missing (§4)."""

def decode_events(receipt: TxReceiptInfo, contract_event) -> list[dict]:
    """Decode a specific event from a receipt, e.g. registry.events.ModelRegistrationRequested().
    Wraps web3's process_receipt so the operations layer can build typed results
    (e.g. ModelRegistrationResult.request_id) without exposing raw web3 objects to consumers."""
```

Why the richer receipt: deploy flows read `tx_receipt.contractAddress` (`dindao.py`,
`modelownerd/deploy.py`) → `contract_address`; registry flows decode events via
`contract.events.X().process_receipt(tx_receipt)` (`task.py`) → `decode_events()` over the retained
`_raw`. The serialized surface (`to_envelope`) omits `_raw`; operations decode events into their own
typed result dataclasses.

Retry safety (§10): on failure the raised `TransactionError.details` carries enough to decide a retry —
`tx_hash` **if broadcast**, `nonce` if known, and a `broadcast: bool` flag (did we hit the network
before failing?). No message strings, no printing: the CLI supplies its own text and prints the
explorer URL; the daemon logs structured `on_event("submitted", {"tx_hash": …})`.

### 5c. IPFS: already SDK-shaped

`services/ipfs.py` already returns values and raises real exceptions. Extraction = move to
`sdk/ipfs.py`, replace the ~3 `console.print("Uploading via …")` lines with `logger`/`on_event`, wrap
raw `RuntimeError` into `IpfsError`.

---

## 6. Confirmations without a console — plan/apply is the default

Several pipelines gate on `_confirm_or_exit` / `typer.confirm` *mid-logic* (`task.register_request`,
`client.train_lms`, `model.*`, `gi.start`). **Plan/apply is the standard interface for all irreversible
operations** — on-chain writes, file mutations, uploads that feed on-chain state, and task execution.

**`plan` is strictly pure — it performs no side effects, including no IPFS upload.** This matters
because IPFS upload is itself an irreversible, CID-producing side effect: `register_request` today
uploads the manifest mid-flow (`task.py`) precisely to obtain the CID it then submits on-chain. A plan
therefore cannot both be pure *and* contain a freshly-produced CID. For CID-producing operations the
split is **three-phase** — prepare → upload → on-chain-apply:

```python
def register_request_prepare(session, manifest_path) -> RegisterPlan
    # PURE. Reads/validates the manifest, resolves the fee, and describes intent:
    #   RegisterPlan(manifest_path=…, fee_wei=…, would_upload=True, manifest_cid=None, …)
    # If a CID is already known, would_upload=False and manifest_cid is populated.

def register_request_upload(session, plan) -> RegisterPlan
    # SIDE EFFECT: uploads the manifest to IPFS, returns the plan with manifest_cid filled in.
    # Skipped when plan.would_upload is False.

def register_request_apply(session, plan) -> RegisterResult
    # ON-CHAIN: requires plan.manifest_cid set; submits the tx. Decision already made upstream.
```

- **CLI:** `prepare` → render (incl. "will upload manifest at <path>") → `_confirm_or_exit` →
  `upload` → `apply`.
- **Daemon:** `prepare` → evaluate the inspectable plan against policy/preferences → `upload` →
  `apply` (or stop after `prepare` if policy rejects — nothing was uploaded or spent).

Operations with **no** CID-producing step collapse to the simple two-phase `prepare`/`apply`.
`assume_yes: bool` / an injected `confirm` callback exist **only as a CLI-compatibility adapter**, not
as the SDK's primary design. Where no decision is supplied, the default policy **raises
`ConfirmationRequired`** rather than silently proceeding.

---

## 7. Backward-compatibility guarantees + test strategy

The refactor is internal. Guaranteed unchanged: **command names/arguments/options**, **human-readable
output**, **exit codes** (CLI maps `DinError` → today's non-zero exits; success `0`), and
**config/keystore/manifest on-disk formats and locations**.

Test strategy:
- **Keep the current suite green** — baseline on `develop` @ `8c4735d`: **70 passed, 1 skipped** across
  `tests/test_*.py` (the earlier connect-wallet / dintoken failures were fixed by PR #16 follow-ups in
  `c12b9e1`). The `tests/dincli/` integration suite is tracked separately — it hardcodes an
  environment path and needs a live Hardhat/IPFS/Docker stack, so it's out of scope for this refactor's
  green-bar.
- **Golden CLI-compatibility tests** for the first extracted commands: assert command names/options,
  exit codes, and key output lines — "same human-readable output" needs enforcing, not just "tests
  pass".
- **Import-boundary test:** assert `import dincli.sdk` pulls in no `typer`, `rich`, or `dincli.cli.*`
  — directly enforces principle 5. **Must run in a fresh Python subprocess** (else another test having
  already imported those modules gives a false pass/fail), e.g.
  `subprocess.run([sys.executable, "-c", "import dincli.sdk, sys; assert not {'typer','rich'} & set(sys.modules); assert not any(m.startswith('dincli.cli') for m in sys.modules)"])`.
- **New SDK-level unit tests** where extraction creates a directly-callable function — logic that today
  can only be exercised through `CliRunner` (because it's welded to the Typer command signature)
  becomes unit-testable in isolation once it lives in the SDK.

---

## 8. Proposed package layout

```
dincli/sdk/
  __init__.py          # curated public exports + __version__
  session.py           # DinSession (was DinContext, minus console/exit/prompts) + SignerProvider
  errors.py            # DinError hierarchy + reserved subcodes (§4) + sanitize_details (§4a)
  serialize.py         # to_envelope() + shared JSON encoder (§3)
  config.py            # config/env/network/IPFS-config resolution (from utils.py)
  wallet.py            # keystore/account/demo-key, non-interactive signing (from utils.py + system.connect_wallet)
  web3.py              # get_w3 (from utils.py)
  contracts.py         # ABIs + contract getters + artifact resolution (contract_utils + DinContext)
  cid.py               # from services/cid_utils.py (verbatim)
  ipfs.py              # from services/ipfs.py (§5c)
  manifest.py          # manifest/CID-cache/din_info (from utils.py + DinContext)
  runtime.py           # from services/runtime.py (verbatim)
  worker.py            # from cli/worker.py (console param → on_event/logger)
  state.py             # GI-state enums/converters + validate_* predicates (return/raise)
  tx.py                # send() + tx-param building (§5b)
  operations/          # role operations returning dataclasses (plan/apply where irreversible)
    registry.py  gi.py  aggregation.py  auditor.py  client.py  model.py  dao.py
```

Consumers:
- **CLI:** `command → build DinSession (interactive SignerProvider) → call sdk fn → render / map errors
  to exit codes` (+ optional `--json` emits `to_envelope(...)`).
- **Daemon:** `job → build DinSession (non-interactive SignerProvider) → call sdk fn →
  to_envelope(...) → update state/job queue`, keying retries off the stable error subcodes.

---

## 9. Resolved decisions (from review)

1. **Envelope shape** — `{status, data, error, meta}`, with `schema_version`, `sdk_version`,
   `network`, `chain_id`, and optional `correlation_id` in `meta`. ✔
2. **Amounts** — typed `int` in SDK dataclasses; decimal **strings** for all wei/token/`uint256` at the
   JSON boundary. ✔
3. **Confirmations** — **plan/apply is the standard**; `assume_yes`/injected confirm is a CLI adapter
   only. ✔
4. **Session naming** — **`DinSession`** (signals the no-console / no-exit / no-prompt contract). ✔
5. **Error taxonomy** — base hierarchy in §4 plus explicit, reserved **transaction and RPC subcodes**
   now. ✔
6. **Wallet** — **non-interactive by contract**: no `getpass`; raise `SignerUnavailable` /
   `WalletError` instead. ✔
7. **Doc home** — accepted version lives in **`Developer/design/`** as the DOC7 seed; summarize/link
   from `Documentation/technical/ARCHITECTURE.md` once implemented. ✔

## 10. Idempotency / retry expectations (daemon-facing writes)

The SDK need not implement full retry policy yet, but write results/errors must expose enough for a
consumer to retry safely: on success, `TxReceiptInfo` carries `tx_hash`, `nonce`, `status`; on failure,
`TransactionError.details` carries `tx_hash` **if broadcast**, `nonce` if known, and a `broadcast: bool`
flag distinguishing pre-broadcast failures (safe to rebuild) from post-broadcast ones (must confirm the
existing tx, not resend). Stable subcodes (§4) let the daemon pick the retry strategy.
```