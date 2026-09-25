#!/usr/bin/env python3
"""PreToolUse hook: block a raw `git push` to develop from Claude's Bash tool.

Pushes to develop must go through the din-push-develop skill (local CI mirror
first, then a background watch of the GitHub push run). The skill marks its own
push with DIN_PUSH_DEVELOP=1, which this hook lets through.
"""
import json
import re
import shlex
import subprocess
import sys

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")
cwd = data.get("cwd") or None

if "DIN_PUSH_DEVELOP=1" in cmd:
    sys.exit(0)


def current_branch(path):
    try:
        return subprocess.run(["git", "-C", path or ".", "branch", "--show-current"],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def pushes_develop(segment):
    try:
        toks = shlex.split(segment)
    except ValueError:
        return False
    while toks and re.match(r"^\w+=", toks[0]):  # leading VAR=value
        toks = toks[1:]
    if len(toks) < 2 or toks[0] != "git":
        return False
    path = cwd
    rest = toks[1:]
    while rest and rest[0] in ("-C", "-c") and len(rest) > 1:
        if rest[0] == "-C":
            path = rest[1]
        rest = rest[2:]
    if not rest or rest[0] != "push":
        return False
    args = [t for t in rest[1:] if not t.startswith("-")]
    refspecs = args[1:]  # args[0] is the remote
    for r in refspecs:
        dest = r.split(":")[-1].lstrip("+").removeprefix("refs/heads/")
        if dest == "HEAD":
            dest = current_branch(path)
        if dest == "develop":
            return True
    return not refspecs and current_branch(path) == "develop"


segments = re.split(r"&&|\|\||;|\||\n", cmd)
if any(pushes_develop(s) for s in segments):
    print("Blocked: pushes to develop go through the din-push-develop skill "
          "(local CI mirror, then background watch of the GitHub push run). "
          "Invoke that skill instead of running git push directly.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
