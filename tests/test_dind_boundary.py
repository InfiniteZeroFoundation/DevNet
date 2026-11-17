"""Import-boundary test: dincli.dind pulls in no dincli.cli.* (P4-1.1).

Runs in a fresh subprocess so earlier tests that imported UI modules can't
mask a violation.
"""

import subprocess
import sys
import textwrap


def test_dind_imports_no_cli():
    script = textwrap.dedent("""
        import importlib, pkgutil, sys
        import dincli.dind
        for m in pkgutil.walk_packages(dincli.dind.__path__, dincli.dind.__name__ + "."):
            importlib.import_module(m.name)
        loaded = set(sys.modules)
        bad_cli = sorted(
            m for m in loaded
            if m == "dincli.cli" or m.startswith("dincli.cli.")
        )
        assert not bad_cli, f"dind imported dincli.cli modules: {bad_cli}"
        print("ok")
    """)
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
