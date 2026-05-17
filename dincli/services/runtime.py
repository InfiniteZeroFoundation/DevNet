from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dincli.cli.utils import get_manifest, get_manifest_path


@dataclass(frozen=True)
class ServiceRuntimeContext:
    network: str
    manifest: dict[str, Any]
    manifest_path: Path
    model_id: Optional[int] = None
    task_coordinator_address: Optional[str] = None
    role: Optional[str] = None

    def get_manifest_key(self, key: str, default: Any = None) -> Any:
        return self.manifest.get(key, default)

    def require_manifest_key(self, key: str) -> Any:
        if key not in self.manifest:
            raise KeyError(f"Manifest key '{key}' not found in {self.manifest_path}")
        return self.manifest[key]


def build_service_runtime_context(
    network: str,
    *,
    model_id: int | None = None,
    task_coordinator_address: str | None = None,
    role: str | None = None,
) -> ServiceRuntimeContext:
    manifest_path = get_manifest_path(
        network,
        model_id=model_id,
        task_coordinator_address=task_coordinator_address,
    )
    manifest = get_manifest(
        network,
        model_id=model_id,
        task_coordinator_address=task_coordinator_address,
    )
    return ServiceRuntimeContext(
        network=network,
        manifest=manifest,
        manifest_path=manifest_path,
        model_id=model_id,
        task_coordinator_address=task_coordinator_address,
        role=role,
    )
