import importlib.util
from pathlib import Path

import requests
from urllib.parse import quote
from rich.console import Console
from dincli.cli.log import logger
from dincli.cli.utils import (
    FILEBASE_IPFS_ADD_URL,
    FILEBASE_IPFS_CAT_URL,
    FILEBASE_IPFS_PIN_URL,
    resolve_ipfs_config,
)
from dincli.services.cid_utils import get_cidv1base32_from_cid

console = Console()

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


def _build_retrieve_url(raw_url: str, cid: str) -> str:
    url = raw_url.rstrip("/")
    encoded_cid = quote(cid)

    if "{cid}" in url:
        return url.format(cid=encoded_cid)
    if "arg=" in url:
        separator = "" if url.endswith(("=", "&", "?")) else "&"
        return f"{url}{separator}arg={encoded_cid}"
    if url.endswith("/cat"):
        return f"{url}?arg={encoded_cid}"

    return f"{url}/cat?arg={encoded_cid}"


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
            console.print("[bold green]Uploading via Environment-backed IPFS...[/bold green]")
            cid = _upload_via_env(config, normalized_path)
        elif provider == "filebase":
            console.print("[bold green]Uploading via Filebase...[/bold green]")
            cid = _upload_via_filebase(config, normalized_path)
        elif provider == "custom":
            console.print("[bold green]Uploading via Custom IPFS provider...[/bold green]")
            cid = _upload_via_custom(config, normalized_path, msg)
        else:
            raise NotImplementedError(f"Unsupported IPFS provider: {provider}")

        normalized_cid = get_cidv1base32_from_cid(cid)
        if msg:
            logger.info(f"{msg} with path: {normalized_path} uploaded to IPFS with CID: {normalized_cid}")
        return normalized_cid

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"{_provider_label(provider)} upload failed: {exc.__class__.__name__}") from exc


def _retrieve_via_env(config, cid: str) -> requests.Response:
    if not config.api_url_retrieve:
        raise ValueError(
            "IPFS provider 'env' requires IPFS_API_URL_RETRIEVE in the current .env or environment."
        )

    response = requests.post(
        _build_retrieve_url(config.api_url_retrieve, cid),
        stream=True,
        timeout=30,
    )
    _raise_for_http_error(response, "download", "Environment-backed IPFS")
    return response


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


def _write_response_to_file(response: requests.Response, destination: Path):
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                handle.write(chunk)


def retrieve_from_ipfs(hash_value, retrieved_file_path):
    safe_path = _normalize_path(retrieved_file_path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    config = resolve_ipfs_config()
    provider = config.provider
    logger.info(f"Retrieving CID: {hash_value} from {_provider_label(provider)}")

    try:
        if provider == "env":
            response = _retrieve_via_env(config, hash_value)
            _write_response_to_file(response, safe_path)
            status_code = response.status_code
        elif provider == "filebase":
            response = _retrieve_via_filebase(config, hash_value)
            _write_response_to_file(response, safe_path)
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
