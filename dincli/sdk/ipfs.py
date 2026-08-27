import importlib.util
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

import requests

from dincli.sdk.cid import get_bytes32_from_cid, get_cidv1base32_from_cid, validate_cid
from dincli.sdk.config import (
    FILEBASE_IPFS_ADD_URL,
    FILEBASE_IPFS_CAT_URL,
    FILEBASE_IPFS_PIN_URL,
    get_env_key,
    resolve_ipfs_config,
)
from dincli.sdk.log import logger

DEFAULT_PUBLIC_GATEWAY = "https://ipfs.io/ipfs"

_NO_PROVIDER_MSG = (
    "Configure Filebase with `dincli system configure-ipfs --provider "
    "filebase` — it handles pinning and 24/7 availability for both reads "
    "and writes. For reads only, set IPFS_API_URL_RETRIEVE for a local "
    "node, or set IPFS_PUBLIC_GATEWAY=1 for a best-effort public gateway."
)
_FALLBACK_MSG = (
    "Reads are coming from a public, best-effort IPFS gateway. Uploads are "
    "NOT covered by this: submitting results still requires a real "
    "provider. Configure Filebase with `dincli system configure-ipfs "
    "--provider filebase` — a local node's pinning and uptime are not "
    "reliable enough for uploads. Set IPFS_API_URL_ADD only if you're "
    "accepting that tradeoff."
)

_NO_VERIFY_MSG = (
    "Downloaded content was NOT verified against the requested CID — no "
    "usable local `ipfs` binary found. Install kubo "
    "(https://docs.ipfs.tech/install/command-line/) and run `ipfs init` "
    "once to enable this check. Both are fast, offline, one-time steps — no "
    "daemon needs to run afterward and no data needs to sync."
)

_warned_fallback = False
_warned_no_provider = False
_warned_no_verify = False


def _ensure_file_exists(file_path: Path):
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")


def _load_custom_fn(module_path: Path, fn_name: str):
    _ensure_file_exists(module_path)

    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, fn_name):
        raise AttributeError(f"{fn_name} not found in custom service {module_path}")

    fn = getattr(module, fn_name)
    if not callable(fn):
        raise TypeError(f"{fn_name} in {module_path} is not callable")

    return fn


def _normalize_path(path: str | Path) -> Path:
    safe_path = Path(path).expanduser().resolve()
    dangerous_roots = (Path("/etc"), Path("/boot"), Path("/dev"), Path("/proc"))

    if any(str(safe_path).startswith(str(root)) for root in dangerous_roots):
        logger.warning(f"Reading or writing through a sensitive system path: {safe_path}")

    return safe_path


def _provider_label(provider: str) -> str:
    return {
        "env": "environment-backed IPFS",
        "filebase": "Filebase",
        "custom": "custom IPFS service",
    }.get(provider, provider)


def _require_custom_service_path(config):
    if config.service_path is None:
        raise ValueError(
            "Custom IPFS provider requires 'ipfs_service_path' in dincli config. "
            "Set it with `dincli system configure-ipfs --provider custom --service-path <path>`."
        )

    return config.service_path


def _build_add_url(raw_url: str) -> str:
    url = raw_url.rstrip("/")
    return url if url.endswith("/add") else f"{url}/add"


def _compute_ipfs_cid_local(file_path: Path) -> str | None:
    """Best-effort: recompute a file's CID with a local `ipfs` binary (kubo).

    Uses the same code path that mints CIDs on upload, so a claimed CID can
    be checked without trusting whichever provider supplied the content.
    `ipfs add -n` (only-hash) needs no running daemon and no synced data —
    just the binary and a one-time offline `ipfs init`.

    Never raises: returns None when a local `ipfs` binary isn't usable
    (missing, never initialised, timeout), which the caller treats as
    "verification unavailable" rather than a failure. A local node is
    optional as a provider here, so it must stay optional for hashing too.
    """
    ipfs_bin = shutil.which("ipfs")
    if not ipfs_bin:
        return None

    try:
        result = subprocess.run(
            [ipfs_bin, "add", "-n", "-Q", str(file_path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def _verify_downloaded_cid(file_path: Path, requested_cid: str, provider: str) -> None:
    """Compare what was downloaded against what was requested.

    Raises ValueError on a genuine mismatch; degrades to a one-time warning
    when no local `ipfs` binary is available.

    Skipped for the `custom` provider: it is a user-supplied path that may
    use different chunking or CID settings, so comparing against kubo's
    defaults there risks rejecting legitimately good downloads.
    """
    if provider == "custom":
        return

    global _warned_no_verify

    computed_cid = _compute_ipfs_cid_local(file_path)
    if computed_cid is None:
        if not _warned_no_verify:
            logger.warning(_NO_VERIFY_MSG)
            _warned_no_verify = True
        return

    if get_bytes32_from_cid(computed_cid) != get_bytes32_from_cid(requested_cid):
        raise ValueError(
            f"CID mismatch: downloaded content hashes to {computed_cid}, not "
            f"the requested CID ({requested_cid[:12]}...). Refusing to save — "
            "the provider may be misbehaving, or the content may have been "
            "tampered with."
        )


def _is_kubo_path(path: str) -> bool:
    """Does this URL path target a kubo RPC endpoint (rather than a gateway)?

    Kubo's RPC is POST-only and takes the CID as an `arg=` query parameter;
    a gateway serves `GET <base>/<cid>`. Nothing but an RPC endpoint ends in
    `/api/v0` or `/cat`, so the suffix is a reliable discriminator.
    """
    p = path.rstrip("/") if path else ""
    return p.endswith("/api/v0") or p.endswith("/api/v0/cat") or p.endswith("/cat")


def _build_retrieve_url(raw_url: str, cid: str) -> tuple[str, str]:
    """Build ``(url, method)`` for retrieving ``cid`` from ``raw_url``.

    Kubo RPC endpoints get `cat?arg=<cid>` over POST; anything else is
    treated as a path-style gateway and gets `<base>/<cid>` over GET. The
    previous behaviour applied the kubo form unconditionally, which meant a
    gateway base such as ``https://ipfs.io/ipfs`` was requested as
    ``https://ipfs.io/ipfs/cat?arg=<cid>`` with POST — rejected by every
    gateway (405/500/301 depending on the host).
    """
    encoded_cid = quote(cid, safe="")

    if "{cid}" in raw_url:
        url = raw_url.replace("{cid}", encoded_cid)
        parsed = urlparse(url)
        method = "POST" if _is_kubo_path(parsed.path) else "GET"
        return url, method

    parsed = urlparse(raw_url)
    path = parsed.path.rstrip("/") if parsed.path else ""
    query = parsed.query

    # An explicit `arg=` means the caller already wrote a kubo RPC URL.
    if "arg=" in query or _is_kubo_path(path):
        if path.endswith("/api/v0"):
            path = f"{path}/cat"
        params = parse_qs(query, keep_blank_values=True)
        params["arg"] = [encoded_cid]
        url = urlunparse(
            (parsed.scheme, parsed.netloc, path, "", urlencode(params, doseq=True), "")
        )
        return url, "POST"

    url = f"{parsed.scheme}://{parsed.netloc}{path}/{encoded_cid}"
    if query:
        url = f"{url}?{query}"
    return url, "GET"


def _should_use_fallback() -> tuple[bool, str | None]:
    """Read IPFS_PUBLIC_GATEWAY. Returns ``(enabled, url)``.

    Opt-in: unset means no fallback. ``1``/``true``/``yes`` selects
    ``DEFAULT_PUBLIC_GATEWAY``; any other value is used as the gateway base
    after validation.
    """
    raw = get_env_key("IPFS_PUBLIC_GATEWAY", None, verbose=False)
    if raw is None:
        return False, None

    value = raw.strip()
    if value.lower() in ("", "0", "false", "no"):
        return False, None
    if value.lower() in ("1", "true", "yes"):
        return True, DEFAULT_PUBLIC_GATEWAY

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"IPFS_PUBLIC_GATEWAY must be http or https, got {parsed.scheme!r}"
        )
    if not parsed.netloc:
        raise ValueError("IPFS_PUBLIC_GATEWAY has no host")
    if "@" in parsed.netloc:
        raise ValueError("IPFS_PUBLIC_GATEWAY must not contain credentials (user:pass@)")
    if parsed.fragment:
        raise ValueError("IPFS_PUBLIC_GATEWAY must not contain a fragment (#)")

    return True, value


def _raise_for_http_error(response: requests.Response, action: str, provider: str):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        details = (response.text or "").strip()
        details = details[:300] if details else "No error details returned."
        raise RuntimeError(
            f"{provider} {action} failed [{response.status_code}]: {details}"
        ) from exc


def _upload_via_env(config, file_path: Path) -> str:
    if not config.api_url_add:
        raise ValueError(
            "IPFS provider 'env' requires IPFS_API_URL_ADD in the current .env or environment."
        )

    with file_path.open("rb") as handle:
        response = requests.post(
            _build_add_url(config.api_url_add),
            files={"file": (file_path.name, handle, "application/octet-stream")},
            timeout=30,
        )

    _raise_for_http_error(response, "upload", "Environment-backed IPFS")
    return response.json()["Hash"]


def _upload_via_filebase(config, file_path: Path) -> str:
    if not config.api_key:
        raise ValueError(
            "Filebase IPFS provider requires 'ipfs_api_key' in dincli config."
        )

    headers = {"Authorization": f"Bearer {config.api_key}"}

    with file_path.open("rb") as handle:
        response = requests.post(
            FILEBASE_IPFS_ADD_URL,
            files={"file": (file_path.name, handle, "application/octet-stream")},
            headers=headers,
            timeout=120,
        )

    _raise_for_http_error(response, "upload", "Filebase")
    cid = response.json()["Hash"]

    pin_response = requests.post(
        f"{FILEBASE_IPFS_PIN_URL}?arg={quote(cid)}",
        headers=headers,
        timeout=10,
    )
    if pin_response.status_code != 200:
        logger.warning(f"Filebase pin request failed for CID {cid}: {pin_response.status_code}")

    return cid


def _upload_via_custom(config, file_path: Path, msg=None) -> str:
    fn = _load_custom_fn(_require_custom_service_path(config), "upload_to_ipfs")
    cid = fn(file_path, msg)

    if not isinstance(cid, str) or not cid.strip():
        raise TypeError("Custom upload_to_ipfs must return a non-empty CID string.")

    return cid.strip()


def upload_to_ipfs(file_path, msg=None):
    normalized_path = _normalize_path(file_path)
    _ensure_file_exists(normalized_path)

    config = resolve_ipfs_config()
    provider = config.provider

    try:
        if provider == "env":
            logger.info("Uploading via Environment-backed IPFS...")
            cid = _upload_via_env(config, normalized_path)
        elif provider == "filebase":
            logger.info("Uploading via Filebase...")
            cid = _upload_via_filebase(config, normalized_path)
        elif provider == "custom":
            logger.info("Uploading via Custom IPFS provider...")
            cid = _upload_via_custom(config, normalized_path, msg)
        else:
            raise NotImplementedError(f"Unsupported IPFS provider: {provider}")

        normalized_cid = get_cidv1base32_from_cid(cid)
        if msg:
            logger.info(f"{msg} with path: {normalized_path} uploaded to IPFS with CID: {normalized_cid}")
        return normalized_cid

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"{_provider_label(provider)} upload failed: {exc.__class__.__name__}") from exc


def _retrieve_via_url(base_url: str, cid: str, label: str) -> requests.Response:
    url, method = _build_retrieve_url(base_url, cid)
    response = requests.request(method, url, stream=True, timeout=30)
    _raise_for_http_error(response, "download", label)
    return response


def _retrieve_via_env(config, cid: str) -> requests.Response:
    """Retrieve over the env-configured endpoint, falling back to a public
    gateway when no endpoint is configured and the fallback is opted into.

    Previously this raised outright when IPFS_API_URL_RETRIEVE was unset,
    which left a fresh install unable to read even fully public content.
    """
    global _warned_fallback, _warned_no_provider

    if config.api_url_retrieve:
        return _retrieve_via_url(
            config.api_url_retrieve, cid, "Environment-backed IPFS"
        )

    fallback_enabled, fallback_url = _should_use_fallback()
    if not fallback_enabled:
        if not _warned_no_provider:
            logger.error(_NO_PROVIDER_MSG)
            _warned_no_provider = True
        raise ValueError(f"No IPFS retrieval endpoint configured. {_NO_PROVIDER_MSG}")

    if not _warned_fallback:
        logger.warning(_FALLBACK_MSG)
        _warned_fallback = True

    return _retrieve_via_url(fallback_url, cid, "Public IPFS gateway")


def _retrieve_via_filebase(config, cid: str) -> requests.Response:
    if not config.api_key:
        raise ValueError(
            "Filebase IPFS provider requires 'ipfs_api_key' in dincli config."
        )

    response = requests.post(
        f"{FILEBASE_IPFS_CAT_URL}?arg={quote(cid)}",
        headers={"Authorization": f"Bearer {config.api_key}"},
        stream=True,
        timeout=30,
    )
    _raise_for_http_error(response, "download", "Filebase")
    return response


def _write_response_to_file(
    response: requests.Response, destination: Path, cid: str, provider: str
):
    """Stream ``response`` to ``destination`` atomically, verifying its CID.

    Writing straight to the destination left a truncated file behind when a
    download failed mid-stream, and callers treat any existing file as a
    cache hit — so a partial model would be silently reused. Write to a
    sibling temp file, fsync, verify, then rename: the destination either
    does not exist or holds complete, CID-checked content.
    """
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(destination.parent), prefix=".ipfs_")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())

        _verify_downloaded_cid(tmp_path, cid, provider)

        os.replace(tmp_path, destination)
        tmp_path = None  # ownership transferred to destination
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def retrieve_from_ipfs(hash_value, retrieved_file_path):
    safe_path = _normalize_path(retrieved_file_path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    config = resolve_ipfs_config()
    provider = config.provider

    # Validate before the CID reaches any URL, so a malformed or
    # path-traversal string fails here rather than being interpolated.
    # Skipped for "custom": that provider's identifiers are defined by the
    # user-supplied module, which need not use CID semantics at all.
    if provider != "custom":
        hash_value = validate_cid(hash_value)

    logger.info(f"Retrieving CID: {hash_value} from {_provider_label(provider)}")

    response = None
    try:
        if provider == "env":
            response = _retrieve_via_env(config, hash_value)
            _write_response_to_file(response, safe_path, hash_value, provider)
            status_code = response.status_code
        elif provider == "filebase":
            response = _retrieve_via_filebase(config, hash_value)
            _write_response_to_file(response, safe_path, hash_value, provider)
            status_code = response.status_code
        elif provider == "custom":
            fn = _load_custom_fn(_require_custom_service_path(config), "retrieve_from_ipfs")
            result = fn(hash_value, safe_path)
            status_code = result if result is not None else 200
        else:
            raise NotImplementedError(f"Unsupported IPFS provider: {provider}")

        logger.info(f"Retrieved to: {safe_path}")
        return status_code

    except requests.exceptions.RequestException as exc:
        logger.error(f"IPFS retrieval failed for {hash_value[:12]}: {exc}")
        raise RuntimeError(f"Failed to retrieve CID {hash_value[:12]}") from exc
    finally:
        # The custom provider returns whatever its module returns, which may
        # not be a Response — guard so a missing close() can't mask the real
        # error.
        if response is not None and hasattr(response, "close"):
            response.close()
