# dincli/core.py
from __future__ import annotations

from typing import List

from typer.core import TyperGroup


class GlobalOptionsGroup(TyperGroup):
    """Allows global options (--network, --version) to appear anywhere in the CLI."""

    GLOBAL_OPTIONS = {"--network", "--version", "-v"}

    def parse_args(self, ctx, args: List[str]):
        global_args = []
        remaining = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in self.GLOBAL_OPTIONS:
                global_args.append(arg)
                if arg == "--network" and i + 1 < len(args) and not args[i + 1].startswith("-"):
                    global_args.append(args[i + 1])
                    i += 1
                i += 1
                continue
            remaining.append(arg)
            i += 1

        super().parse_args(ctx, global_args + remaining)
        return remaining
