# IPFS Configuration Guide

`dincli` supports three IPFS modes:

1. `env`: use URLs from the current shell or project `.env`
2. `filebase`: use Filebase's managed IPFS RPC
3. `custom`: load a Python module that implements the IPFS operations

## Default behavior

If you do not configure an IPFS provider, `dincli` now defaults to `env`.

That means the built-in `upload_to_ipfs(...)` and `retrieve_from_ipfs(...)` helpers will read:

```bash
IPFS_API_URL_ADD=...
IPFS_API_URL_RETRIEVE=...
```

from the current environment or the `.env` file in your project root.

## Provider selection

Show the active configuration:

```bash
dincli system configure-ipfs
```

Set the provider explicitly:

```bash
dincli system configure-ipfs --provider env
dincli system configure-ipfs --provider filebase --api-key <filebase_rpc_token>
dincli system configure-ipfs --provider custom --service-path /abs/path/to/custom_ipfs.py
```

## `env` provider

This is the default mode when you already control an IPFS-compatible HTTP API.

Add these variables to your project `.env`:

```bash
IPFS_API_URL_ADD=http://127.0.0.1:5001/api/v0
IPFS_API_URL_RETRIEVE=http://127.0.0.1:5001/api/v0
```

`dincli` accepts either:

- the API root, such as `http://127.0.0.1:5001/api/v0`
- the full add endpoint, such as `http://127.0.0.1:5001/api/v0/add`
- the full cat endpoint, such as `http://127.0.0.1:5001/api/v0/cat`
- a retrieve URL template containing `{cid}`
- a path-style gateway base, such as `https://ipfs.io/ipfs` (retrieval only)

`IPFS_API_URL_RETRIEVE` may therefore point at either a kubo RPC endpoint or a
read-only gateway, and `dincli` picks the right call for each:

| Endpoint shape | Request issued |
|---|---|
| ends in `/api/v0`, `/api/v0/cat`, or `/cat` | `POST <base>/cat?arg=<cid>` (kubo RPC) |
| anything else | `GET <base>/<cid>` (gateway) |

A gateway cannot accept uploads, so `IPFS_API_URL_ADD` must still be a kubo RPC
endpoint.

If you use a local node, make sure uploaded artifacts are pinned or otherwise retained.

## Reading without a configured provider

Retrieval needs an endpoint. If `IPFS_API_URL_RETRIEVE` is unset, `dincli` fails
with a message naming your options rather than reporting the CID as unavailable.

For read-only access to public content — inspecting a manifest or a global model
before you have an account anywhere — opt into a public gateway:

```bash
IPFS_PUBLIC_GATEWAY=1                        # use the default gateway
IPFS_PUBLIC_GATEWAY=https://dweb.link/ipfs   # or name your own
```

Accepted values: `1`, `true`, `yes` select the default gateway; `0`, `false`,
`no` or leaving it unset disables the fallback; anything else is used as the
gateway base, and must be `http`/`https`, carry a host, and contain no
credentials or fragment.

This is deliberately opt-in and read-only. It is a best-effort public endpoint,
so treat it as a convenience for public data, not as a provider:

- **uploads are not covered.** Submitting aggregation or audit results needs a
  real upload-capable provider — configure `filebase` for that.
- a configured `IPFS_API_URL_RETRIEVE` always takes precedence over the fallback.

## Content verification

Retrieved content is checked against the CID that was requested before it is
saved, on every provider except `custom` (whose CID semantics are defined by
your own module). A mismatch raises and nothing is written.

The check recomputes the CID with a local `ipfs add -n` (only-hash). That needs
the kubo binary and a one-time `ipfs init`, but **no running daemon and no
synced data** — both steps are offline and near-instant:

```bash
ipfs init      # once; safe to run even if you never start a daemon
```

Without a usable local `ipfs` binary the check is skipped with a warning rather
than failing, so a local node stays optional. Downloads are written atomically,
so a transfer that fails midway leaves no partial file behind for a later run to
mistake for a cached artifact.

## `filebase` provider

Use Filebase when you want a managed IPFS backend:

```bash
dincli system configure-ipfs --provider filebase --api-key <filebase_rpc_token>
```

Notes:

- the token is stored in the user-level `dincli` config
- `dincli` uploads through Filebase's RPC API and issues a pin request after upload
- `api_secret` is optional metadata only; the built-in Filebase flow uses the API key

## `custom` provider

Use `custom` when you want complete control over the storage implementation.

Your module must export both functions:

```python
from pathlib import Path

def upload_to_ipfs(file_path: Path, msg: str | None = None) -> str:
    ...

def retrieve_from_ipfs(cid: str, file_path: Path) -> int | None:
    ...
```

Requirements:

- `upload_to_ipfs` must return a non-empty CID string
- `retrieve_from_ipfs` must write the downloaded artifact to `file_path`
- `retrieve_from_ipfs` may return an HTTP-like status code, or `None`

Example:

```python
from pathlib import Path

def upload_to_ipfs(file_path: Path, msg: str | None = None) -> str:
    return "bafy..."

def retrieve_from_ipfs(cid: str, file_path: Path) -> int:
    Path(file_path).write_bytes(b"example payload")
    return 200
```

Configure it with:

```bash
dincli system configure-ipfs --provider custom --service-path /abs/path/to/custom_ipfs.py
```

## Migration notes

- legacy config values such as `"ipfs node"` are treated as `env`
- API keys are now stored per-provider (`ipfs_api_key_<provider>`) instead of one flat `ipfs_api_key` field; existing Filebase configs keep working unchanged via a legacy fallback
- existing call sites do not need to change; `dincli.services.ipfs.upload_to_ipfs` and `retrieve_from_ipfs` still provide the shared interface used across the codebase
- system diagnostics now validate only the active provider instead of always requiring `.env` IPFS URLs
