#!/usr/bin/env python3
"""Verify task ABI bundles and deployable reference artifacts after forge build."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CONTRACTS = ("DINTaskCoordinator", "DINTaskAuditor")


def canonical_abi(abi: list) -> list[str]:
    # ABI entry order is not semantically significant; preserve nested ordering.
    return sorted(json.dumps(entry, sort_keys=True, separators=(",", ":")) for entry in abi)


def check_artifacts(root: Path) -> list[str]:
    errors = []
    for name in CONTRACTS:
        artifact_path = root / "foundry/out" / f"{name}.sol" / f"{name}.json"
        try:
            artifact = json.loads(artifact_path.read_text())
            expected_abi = canonical_abi(artifact["abi"])
            expected_bytecode = artifact["bytecode"]["object"]
            if not expected_bytecode or expected_bytecode == "0x":
                raise ValueError("empty build bytecode")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{name}: cannot read build artifact; run forge build first ({exc})")
            continue

        for directory in ("dincli/abis", "cache_model_0/abis"):
            path = root / directory / f"{name}.json"
            try:
                bundled = json.loads(path.read_text())
                if canonical_abi(bundled["abi"]) != expected_abi:
                    errors.append(f"{directory}/{name}.json: ABI differs from build")
                if directory == "cache_model_0/abis" and bundled.get("bytecode") != expected_bytecode:
                    errors.append(f"{directory}/{name}.json: creation bytecode differs from build")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"{directory}/{name}.json: invalid artifact ({exc})")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    errors = check_artifacts(args.root)
    for error in errors:
        print(error)
    if errors:
        return 1
    print("Task ABI bundles and reference creation bytecode match the Foundry build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
