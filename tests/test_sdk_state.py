"""Tests for dincli.sdk.state (issue #20 Part A)."""
import pytest
from dincli.sdk.errors import ValidationError
from dincli.sdk.state import (
    GIState,
    GIstateToDes,
    GIstateToStr,
    GIstatestrToIndex,
    GIstate_to_index,
    stateDescription,
    states,
    validate_gi_state_equals,
    validate_gi_state_at_least,
)


def test_converters_snapshot():
    assert len(states) == len(stateDescription)
    for i, name in enumerate(states):
        assert GIstateToStr(i) == name
        assert GIstateToDes(i) == stateDescription[i]
        assert GIstatestrToIndex(name) == i
        assert GIstate_to_index[name] == i


def test_GIstateToStr_out_of_range():
    assert GIstateToStr(-1) == "UnknownState(-1)"
    assert GIstateToStr(len(states)) == f"UnknownState({len(states)})"


def test_GIstateToDes_out_of_range():
    assert GIstateToDes(-1) == "UnknownState(-1)"
    assert GIstateToDes(len(states)) == f"UnknownState({len(states)})"


def test_GIstatestrToIndex_invalid():
    with pytest.raises(KeyError):
        GIstatestrToIndex("NoSuchState")


def test_shim_parity():
    from dincli.cli.utils import GIstateToStr as shim_GIstateToStr
    assert shim_GIstateToStr is GIstateToStr


def test_GIState_enum():
    for i, name in enumerate(states):
        assert GIState(i).name == name
        assert GIState(i).value == i
        assert GIState[name].value == i


def test_validate_gi_state_equals_passes():
    validate_gi_state_equals(0, "AwaitingDINTaskAuditorToBeSet")


def test_validate_gi_state_equals_raises():
    with pytest.raises(ValidationError) as exc:
        validate_gi_state_equals(0, "LMSstarted")
    assert exc.value.code == "validation_failed"
    assert exc.value.details == {
        "field": "gi_state",
        "expected": "LMSstarted",
        "actual": "AwaitingDINTaskAuditorToBeSet",
    }


def test_validate_gi_state_at_least_passes_equal():
    validate_gi_state_at_least(5, "GIstarted")


def test_validate_gi_state_at_least_passes_above():
    validate_gi_state_at_least(10, "LMSstarted")


def test_validate_gi_state_at_least_raises():
    with pytest.raises(ValidationError) as exc:
        validate_gi_state_at_least(0, "LMSstarted")
    assert exc.value.code == "validation_failed"
    assert exc.value.details == {
        "field": "gi_state",
        "expected": "LMSstarted",
        "actual": "AwaitingDINTaskAuditorToBeSet",
    }
