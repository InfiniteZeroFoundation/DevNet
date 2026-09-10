"""Tests for the CI helper scripts in .github/scripts/.

Both become required gates, so they get the same treatment as the code they
guard. The forge-lint gate in particular must fail closed: a parser that
silently skips what it does not understand turns a security check into a
rubber stamp.
"""
import io
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _load(name):
    path = SCRIPTS / name
    spec = spec_from_file_location(f"ci_scripts_{path.stem}", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gate = _load("forge_lint_gate.py")
links = _load("check_doc_links.py")


# --------------------------------------------------------------------------
# forge_lint_gate: fail closed
# --------------------------------------------------------------------------

DIAG = (
    '{{"$message_type":"diagnostic","level":"{level}",'
    '"code":{{"code":"{code}"}},"message":"m",'
    '"spans":[{{"file_name":"src/A.sol","line_start":1,"column_start":2,"is_primary":true}}]}}'
)


def _scan(*lines):
    return gate.scan(io.StringIO("\n".join(lines)))


def test_empty_input_is_a_clean_tree():
    failing, seen = _scan()
    assert not failing and seen == 0


def test_blank_lines_are_ignored():
    failing, seen = _scan("", "   ", "")
    assert not failing and seen == 0


@pytest.mark.parametrize("level", ["warning", "error"])
def test_failing_levels_are_counted(level):
    failing, seen = _scan(DIAG.format(level=level, code="unsafe-typecast"))
    assert seen == 1
    assert failing == {f"{level}[unsafe-typecast]": 1}


@pytest.mark.parametrize("level", ["note", "help", "info"])
def test_non_failing_levels_are_seen_but_not_counted(level):
    failing, seen = _scan(DIAG.format(level=level, code="whatever"))
    assert seen == 1
    assert not failing


def test_unknown_message_type_is_rejected():
    """A new record type means forge's output changed; do not skip it."""
    with pytest.raises(gate.SchemaError, match="unrecognised .message_type"):
        _scan('{"$message_type":"changed-schema","level":"warning"}')


def test_diagnostic_without_level_is_rejected():
    with pytest.raises(gate.SchemaError, match="no `level`"):
        _scan('{"$message_type":"diagnostic"}')


def test_diagnostic_with_unknown_level_is_rejected():
    with pytest.raises(gate.SchemaError, match="unknown severity"):
        _scan(
            '{"$message_type":"diagnostic","level":"catastrophe",'
            '"code":{"code":"x"}}'
        )


def test_diagnostic_without_code_is_rejected():
    with pytest.raises(gate.SchemaError, match="no `code` object"):
        _scan('{"$message_type":"diagnostic","level":"warning"}')


def test_unparseable_line_is_rejected():
    with pytest.raises(gate.SchemaError, match="unparseable JSON"):
        _scan("not json at all")


def test_non_object_json_is_rejected():
    with pytest.raises(gate.SchemaError, match="expected a JSON object"):
        _scan("[1, 2, 3]")


def test_missing_primary_span_still_reports():
    failing, _ = _scan(
        '{"$message_type":"diagnostic","level":"warning",'
        '"code":{"code":"x"},"spans":[]}'
    )
    assert failing == {"warning[x]": 1}


# --------------------------------------------------------------------------
# check_doc_links: fence tracking
# --------------------------------------------------------------------------


def _prose(text):
    return [line for _lineno, line in links.iter_prose(text)]


# Fences are built from explicit repeats rather than written literally: it keeps
# the run lengths visible in each test, and lets this file be quoted inside a
# Markdown fence without terminating it.
BT3, BT4 = "`" * 3, "`" * 4
TL3 = "~" * 3


def test_backtick_fence_contents_are_skipped():
    assert _prose(f"a\n{BT3}\nhidden\n{BT3}\nb") == ["a", "b"]


def test_tilde_fence_is_not_closed_by_a_backtick_run():
    """The naive toggle mis-closed here and leaked the rest of the file."""
    assert _prose(f"a\n{TL3}\ncontains {BT3} inside\nhidden\n{TL3}\nb") == ["a", "b"]


def test_longer_fence_treats_shorter_inner_runs_as_content():
    assert _prose(f"a\n{BT4}\n{BT3}\ninner\n{BT3}\n{BT4}\nb") == ["a", "b"]


def test_closing_fence_may_not_carry_an_info_string():
    assert _prose(f"a\n{BT3}\nhidden\n{BT3} python\nhidden\n{BT3}\nb") == ["a", "b"]


def test_unterminated_fence_swallows_the_rest():
    assert _prose(f"a\n{BT3}\nhidden\nalso hidden") == ["a"]


def test_indented_fence_up_to_three_spaces_counts():
    assert _prose(f"a\n   {BT3}\nhidden\n   {BT3}\nb") == ["a", "b"]


def test_prose_is_yielded_when_there_are_no_fences():
    assert _prose("one\ntwo") == ["one", "two"]
