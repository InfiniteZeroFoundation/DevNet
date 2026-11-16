"""Seed the isolated IPFS node with the reference model's default artifacts.

`model-owner task cache-default-artifacts` and `add-default-test-data` fetch
the CIDs in din_info.json's `default_*` entries. Isolated runs use a fresh,
offline Kubo node, which can't fetch those CIDs, and since Nov 2026 no
provider on the public IPFS network serves `default_manifest` at all. This
module adds the repo's reference MNIST model (`cache_model_0/`,
`cid_services/`, the bundled `dincli/abis/`) to the isolated node instead,
and returns the din_info overrides pointing at the CIDs it got.

A CID that a repo file already reproduces is kept, so the content is
unchanged. Otherwise the repo's version of that artifact is added and its
new CID is used, both in din_info and in the default manifest:

- services: `cache_model_0/services/<name>`
- task-contract ABIs: `dincli/abis/<name>` (current foundry ABIs; the copies
  in `cache_model_0/abis/` predate the richer GI states)
- per-role requirements: `cache_model_0/requirements/<role>/requirements.txt`
- default test dataset: `cache_model_0/dataset/test/test_dataset.pt`
"""

import json
from pathlib import Path
from typing import Callable

from dincli.services.cid_utils import get_bytes32_from_cid
from tests.dincli.constants import DEVNET_ROOT

MODEL_DIR = DEVNET_ROOT / "cache_model_0"
CID_SERVICES_DIR = DEVNET_ROOT / "cid_services"
BUNDLED_ABIS_DIR = DEVNET_ROOT / "dincli" / "abis"
CID_SERVICES_JSON = DEVNET_ROOT / "dincli" / "config" / "cid_services.json"

AddFn = Callable[[Path], str]


def _service_file(manifest_path: str) -> Path:
    return MODEL_DIR / manifest_path.lstrip("/")


def _abi_file(manifest_path: str) -> Path:
    return BUNDLED_ABIS_DIR / Path(manifest_path).name


def build_seeded_manifest(add: AddFn) -> dict:
    """The reference manifest with every artifact CID replaced by one `add` returned."""
    manifest = json.loads((MODEL_DIR / "manifest.json").read_text(encoding="utf-8"))

    for entry in manifest.values():
        if isinstance(entry, dict) and entry.get("path") and entry.get("ipfs"):
            entry["ipfs"] = add(_service_file(entry["path"]))

    for contract in manifest.get("task_contracts", {}).values():
        artifact = contract.get("artifact") or {}
        if artifact.get("path") and artifact.get("ipfs"):
            artifact["ipfs"] = add(_abi_file(artifact["path"]))

    for role in list(manifest.get("requirements.txt", {})):
        manifest["requirements.txt"][role] = add(MODEL_DIR / "requirements" / role / "requirements.txt")

    return manifest


def seed_default_artifacts(add: AddFn, scratch: Path) -> dict:
    """Add the reference artifacts via `add` and return the din_info `default_*` overrides.

    `scratch` is a writable directory for the generated manifest file.
    """
    manifest = build_seeded_manifest(add)
    manifest_path = scratch / "seeded_default_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=3), encoding="utf-8")

    services = {
        name: add(MODEL_DIR / "services" / name)
        for name in ("model.py", "modelowner.py", "client.py", "auditor.py", "aggregator.py", "scoring.py")
    }
    abis = {name: add(BUNDLED_ABIS_DIR / name) for name in ("DINTaskCoordinator.json", "DINTaskAuditor.json")}
    requirements = {
        role: add(MODEL_DIR / "requirements" / role / "requirements.txt")
        for role in ("clients", "auditors", "aggregators", "modelowner")
    }

    # `system dataset distribute-mnist` fetches its service by the CIDs in
    # cid_services.json; the repo copies reproduce them, so adding them is enough.
    for entry in json.loads(CID_SERVICES_JSON.read_text(encoding="utf-8"))["services"].values():
        service = CID_SERVICES_DIR / entry["path"].lstrip("/").removeprefix("services/")
        requirements_file = CID_SERVICES_DIR / "requirements" / Path(entry["path"]).with_suffix(".txt").name
        for path, expected in ((service, entry["ipfs"]), (requirements_file, entry["requirements"])):
            got = add(path)
            # Compare digests, as dincli does: the node may return a CIDv0 for a v1 CID.
            if get_bytes32_from_cid(got) != get_bytes32_from_cid(expected):
                raise RuntimeError(f"{path} hashes to {got}, but cid_services.json expects {expected}")

    return {
        "default_manifest": add(manifest_path),
        "default_services": services,
        "default_abis": abis,
        "default_requirements": requirements,
        "default_test_dataset": add(MODEL_DIR / "dataset" / "test" / "test_dataset.pt"),
    }


def apply_din_info_overrides(din_info_path: Path, network: str, overrides: dict) -> None:
    din_info = json.loads(din_info_path.read_text(encoding="utf-8"))
    din_info.setdefault(network, {}).update(overrides)
    din_info_path.write_text(json.dumps(din_info, indent=4) + "\n", encoding="utf-8")
