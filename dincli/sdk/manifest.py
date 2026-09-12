import json
import logging
import os
import re
from importlib.resources import files
from pathlib import Path

from dincli.sdk.cid import get_cid_from_bytes32
from dincli.sdk.config import CACHE_DIR
from dincli.sdk.contracts import get_contract_instance
from dincli.sdk.errors import ValidationError
from dincli.sdk.ipfs import retrieve_from_ipfs

logger = logging.getLogger("dincli")

DIN_INFO_PATH = files("dincli").joinpath("config", "din_info.json")
CID_SERVICES_PATH = files("dincli").joinpath("config", "cid_services.json")


def load_din_info() -> dict:
    with open(DIN_INFO_PATH) as f:
        return json.load(f)


def load_cid_services() -> dict:
    with open(CID_SERVICES_PATH) as f:
        return json.load(f)


def save_din_info(data: dict):
    with open(DIN_INFO_PATH, "w") as f:
        json.dump(data, f, indent=2)


def is_ethereum_address(s: str) -> bool:
    return bool(re.fullmatch(r'0x[a-fA-F0-9]{40}', s))


def download_manifest(network: str, model_id: int, *, force: bool = False) -> None:
    if int(model_id) < 0:
        raise ValidationError("Model ID must be non-negative")

    manifest_dir = CACHE_DIR / network / f"model_{model_id}"
    os.makedirs(manifest_dir, exist_ok=True)
    manifest_path = manifest_dir / "manifest.json"
    cid_path = manifest_dir / "manifest.json.cid"

    if not force and manifest_path.exists():
        return

    din_info = load_din_info()
    din_registry_address = din_info[network]["registry"]
    din_registry_abi = files("dincli").joinpath("abis", "DINModelRegistry.json")

    din_registry_contract = get_contract_instance(din_registry_abi, network, din_registry_address)

    model_info = din_registry_contract.functions.getModel(model_id).call()

    if force or not manifest_path.exists():
        retrieve_from_ipfs(get_cid_from_bytes32(model_info[2].hex()), manifest_path)

        with open(cid_path, "w") as f:
            f.write(get_cid_from_bytes32(model_info[2].hex()))


def get_model_info(network: str, model_id: int, *, include_genesis: bool = False) -> dict:
    din_info = load_din_info()
    din_registry_address = din_info[network]["registry"]
    din_registry_abi = files("dincli").joinpath("abis", "DINModelRegistry.json")

    din_registry_contract = get_contract_instance(din_registry_abi, network, din_registry_address)

    model_info = din_registry_contract.functions.getModel(model_id).call()

    result = {
        "model_owner": model_info[0],
        "is_open_source": model_info[1],
        "manifest_cid_bytes32": model_info[2],
        "manifest_cid": get_cid_from_bytes32(model_info[2].hex()),
        "created_at": model_info[3],
        "task_coordinator_address": model_info[4],
        "task_auditor_address": model_info[5],
    }

    if include_genesis:
        din_task_coordinator_abi = files("dincli").joinpath("abis", "DINTaskCoordinator.json")
        task_coordinator_contract = get_contract_instance(
            din_task_coordinator_abi, network, model_info[4]
        )
        genesis_model_ipfs_hash_raw = task_coordinator_contract.functions.genesisModelIpfsHash().call()
        result["genesis_model_ipfs_hash"] = get_cid_from_bytes32(
            genesis_model_ipfs_hash_raw.hex()
        )

    return result


def get_manifest_path(
    network: str,
    model_id: int | None = None,
    task_coordinator_address: str | None = None,
) -> Path:
    has_model_id = model_id is not None
    has_coordinator_address = task_coordinator_address is not None

    if not has_model_id and not has_coordinator_address:
        raise ValueError("Either model_id or task_coordinator_address must be provided")

    if has_model_id and has_coordinator_address:
        raise ValueError("Only one of model_id or task_coordinator_address can be provided")

    if has_model_id:
        return CACHE_DIR / network / f"model_{model_id}" / "manifest.json"

    return Path(os.getcwd()) / "tasks" / network.lower() / task_coordinator_address / "manifest.json"


def get_manifest(
    network: str,
    model_id: int | None = None,
    task_coordinator_address: str | None = None,
) -> dict:
    manifest_path = get_manifest_path(
        network,
        model_id=model_id,
        task_coordinator_address=task_coordinator_address,
    )

    if model_id is not None:
        cid_path = manifest_path.with_suffix(".json.cid")

        needs_update = True

        try:
            din_info = load_din_info()
            din_registry_address = din_info[network]["registry"]
            din_registry_abi = files("dincli").joinpath("abis", "DINModelRegistry.json")
            din_registry_contract = get_contract_instance(din_registry_abi, network, din_registry_address)
            model_info = din_registry_contract.functions.getModel(int(model_id)).call()
            on_chain_cid = get_cid_from_bytes32(model_info[2].hex())

            if manifest_path.exists() and cid_path.exists():
                with open(cid_path, "r") as f:
                    local_cid = f.read().strip()
                if local_cid == on_chain_cid:
                    needs_update = False
        except Exception as e:
            logger.warning("Could not verify manifest freshness: %s", e)
            needs_update = True

        if needs_update:
            download_manifest(network, int(model_id), force=True)
    elif not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found for task coordinator {task_coordinator_address} at {manifest_path}"
        )

    with open(manifest_path, "r") as f:
        return json.load(f)


def get_manifest_key(
    network: str,
    key: str,
    model_id: int | None = None,
    task_coordinator_address: str | None = None,
):
    manifest = get_manifest(
        network,
        model_id=model_id,
        task_coordinator_address=task_coordinator_address,
    )
    return manifest[key]
