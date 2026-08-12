# dincli/core.py
from __future__ import annotations

import sys
from typing import List

import click
from typer.core import TyperGroup

from dincli.cli.utils import ChainIdMismatchError


class GlobalOptionsGroup(TyperGroup):
    """Allows global options (--network, --version) to appear anywhere in the CLI."""

    GLOBAL_OPTIONS = {"--network", "--version", "-v"}

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except (ChainIdMismatchError, ConnectionError) as e:
            # pretty_exceptions_enable=False means anything uncaught here reaches the
            # user as a raw traceback. Both of these are expected, actionable operator
            # errors, so render the message alone. Their text is already scrubbed of
            # the RPC URL and the underlying provider exception (see get_w3).
            #
            # sys.exit, not click.exceptions.Exit: Typer re-raises the latter when
            # pretty_exceptions_enable=False, which prints the clean message AND a
            # full traceback. Verified against both failure modes.
            click.secho(str(e), err=True, fg="red")
            sys.exit(1)

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
