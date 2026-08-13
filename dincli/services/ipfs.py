import importlib.util  # NOT `import importlib`: util is a submodule and is not
                       # loaded by the parent package, so attribute access on it
                       # only works if something else happened to import it first
import os
import requests
from rich import console
from pathlib import Path
from urllib.parse import quote, parse_qs, urlencode, urlparse, urlunparse
from dincli.cli.log import logger
from dincli.services.cid_utils import get_cidv1base32_from_cid, validate_cid

def _get_config():
    from dincli.cli.utils import load_config
    return load_config()

def _get_ipfs_urls():
    from dincli.cli.utils import resolve_ipfs_config
    return resolve_ipfs_config()

def  _ensure_file_exists(file_path: Path):
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

def _load_custom_fn(module_path: Path, fn_name: str):
    _ensure_file_exists(module_path)
    spec = importlib.util.spec_from_file_location(
        module_path.stem,
        module_path
    )

    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, fn_name):
        raise AttributeError(
            f"{fn_name} not found in custom service {module_path}"
            )

    fn = getattr(module, fn_name)
    if not callable(fn):
        raise TypeError(
            f"{fn_name} in {module_path} is not callable"
        )

    return fn

console = console.Console()

DEFAULT_PUBLIC_GATEWAY = "https://ipfs.io/ipfs"
_NO_PROVIDER_MSG = (
    "Set IPFS_API_URL_RETRIEVE (and IPFS_API_URL_ADD) for a local node, "
    "set IPFS_PUBLIC_GATEWAY=1 for a best-effort public gateway, or "
    "configure Filebase with "
    "`dincli system configure-ipfs --provider filebase`."
)
_FALLBACK_MSG = (
    "Reads are coming from a public, best-effort IPFS gateway, and the "
    "response is not verified against the requested CID. Uploads are NOT "
    "covered by this: submitting results still requires a real provider — "
    "set IPFS_API_URL_ADD for a local node, or configure Filebase with "
    "`dincli system configure-ipfs --provider filebase`."
)

_warned_fallback = False
_warned_no_provider = False


def _should_use_fallback():
    """Check IPFS_PUBLIC_GATEWAY env var.  Returns (enabled: bool, url: str|None)."""
    from dincli.cli.utils import get_env_key

    val = get_env_key("IPFS_PUBLIC_GATEWAY", None, verbose=False)
    if val is None:
        return False, None
    val = val.strip()
    if val.lower() in ("", "0", "false", "no"):
        return False, None
    if val.lower() in ("1", "true", "yes"):
        return True, DEFAULT_PUBLIC_GATEWAY

    parsed = urlparse(val)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"IPFS_PUBLIC_GATEWAY must be http or https, got {parsed.scheme!r}"
        )
    if "@" in parsed.netloc:
        raise ValueError(
            "IPFS_PUBLIC_GATEWAY must not contain credentials (user:pass@)"
        )
    if parsed.fragment:
        raise ValueError(
            "IPFS_PUBLIC_GATEWAY must not contain a fragment (#)"
        )
    if not parsed.netloc:
        raise ValueError("IPFS_PUBLIC_GATEWAY has no host")
    return True, val


def _is_kubo_path(path):
    """Check if a URL path targets a kubo RPC endpoint."""
    p = path.rstrip("/") if path else ""
    return p.endswith("/api/v0") or p.endswith("/api/v0/cat")


def _build_retrieval_url(base, cid):
    """Build (url, method) from a configured base URL and a CID.

    Returns (str, \"GET\") or (str, \"POST\").
    """
    encoded = quote(cid, safe="")

    if "{cid}" in base:
        url = base.replace("{cid}", encoded)
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") if parsed.path else ""
        method = "POST" if _is_kubo_path(path) else "GET"
        return url, method

    parsed = urlparse(base)
    scheme = parsed.scheme
    netloc = parsed.netloc
    path = parsed.path.rstrip("/") if parsed.path else ""
    query = parsed.query

    if _is_kubo_path(path):
        if path.endswith("/api/v0"):
            path = path + "/cat"
        qp = parse_qs(query, keep_blank_values=True)
        qp["arg"] = [encoded]
        new_query = urlencode(qp, doseq=True)
        url = urlunparse((scheme, netloc, path, "", new_query, ""))
        return url, "POST"

    base_url = f"{scheme}://{netloc}{path}"
    url = f"{base_url}/{encoded}"
    if query:
        url += "?" + query
    return url, "GET"

def _normalize_path(path: str) -> Path:
    """Normalize path (resolve .., ., symlinks)
    Warn about dangerous locations (but don't block)"""
    
    safe_path = Path(path).resolve()
    dangerous_roots = {Path("/etc"), Path("/boot"), Path("/dev"), Path("/proc")}
    if any(str(safe_path).startswith(str(root)) for root in dangerous_roots):
        logger.warning(f"⚠️ Readng/ Writing from/to system directory: {safe_path}")
        # Still proceed — user might have valid reason (e.g., containerized env)
    
    return Path(path).resolve()

def upload_to_ipfs(file_path, msg=None):

    file_path = _normalize_path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, 'rb') as f:
        file_content = f.read()

    config = _get_config()
    provider = config.get("ipfs_provider", "ipfs node")
    if not provider == "filebase":
        ipfs_api_url_add, _ = _get_ipfs_urls()
    cid = None

    try:
        if provider is None or provider == "ipfs node":

            if not ipfs_api_url_add:
                raise ValueError(f"IPFS API URL missing in {os.getcwd()}/.env as IPFS_API_URL_ADD ")

            response = requests.post(
                ipfs_api_url_add.rstrip('/'),  # Remove trailing slashes
                files={'file': (file_path.name, file_content)},
                timeout=30
            )
            response.raise_for_status()
            cid = response.json()['Hash']

        elif provider == "filebase":
            api_key = config.get("ipfs_api_key")
            if not api_key:
                raise ValueError("Filebase API key missing in dincli config as ipfs_api_key ")
            
            with open(file_path, 'rb') as f:
                # Upload
                upload_resp = requests.post(
                    "https://rpc.filebase.io/api/v0/add",
                    files={'file': (file_path.name, f, 'application/octet-stream')},
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=120
                )

            # Detailed error reporting
            if upload_resp.status_code != 200:
                error_detail = upload_resp.text[:-1] if upload_resp.text else "No error details"
                raise RuntimeError(
                    f"Filebase upload failed [{upload_resp.status_code}]: {error_detail}\n"
                    f"URL: https://rpc.filebase.io/api/v0/add\n"
                    f"File: {file_path.name} ({len(file_content)} bytes)"
                )
            
            upload_resp.raise_for_status()
            cid = upload_resp.json()['Hash']
            
            # Critical: Verify pinning succeeded
            pin_resp = requests.post(
                f"https://rpc.filebase.io/api/v0/pin/add?arg={quote(cid)}",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )
            if pin_resp.status_code != 200:
                logger.warning(f"Pinning failed for CID {cid} (status {pin_resp.status_code})")
                # Note: Filebase auto-pins on upload, but explicit pin adds redundancy
            
        elif provider == "custom":
            ipfs_service_path = config.get("ipfs_service_path")
            if not ipfs_service_path:
                raise ValueError(f"IPFS service path missing in dincli config as ipfs_service_path ")
            fn = _load_custom_fn(Path(ipfs_service_path), "upload_to_ipfs")
            cid = fn(file_path, msg)
            
        else:
            raise NotImplementedError(f"Unsupported IPFS provider: {provider}")

        cidv1base32_from_cid = get_cidv1base32_from_cid(cid)
        if msg:
            logger.info(f"{msg} uploaded to IPFS with CID: {cidv1base32_from_cid}")
        return cidv1base32_from_cid

    except requests.exceptions.RequestException as e:
        # NEVER log raw responses containing secrets
        provider_name = "Filebase" if provider == "filebase" else "IPFS node"
        raise RuntimeError(f"{provider_name} upload failed: {e.__class__.__name__}") from e


def retrieve_from_ipfs(hash_value, retrieved_file_path):
    # ── CID validation (before any provider branch) ─────────────────
    hash_value = validate_cid(hash_value)

    safe_path = _normalize_path(retrieved_file_path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    config = _get_config()
    provider = config.get("ipfs_provider", "ipfs node")
    if not provider == "filebase":
        _, ipfs_api_url_retrieve = _get_ipfs_urls()

    response = None
    tmp_path = None

    logger.info(f"Retrieving CID: {hash_value} from {provider.title()}")

    try:
        if provider is None or provider == "ipfs node":
            if ipfs_api_url_retrieve:
                url, method = _build_retrieval_url(
                    ipfs_api_url_retrieve, hash_value
                )
                response = requests.request(
                    method, url, stream=True, timeout=30
                )
            else:
                global _warned_fallback, _warned_no_provider
                fallback_enabled, fallback_url = _should_use_fallback()
                if fallback_enabled:
                    if not _warned_fallback:
                        logger.warning(_FALLBACK_MSG)
                        _warned_fallback = True
                    url, method = _build_retrieval_url(fallback_url, hash_value)
                    response = requests.request(
                        method, url, stream=True, timeout=30
                    )
                else:
                    if not _warned_no_provider:
                        logger.error(_NO_PROVIDER_MSG)
                        _warned_no_provider = True
                    raise ValueError(
                        "No IPFS retrieval endpoint configured. "
                        + _NO_PROVIDER_MSG
                    )

        elif provider == "filebase":
            api_key = config.get("ipfs_api_key")
            if not api_key:
                raise ValueError("Filebase API key missing")

            encoded = quote(hash_value, safe="")
            response = requests.post(
                f"https://rpc.filebase.io/api/v0/cat?arg={encoded}",
                headers={"Authorization": f"Bearer {api_key}"},
                stream=True,
                timeout=30,
            )

        elif provider == "custom":
            ipfs_service_path = config.get("ipfs_service_path")
            if not ipfs_service_path:
                raise ValueError(
                    "IPFS service path missing in dincli config "
                    "as ipfs_service_path "
                )
            fn = _load_custom_fn(
                Path(ipfs_service_path), "retrieve_from_ipfs"
            )
            response = fn(hash_value, retrieved_file_path)

        else:
            raise NotImplementedError(f"Unsupported provider: {provider}")

        # ── Atomic write ───────────────────────────────────────────
        response.raise_for_status()

        import tempfile

        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(safe_path.parent), prefix=".ipfs_"
        )
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, safe_path)
            tmp_path = None  # ownership transferred, do not clean up

            logger.info(f"Retrieved to: {safe_path}")
            status = response.status_code
            return status
        except BaseException:
            raise
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    except requests.exceptions.RequestException as e:
        logger.error(
            f"IPFS retrieval failed for {hash_value[:12]}: {e}"
        )
        raise RuntimeError(
            f"Failed to retrieve CID {hash_value[:12]}"
        ) from e
    finally:
        # The custom provider returns whatever its module returns, which may not
        # be a Response. Guard so a missing close() cannot mask the real error.
        if response is not None and hasattr(response, "close"):
            response.close()


