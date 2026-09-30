#!/usr/bin/env python3
"""Check *inline* relative Markdown links under the given roots.

Scope, stated precisely because a checker that overstates its coverage is worse
than one that admits its limits:

  handled     inline links -- [text](path), [text](<path>), [text](path "title"),
              with an optional #fragment; fenced code blocks are skipped
  NOT handled reference-style links ([text][ref] + [ref]: path), destinations
              spanning multiple lines, destinations containing balanced
              parentheses, single-quoted or parenthesised titles, and
              percent-encoded paths

Anything in the "not handled" list is invisible to this check, not tolerated by
it. The Documentation/ corpus contains none of those forms today (verified: 0
fenced links, 0 reference definitions); widen this script before relying on it
for a tree that does.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# Fence opener/closer. Written with `{3,}` rather than literal backticks so this
# file can itself be embedded in a Markdown fence without terminating it.
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*(.*)$")
EXTERNAL = ("http://", "https://", "mailto:", "tel:", "ftp://", "//")


def iter_prose(text: str):
    """Yield (lineno, line) for lines outside fenced code blocks.

    Tracks the opening fence's character and length: a fence closes only on the
    same character, at least as long, and with no trailing info string. Without
    that, a ``~~~`` block containing a triple backtick toggles the state and the
    rest of the file is misclassified.
    """
    fence_char: str | None = None
    fence_len = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        match = FENCE.match(line)
        if match:
            run, info = match.group(1), match.group(2).strip()
            if fence_char is None:
                fence_char, fence_len = run[0], len(run)
                continue
            if run[0] == fence_char and len(run) >= fence_len and not info:
                fence_char, fence_len = None, 0
                continue
            # a shorter/different run inside a fence is content, not a closer
            continue
        if fence_char is None:
            yield lineno, line


def main(roots: list[str]) -> int:
    repo = Path(__file__).resolve().parents[2]
    broken, checked = [], 0
    for root in roots:
        for md in sorted((repo / root).rglob("*.md")):
            text = md.read_text(encoding="utf-8", errors="replace")
            for lineno, line in iter_prose(text):
                for href in LINK.findall(line):
                    if href.startswith(EXTERNAL) or href.startswith("#"):
                        continue
                    target = href.split("#", 1)[0]
                    if not target:
                        continue
                    checked += 1
                    if (md.parent / target).exists():
                        continue
                    if (repo / target.lstrip("/")).exists():
                        continue
                    broken.append(f"{md.relative_to(repo)}:{lineno} -> {href}")

    print(f"checked {checked} inline relative link(s) in: {', '.join(roots)}")
    if broken:
        print(f"\n{len(broken)} broken link(s):")
        for b in broken:
            print(f"  {b}")
        return 1
    print("all inline relative links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["Documentation"]))
