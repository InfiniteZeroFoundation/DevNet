# IPFS Configuration Guide

**Prerequisite:** [Wallet Setup](./wallet-setup.md) — set up a production keystore before configuring IPFS and connecting to the network.

`dincli` supports four IPFS modes:

1. `env`: use URLs from the current shell or project `.env`
2. `filebase`: use Filebase's managed IPFS RPC
3. `lighthouse`: use Lighthouse's Filecoin-backed IPFS pinning service
4. `custom`: load a Python module that implements the IPFS operations

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
dincli system configure-ipfs --provider lighthouse --api-key <lighthouse_api_key>
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

If you use a local node, make sure uploaded artifacts are pinned or otherwise retained.

## `filebase` provider

Use Filebase when you want a managed IPFS backend:

```bash
dincli system configure-ipfs --provider filebase --api-key <filebase_rpc_token>
```

Notes:

- the token is stored in the user-level `dincli` config
- `dincli` uploads through Filebase's RPC API and issues a pin request after upload
- `api_secret` is optional metadata only; the built-in Filebase flow uses the API key

## `lighthouse` provider

Use Lighthouse when you want Filecoin-backed IPFS pinning:

```bash
dincli system configure-ipfs --provider lighthouse --api-key <lighthouse_api_key>
# or: export LIGHTHOUSE_API_KEY=<key>   (fallback if no key is configured)
```

Notes:

- uploads go to Filecoin via Lighthouse's pinning service; retrieval uses Lighthouse's IPFS gateway
- API keys are created via [files.lighthouse.storage](https://files.lighthouse.storage) or the `lighthouse-web3` CLI (requires a wallet signature)
- the API key is stored per-provider (`ipfs_api_key_lighthouse`), so switching from Filebase does not silently reuse its key
- `LIGHTHOUSE_API_KEY` env var is honored as a fallback when no key is configured

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
