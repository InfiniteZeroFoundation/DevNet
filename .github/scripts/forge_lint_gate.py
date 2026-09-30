#!/usr/bin/env python3
"""Fail closed on `forge lint --json` output.

Reads JSON-lines diagnostics on stdin and exits non-zero if anything is wrong.
This is a required, security-sensitive gate, so it validates the *schema* it was
written against rather than only the JSON syntax:

  * an unparseable line                     -> fail
  * an unrecognised `$message_type`         -> fail (forge's output changed)
  * a diagnostic missing `level` or a code  -> fail (schema drifted)
  * a diagnostic whose `level` is unknown   -> fail (new severity, unclassified)
  * any diagnostic at `warning` or `error`  -> fail (the actual findings)

Empty input is valid and means a clean tree. The caller must check forge's own
exit status separately; this script never sees it.

Pinned against Foundry v1.7.1, whose `forge lint --json` emits only
`$message_type: "diagnostic"` records. A new record type is treated as a
breaking change to be reviewed, not as something to skip silently.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

# Severities forge can emit, partitioned into what fails and what does not.
FAIL_LEVELS = frozenset({"warning", "error"})
PASS_LEVELS = frozenset({"note", "help", "info"})
KNOWN_LEVELS = FAIL_LEVELS | PASS_LEVELS

# Record types this parser was written against.
KNOWN_MESSAGE_TYPES = frozenset({"diagnostic"})


class SchemaError(Exception):
    """forge's output does not match what this gate was written against."""


def _diagnostic_code(record: dict) -> str:
    code = record.get("code")
    if not isinstance(code, dict):
        raise SchemaError("diagnostic has no `code` object")
    value = code.get("code")
    if not isinstance(value, str) or not value:
        raise SchemaError("diagnostic `code.code` is missing or not a string")
    return value


def _primary_location(record: dict) -> str:
    for span in record.get("spans") or []:
        if isinstance(span, dict) and span.get("is_primary"):
            return f"{span.get('file_name')}:{span.get('line_start')}:{span.get('column_start')}"
    return "<no primary span>"


def scan(stream) -> tuple[Counter, int]:
    """Return (failing counts by level[code], number of diagnostics seen).

    Raises SchemaError on anything unrecognised.
    """
    failing: Counter[str] = Counter()
    seen = 0
    for lineno, raw in enumerate(stream, 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SchemaError(f"line {lineno}: unparseable JSON ({exc})") from exc
        if not isinstance(record, dict):
            raise SchemaError(f"line {lineno}: expected a JSON object, got {type(record).__name__}")

        message_type = record.get("$message_type")
        if message_type not in KNOWN_MESSAGE_TYPES:
            raise SchemaError(
                f"line {lineno}: unrecognised $message_type {message_type!r} — "
                "forge's lint output has changed; review before trusting this gate"
            )

        seen += 1
        level = record.get("level")
        if not isinstance(level, str) or not level:
            raise SchemaError(f"line {lineno}: diagnostic has no `level`")
        if level not in KNOWN_LEVELS:
            raise SchemaError(
                f"line {lineno}: unknown severity {level!r} — classify it in "
                "FAIL_LEVELS or PASS_LEVELS before trusting this gate"
            )
        code = _diagnostic_code(record)

        if level in FAIL_LEVELS:
            failing[f"{level}[{code}]"] += 1
            print(f"{_primary_location(record)}: {level}[{code}] {record.get('message')}")

    return failing, seen


def main() -> int:
    try:
        failing, seen = scan(sys.stdin)
    except SchemaError as exc:
        print(f"::error::forge lint output failed validation: {exc}")
        return 1

    if failing:
        total = sum(failing.values())
        print(f"\n::error::forge lint reported {total} finding(s) at {sorted(FAIL_LEVELS)}")
        for key, count in sorted(failing.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {count:4d}  {key}")
        return 1

    print(f"forge lint: {seen} diagnostic(s), none at {sorted(FAIL_LEVELS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
