import os
import requests
from rich import console
from pathlib import Path
from urllib.parse import quote
from dincli.cli.log import logger
from dincli.cli.utils import resolve_ipfs_config, load_config

config = load_config()
ipfs_api_url_add, ipfs_api_url_retrieve = resolve_ipfs_config()
console = console.Console()

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

    provider = config.get("ipfs_provider", "ipfs node")
    cid = None

    try:
        if provider is None or provider == "ipfs node":
            # Raw IPFS node (self-hosted/Infura)

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
            
        else:
            raise NotImplementedError(f"Unsupported IPFS provider: {provider}")

        if msg:
            logger.info(f"{msg} uploaded to IPFS [{cid}]")
        return cid

    except requests.exceptions.RequestException as e:
        # NEVER log raw responses containing secrets
        provider_name = "Filebase" if provider == "filebase" else "IPFS node"
        raise RuntimeError(f"{provider_name} upload failed: {e.__class__.__name__}") from e


def retrieve_from_ipfs(hash_value, retrieved_file_path):

    safe_path = _normalize_path(retrieved_file_path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    provider = config.get("ipfs_provider", "ipfs node")
    response = None

    logger.info(f"Retrieving CID: {hash_value} from {provider.title()}")


    try:
        if provider is None or provider == "ipfs node":
            if not ipfs_api_url_retrieve:
                raise ValueError(f"IPFS API retrieve URL missing in {os.getcwd()}/.env as IPFS_API_URL_RETRIEVE ")

            response = requests.post(
                f"{ipfs_api_url_retrieve.rstrip('/')}/{quote(hash_value)}",
                stream=True,
                timeout=30
            )
            
        elif provider == "filebase":
            api_key = config.get("ipfs_api_key")
            if not api_key:
                raise ValueError("Filebase API key missing")
                
            response = requests.post(
                f"https://rpc.filebase.io/api/v0/cat?arg={quote(hash_value)}",
                headers={"Authorization": f"Bearer {api_key}"},
                stream=True,
                timeout=30
            )
            
        else:
            raise NotImplementedError(f"Unsupported provider: {provider}")
        
        response.raise_for_status()
        
        # Write file securely
        with open(safe_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        logger.info(f"Retrieved to: {safe_path.name}")
        return response.status_code

    except requests.exceptions.RequestException as e:
        logger.error(f"IPFS retrieval failed for {hash_value[:12]}: {e}")
        raise RuntimeError(f"Failed to retrieve CID {hash_value[:12]}") from e
