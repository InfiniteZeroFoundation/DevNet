"""Tests for the four small fixes backported from `main`.

1. `requires-python` is >=3.12, which the code already requires in practice
   (PEP 701 nested-quote f-string at `dincli/cli/dintoken.py:76`).
2. every third-party module `dincli/` imports is declared in `pyproject.toml`,
   so the package cannot install into an environment it can't import in.
3. `configure-ipfs` is in the system callback's skip-list, since it never
   touches the wallet it was demanding.
4. `read-din-per-eth` exposes the owner-mutable rate `buy` spends against.
"""

import ast
import sys
import tomllib
from pathlib import Path

import pytest
import typer
from typer.main import get_group
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
DINCLI = REPO_ROOT / "dincli"

runner = CliRunner()


def _pyproject():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _declared_distributions():
    deps = _pyproject()["project"]["dependencies"]
    # "rich>=13.0.0,<15.0.0" -> "rich"
    return {
        dep.split(";")[0].strip().split("[")[0]
        .split(">")[0].split("<")[0].split("=")[0].split("!")[0].strip().lower()
        for dep in deps
    }


# Module name -> distribution name, where they differ.
_MODULE_TO_DIST = {
    "dotenv": "python-dotenv",
    "cid": "py-cid",
    "multibase": "py-multibase",
    "eth_account": "eth-account",
    "yaml": "pyyaml",
}


def _imported_third_party_modules():
    """Top-level non-stdlib, non-first-party modules imported under dincli/."""
    stdlib = set(sys.stdlib_module_names)
    found = {}
    for path in DINCLI.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top not in stdlib and top != "dincli":
                    found.setdefault(top, set()).add(
                        str(path.relative_to(REPO_ROOT))
                    )
    return found


# ── 1. Python floor ─────────────────────────────────────────────────────


def test_requires_python_is_3_12():
    assert _pyproject()["project"]["requires-python"] == ">=3.12"


def test_codebase_actually_needs_3_12():
    """The floor is not arbitrary: at least one file uses PEP 701 syntax.

    Nested same-type quotes inside an f-string expression are a SyntaxError
    before 3.12. Asserting the syntax exists keeps the floor and the code
    honest about each other, rather than trusting a version string.
    """
    offenders = []
    for path in DINCLI.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith(("f\"", "console.print(f\"")) and "f\"" not in stripped:
                continue
            # A double-quoted f-string whose {...} contains a double quote.
            if _has_nested_same_quote_fstring(stripped):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert offenders, (
        "No PEP 701 syntax found. If this is genuinely true now, the >=3.12 "
        "floor may be loosenable again - re-measure before changing it."
    )


def _has_nested_same_quote_fstring(line: str) -> bool:
    idx = line.find('f"')
    while idx != -1:
        depth = 0
        i = idx + 2
        while i < len(line):
            char = line[i]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            elif char == '"':
                if depth > 0:
                    return True
                break
            i += 1
        idx = line.find('f"', idx + 2)
    return False


# ── 2. Declared dependencies ────────────────────────────────────────────


def test_every_imported_third_party_module_is_declared():
    """Guards the class of bug that made `main` need an explicit `click`.

    A dependency that only arrives transitively can disappear when an
    intermediate package changes its own requirements, and the failure mode
    is an ImportError at startup rather than anything gradual.
    """
    declared = _declared_distributions()
    missing = {}
    for module, files in sorted(_imported_third_party_modules().items()):
        dist = _MODULE_TO_DIST.get(module, module).lower()
        if dist not in declared:
            missing[f"{module} (as {dist})"] = sorted(files)[:3]
    assert not missing, f"imported but not declared in pyproject.toml: {missing}"


@pytest.mark.parametrize("dist", ["rich", "requests", "eth-account", "py-multibase"])
def test_previously_transitive_dependencies_are_declared(dist):
    """The four that were relying on web3/py-cid/typer to supply them.

    `rich` is the load-bearing one: at the declared floor of `typer>=0.9.0`,
    typer 0.9.0 lists rich only under `extra == "all"`, so a resolver may
    legitimately install it without rich and `import dincli.main` then fails
    on `from rich.table import Table`.
    """
    assert dist in _declared_distributions()


def test_dependency_list_has_no_duplicates():
    deps = _pyproject()["project"]["dependencies"]
    names = [d.split(">")[0].split("<")[0].split("=")[0].strip().lower() for d in deps]
    assert len(names) == len(set(names))


# ── 3. configure-ipfs skip-list ─────────────────────────────────────────


def _skip_list():
    """The literal list in the `system` group callback's skip check."""
    source = (DINCLI / "cli" / "system.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Compare)
            and isinstance(node.ops[0], ast.In)
            and isinstance(node.comparators[0], (ast.List, ast.Tuple))
        ):
            elements = node.comparators[0].elts
            if all(isinstance(e, ast.Constant) for e in elements):
                values = [e.value for e in elements]
                if "init" in values and "connect-wallet" in values:
                    return values
    raise AssertionError("could not locate the system callback skip-list")


def test_configure_ipfs_is_in_the_skip_list():
    assert "configure-ipfs" in _skip_list()


def test_skip_list_entries_match_registered_command_names():
    """Guards the underscore-vs-dash class of dead entry.

    Typer registers `read_wallet` as `read-wallet`, so a skip-list entry
    spelled with an underscore silently never matches. Every entry must
    correspond to a real command (or the `dataset` sub-app).
    """
    from dincli.cli import system

    registered = set(get_group(system.app).commands)
    unknown = [name for name in _skip_list() if name not in registered]
    assert not unknown, f"skip-list entries matching no registered command: {unknown}"


def test_configure_ipfs_body_never_touches_the_wallet():
    """Why the skip is correct rather than merely convenient."""
    source = (DINCLI / "cli" / "system.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "configure_ipfs"
    )
    body = ast.dump(func)
    for forbidden in ("get_en_w3_account_console", "'account'", "'w3'"):
        assert forbidden not in body, f"configure_ipfs references {forbidden}"


# ── 4. read-din-per-eth ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "module_name,app_attr",
    [
        ("dincli.cli.dintoken", "app"),
        ("dincli.cli.aggregator", "dintoken_app"),
        ("dincli.cli.auditor", "dintoken_app"),
    ],
)
def test_read_din_per_eth_registered_on_every_dintoken_app(module_name, app_attr):
    """All three `dintoken` sub-apps expose it, matching how buy/stake work."""
    import importlib

    app = getattr(importlib.import_module(module_name), app_attr)
    assert "read-din-per-eth" in get_group(app).commands


def test_read_din_per_eth_reads_the_rate_and_reports_both_forms(monkeypatch):
    from dincli.cli import dintoken

    printed = []

    class _Console:
        def print(self, *args, **kwargs):
            printed.append(" ".join(str(a) for a in args))

    class _Fn:
        def call(self):
            return 100_000 * 10**18

    class _Coordinator:
        functions = type("F", (), {"dinPerEth": staticmethod(lambda: _Fn())})()

    class _Ctx:
        obj = type(
            "O",
            (),
            {
                "get_en_w3_account_console": lambda self: (
                    "local", None, None, _Console()
                ),
                "get_deployed_din_coordinator_contract": lambda self: _Coordinator(),
            },
        )()

    raw = dintoken.read_din_per_eth_rate(_Ctx())

    assert raw == 100_000 * 10**18
    joined = "\n".join(printed)
    assert "100000" in joined          # human-readable, from_wei
    assert str(100_000 * 10**18) in joined  # raw, so the units are unambiguous


def test_read_din_per_eth_is_a_shared_helper_not_duplicated_logic():
    """`main` duplicated this across aggregator.py and auditor.py.

    Here it exists once in dintoken.py and the role apps delegate, matching
    how buy/stake/read-stake already work on this branch.
    """
    implementations = []
    for path in DINCLI.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "dinPerEth()" in source:
            implementations.append(str(path.relative_to(REPO_ROOT)))
    assert implementations == ["dincli/cli/dintoken.py"], implementations
