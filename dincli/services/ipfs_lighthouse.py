import requests
from pathlib import Path
from urllib.parse import quote

LIGHTHOUSE_UPLOAD_URL = "https://upload.lighthouse.storage/api/v0/add"
LIGHTHOUSE_GATEWAY_URL = "https://gateway.lighthouse.storage/ipfs"


def _raise_for_http_error(response: requests.Response, action: str, provider: str):
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        details = (response.text or "").strip()
        details = details[:300] if details else "No error details returned."
        raise RuntimeError(f"{provider} {action} failed [{response.status_code}]: {details}") from exc


def upload_via_lighthouse(config, file_path: Path) -> str:
    if not config.api_key:
        raise ValueError("Lighthouse IPFS provider requires an API key (config 'ipfs_api_key_lighthouse' or LIGHTHOUSE_API_KEY env var).")

    headers = {"Authorization": f"Bearer {config.api_key}"}
    with file_path.open("rb") as handle:
        response = requests.post(
            LIGHTHOUSE_UPLOAD_URL,
            files={"file": (file_path.name, handle, "application/octet-stream")},
            headers=headers,
            timeout=120,
        )
    _raise_for_http_error(response, "upload", "Lighthouse")
    try:
        return response.json()["data"]["Hash"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"Lighthouse upload returned an unexpected response shape: {exc}") from exc


def retrieve_via_lighthouse(config, cid: str) -> requests.Response:
    response = requests.get(f"{LIGHTHOUSE_GATEWAY_URL}/{quote(cid)}", stream=True, timeout=30)
    _raise_for_http_error(response, "download", "Lighthouse")
    return response
