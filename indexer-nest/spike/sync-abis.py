#!/usr/bin/env python3
"""Keep indexer-nest/abis/ equal to what `forge build` produces.

Nuthatch cannot read the ABIs from subgraph/abis/ or foundry/out/ directly: its blob-path guard
refuses `..` and absolute paths, and it wants a bare JSON array where both of those wrap the array
as {"abi": [...]}. So the nest keeps plain-array copies, and this script is the only thing that
writes them.

  spike/sync-abis.py            rewrite indexer-nest/abis/ from foundry/out/
  spike/sync-abis.py --check    exit 1 if any file differs (for CI, after `forge build`)

DINTask.json is DINTaskCoordinator's and DINTaskAuditor's ABIs merged (one nuthatch template takes
one ABI), without their constructors. Entries are compared as JSON and order does not matter.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEST = os.path.dirname(HERE)
OUT = os.path.join(os.environ.get("DEVNET", os.path.dirname(NEST)), "foundry", "out")
SUBGRAPH = os.path.join(os.path.dirname(NEST), "subgraph", "abis")
PLAIN = ["DINModelRegistry", "DinValidatorStake", "DinCoordinator", "DinToken",
         "DinFeeRouter", "DinTreasury", "DinEmission"]


def canon(abi):
    return sorted(json.dumps(e, sort_keys=True) for e in abi)


def forge(name):
    with open(os.path.join(OUT, f"{name}.sol", f"{name}.json")) as f:
        return json.load(f)["abi"]


def wanted():
    files = {n: forge(n) for n in PLAIN}
    merged, seen = [], set()
    for e in forge("DINTaskCoordinator") + forge("DINTaskAuditor"):
        k = json.dumps(e, sort_keys=True)
        if e["type"] != "constructor" and k not in seen:
            seen.add(k)
            merged.append(e)
    files["DINTask"] = merged
    return files


def main():
    check = "--check" in sys.argv
    bad = []
    for name, abi in wanted().items():
        path = os.path.join(NEST, "abis", f"{name}.json")
        have = json.load(open(path)) if os.path.exists(path) else None
        if have is None or canon(have) != canon(abi):
            bad.append(name)
            if not check:
                with open(path, "w") as f:
                    json.dump(abi, f, indent=2)
                    f.write("\n")
    # The subgraph's copies, where it has one, must say the same: a drift there is worth knowing.
    for name in PLAIN + ["DINTaskCoordinator", "DINTaskAuditor"]:
        p = os.path.join(SUBGRAPH, f"{name}.json")
        if os.path.exists(p) and canon(json.load(open(p))["abi"]) != canon(forge(name)):
            print(f"note: subgraph/abis/{name}.json differs from forge build")
    if bad:
        print(("stale: " if check else "rewrote: ") + ", ".join(bad))
    else:
        print("indexer-nest/abis/ matches forge build")
    sys.exit(1 if bad and check else 0)


main()
