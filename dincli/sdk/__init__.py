"""DIN-SDK — shared logic layer for dincli and the dind daemon.

All protocol logic (chain, IPFS, wallet, manifest, transactions) lives here so
both the interactive CLI and the daemon can drive it. SDK functions return typed
dataclasses and raise ``DinError`` subclasses; they never print, never call
``typer.Exit``/``sys.exit``, and never prompt.

Design contract: ``dincli.sdk`` must import without pulling in ``typer``,
``rich``, or any ``dincli.cli.*`` module (enforced by tests/test_sdk_boundary.py).
The CLI depends on the SDK, never the reverse.

See Developer/design/sdk-interface-proposal.md for the full interface proposal.
"""

__version__ = "0.1.0"
