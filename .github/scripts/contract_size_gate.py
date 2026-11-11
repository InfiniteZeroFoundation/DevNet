#!/usr/bin/env python3
"""Enforce an EIP-170 / EIP-3860 size budget on every deployable foundry/src contract.

Run from foundry/ after `forge build` (issue #201 Part A):

    python ../.github/scripts/contract_size_gate.py [--out out]

Reads every foundry/out/<File>.sol/<Contract>.json artifact directly, rather than
`forge build --sizes`, whose table leaves DINTaskAuditor out. An artifact is
checked when its metadata compilationTarget is under src/ and its
deployedBytecode is non-empty (interfaces and abstract contracts have none;
test and script contracts aren't under src/). Linked libraries would show
unresolved `__$...$__` placeholders; none exist today, and the gate counts them
at their 20-byte linked size.

Fails when any runtime margin under EIP-170 is below FAIL_MARGIN, or any initcode
exceeds EIP-3860. Warns, without failing, when a runtime margin is below
WARN_MARGIN, so a contract approaching the budget shows up in every PR's log.
Fails closed if no artifacts are found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EIP170 = 24_576          # max runtime bytecode (bytes)
EIP3860 = 49_152         # max initcode (bytes)
FAIL_MARGIN = 1_024      # required runtime headroom under EIP170 (issue #201, PR #209 Decision 1)
WARN_MARGIN = 2_048      # headroom below which CI warns

PLACEHOLDER = re.compile(r"__\$[0-9a-fA-F]{34}\$__")


def code_size(obj: str) -> int:
    hexstr = obj[2:] if obj.startswith("0x") else obj
    # Each unlinked-library placeholder is 40 hex chars, the size of the address it becomes.
    hexstr = PLACEHOLDER.sub("0" * 40, hexstr)
    return len(hexstr) // 2


def compilation_target(artifact: dict) -> str | None:
    metadata = artifact.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return None
    target = (metadata.get("settings") or {}).get("compilationTarget") or {}
    return next(iter(target), None)


def collect(out_dir: Path) -> list[tuple[str, str, int, int]]:
    rows = []
    for path in sorted(out_dir.glob("*.sol/*.json")):
        try:
            artifact = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"::error::cannot read {path}: {exc}")
            sys.exit(1)
        source = compilation_target(artifact)
        if not source or not source.startswith("src/"):
            continue
        runtime = code_size((artifact.get("deployedBytecode") or {}).get("object", ""))
        if runtime == 0:
            continue
        initcode = code_size((artifact.get("bytecode") or {}).get("object", ""))
        rows.append((path.stem, source, runtime, initcode))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="out", help="forge artifact directory (default: out)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    rows = collect(out_dir)
    if not rows:
        print(f"::error::no deployable src/ artifacts found under {out_dir}/ -- run `forge build` first")
        return 1

    print(f"EIP-170 runtime limit {EIP170} B (fail below {FAIL_MARGIN} B margin, warn below {WARN_MARGIN} B); "
          f"EIP-3860 initcode limit {EIP3860} B")
    print(f"{'contract':<28} {'runtime':>8} {'margin':>8} {'initcode':>9}  status")
    failed = False
    for name, source, runtime, initcode in sorted(rows, key=lambda r: EIP170 - r[2]):
        margin = EIP170 - runtime
        status = "ok"
        if margin < FAIL_MARGIN:
            status = "FAIL"
            failed = True
            print(f"::error file=foundry/{source}::{name} runtime {runtime} B leaves {margin} B under EIP-170; "
                  f"the budget requires >= {FAIL_MARGIN} B")
        elif margin < WARN_MARGIN:
            status = "warn"
            print(f"::warning file=foundry/{source}::{name} runtime {runtime} B leaves only {margin} B under "
                  f"EIP-170 (warn below {WARN_MARGIN} B)")
        if initcode > EIP3860:
            status = "FAIL"
            failed = True
            print(f"::error file=foundry/{source}::{name} initcode {initcode} B exceeds EIP-3860 ({EIP3860} B)")
        print(f"{name:<28} {runtime:>8} {margin:>8} {initcode:>9}  {status}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
