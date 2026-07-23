"""GI-state enums, converters, and validation predicates.

Moved from ``dincli.cli.utils`` (issue #20). Pure module — no ``typer``,
``rich``, or ``dincli.cli.*`` imports. The converters are verbatim copies of the
originals; their behavior must be byte-identical to the utils.py versions.
"""
from __future__ import annotations

from enum import IntEnum

from dincli.sdk.errors import ValidationError

stateDescription = [
    "Awaiting DINTaskAuditor to be set",
    "Awaiting DINTaskCoordinator to be set as slasher",
    "Awaiting DINTaskAuditor to be set as slasher",
    "Awaiting Genesis Model",
    "Genesis Model Created",
    "GI started",
    "DIN aggregators registration started",
    "DIN aggregators registration closed",
    "DIN auditors registration started",
    "DIN auditors registration closed",
    "LM submissions started",
    "LM submissions closed",
    "Auditors batches created",
    "LM submissions evaluation started",
    "LM submissions evaluation closed",
    "T1nT2B created",
    "T1B aggregation started",
    "T1B aggregation done",
    "T2B aggregation started",
    "T2B aggregation done",
    "Auditors slashed",
    "Validators slashed",
    "GI ended",
]

states = [
    "AwaitingDINTaskAuditorToBeSet",
    "AwaitingDINTaskCoordinatorAsSlasher",
    "AwaitingDINTaskAuditorAsSlasher",
    "AwaitingGenesisModel",
    "GenesisModelCreated",
    "GIstarted",
    "DINaggregatorsRegistrationStarted",
    "DINaggregatorsRegistrationClosed",
    "DINauditorsRegistrationStarted",
    "DINauditorsRegistrationClosed",
    "LMSstarted",
    "LMSclosed",
    "AuditorsBatchesCreated",
    "LMSevaluationStarted",
    "LMSevaluationClosed",
    "T1nT2Bcreated",
    "T1AggregationStarted",
    "T1AggregationDone",
    "T2AggregationStarted",
    "T2AggregationDone",
    "AuditorsSlashed",
    "AggregatorsSlashed",
    "GIended",
]

GIstate_to_index = {state: idx for idx, state in enumerate(states)}

GIState = IntEnum("GIState", {name: idx for idx, name in enumerate(states)})


def GIstateToDes(GIstate: int) -> str:
    if 0 <= GIstate < len(stateDescription):
        return stateDescription[GIstate]
    else:
        return f"UnknownState({GIstate})"


def GIstateToStr(GIstate: int) -> str:
    """
    Convert GIstate integer (from Solidity enum) to its string representation.
    Safe against errors by returning 'Unknown' for invalid states.
    """
    if 0 <= GIstate < len(states):
        return states[GIstate]
    else:
        return f"UnknownState({GIstate})"


def GIstatestrToIndex(GIstateStr: str) -> int:
    return GIstate_to_index[GIstateStr]


def validate_gi_state_equals(current: int, expected: str) -> None:
    actual = GIstateToStr(current)
    if actual != expected:
        raise ValidationError(
            f"expected GI state {expected!r}, current is {actual!r}",
            details={"field": "gi_state", "expected": expected, "actual": actual},
        )


def validate_gi_state_at_least(current: int, minimum: str) -> None:
    if current < GIstatestrToIndex(minimum):
        raise ValidationError(
            f"GI state must be at least {minimum!r}, current is {GIstateToStr(current)!r}",
            details={"field": "gi_state", "expected": minimum, "actual": GIstateToStr(current)},
        )
