#!/usr/bin/env python3
"""Verify task ABI bundles and deployable reference artifacts after forge build."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CONTRACTS = ("DINTaskCoordinator", "DINTaskAuditor")


def canonical_abi(abi: list) -> list[str]:
    # ABI entry order is not semantically significant; preserve nested ordering.
    return sorted(json.dumps(entry, sort_keys=True, separators=(",", ":")) for entry in abi)


def bytecode_diagnostics(bundled: object, expected: str, artifact: dict) -> str:
    """Expose reproducibility differences without relaxing exact bytecode parity."""
    if not isinstance(bundled, str):
        return "bundled creation bytecode is not a string"
    actual = bytes.fromhex(expected.removeprefix("0x"))
    try:
        saved = bytes.fromhex(bundled.removeprefix("0x"))
    except ValueError:
        return "bundled creation bytecode is not valid hex"
    if saved == actual:
        difference = "decoded bytes identical; textual representation differs"
    else:
        first = next((i for i, (a, b) in enumerate(zip(saved, actual)) if a != b), min(len(saved), len(actual)))
        difference = f"first differing byte: {first}"
    metadata = artifact.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            metadata = None
    if not isinstance(metadata, dict):
        details = "build metadata: unavailable"
    else:
        sources = metadata.get("sources", {})
        source_hashes = {
            path: source.get("keccak256")
            for path, source in sources.items() if isinstance(source, dict)
        } if isinstance(sources, dict) else {}
        details = (
            f"build compiler: {json.dumps(metadata.get('compiler', {}), sort_keys=True)}; "
            f"build settings: {json.dumps(metadata.get('settings', {}), sort_keys=True)}; "
            f"build source hashes: {json.dumps(source_hashes, sort_keys=True)}"
        )
    return (
        f"{difference}; bundled length: {len(saved)}; build length: {len(actual)}; "
        f"bundled sha256: {hashlib.sha256(saved).hexdigest()}; "
        f"build sha256: {hashlib.sha256(actual).hexdigest()}; "
        f"{details}"
    )


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
                    errors.append(f"{name}: {bytecode_diagnostics(bundled.get('bytecode'), expected_bytecode, artifact)}")
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
