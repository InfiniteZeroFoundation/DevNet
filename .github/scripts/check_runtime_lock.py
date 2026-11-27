"""Compare the installed dincli runtime dependency graph to its applicable lock pins."""

from collections import deque
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

LOCK = Path(__file__).resolve().parents[2] / "requirements/dincli-runtime.txt"


def applicable_pins(path):
    pins = {}
    for line in path.read_text().splitlines():
        spec = line.partition("#")[0].strip()
        if not spec:
            continue
        req = Requirement(spec)
        if req.marker and not req.marker.evaluate({"extra": ""}):
            continue
        (pin,) = req.specifier
        name = canonicalize_name(req.name)
        if pin.operator != "==" or "*" in pin.version or name in pins:
            raise ValueError(f"Expected a unique exact pin for {name}: {spec}")
        pins[name] = Version(pin.version)
    return pins


def installed_runtime():
    versions = {}
    missing = set()
    visited = set()
    pending = deque([("dincli", "")])
    while pending:
        name, extra = pending.popleft()
        if (name, extra) in visited:
            continue
        visited.add((name, extra))
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            missing.add(name)
            continue
        if name != "dincli":
            versions[name] = Version(dist.version)
        for dependency in dist.requires or ():
            req = Requirement(dependency)
            if req.marker and not req.marker.evaluate({"extra": extra}):
                continue
            child = canonicalize_name(req.name)
            pending.append((child, ""))
            pending.extend((child, value) for value in req.extras)
    return versions, missing


def main():
    pins = applicable_pins(LOCK)
    installed, missing = installed_runtime()
    problems = [f"Missing installed distribution: {name}" for name in sorted(missing)]
    for name in sorted(pins.keys() | installed.keys()):
        if name not in pins:
            problems.append(f"Missing runtime pin: {name}=={installed[name]}")
        elif name not in installed:
            problems.append(f"Pin outside installed runtime graph: {name}=={pins[name]}")
        elif pins[name] != installed[name]:
            problems.append(f"{name}: installed {installed[name]}, locked {pins[name]}")
    if problems:
        raise SystemExit("\n".join(problems))
    print(f"Verified {len(pins)} runtime pins against installed dincli dependencies.")


if __name__ == "__main__":
    main()
