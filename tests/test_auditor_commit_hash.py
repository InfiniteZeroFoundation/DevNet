"""Tests for dincli.cli.auditor._audit_commit_hash (issue #192).

DINTaskAuditor.revealAuditScore requires commitHash ==
keccak256(abi.encode(score, vote, salt, msg.sender, gi, batchId, modelIndex)).
This must match byte-for-byte, or every `auditor lms-evaluation reveal` would
revert with TA_RevealHashMismatch and the auditor be S1-slashed. Golden values
below were computed independently via `cast abi-encode` + `cast keccak` (not by
importing this module's own encoding logic), so a field-order or type mistake
here would be caught rather than silently agreeing with itself.
"""
from web3 import Web3

from dincli.cli.auditor import _audit_commit_hash

SALT_AA = Web3.to_bytes(hexstr="0x00000000000000000000000000000000000000000000000000000000000000aa")
SENDER_A = "0x1111111111111111111111111111111111111111"
SENDER_B = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"


def test_audit_commit_hash_matches_cast_golden_vector_eligible():
    result = _audit_commit_hash(80, True, SALT_AA, SENDER_A, 3, 1, 7)

    assert result.hex() == "a2683a5803068e12385e07c963a48b966dcfe2543d3b5c29915083d4ebc8c97c"


def test_audit_commit_hash_matches_cast_golden_vector_ineligible():
    salt = Web3.to_bytes(hexstr="0x000000000000000000000000000000000000000000000000000000000000dead")

    result = _audit_commit_hash(35, False, salt, SENDER_B, 7, 0, 2)

    assert result.hex() == "82fd3121412903eecc66c36416d5d850461e4304c1e7fbcd7bbed87c38a5a127"


def test_audit_commit_hash_changes_with_sender():
    """Binding msg.sender is the #192 fix: two auditors committing the same
    (score, vote, salt) must get different hashes, or one could copy the
    other's commit hash and replay its reveal."""
    hash_a = _audit_commit_hash(80, True, SALT_AA, SENDER_A, 3, 1, 7)
    hash_b = _audit_commit_hash(80, True, SALT_AA, SENDER_B, 3, 1, 7)

    assert hash_a != hash_b


def test_audit_commit_hash_changes_with_slot():
    """gi, batchId and modelIndex are bound too, so one commit can't be
    reused for another model, batch or GI."""
    base = _audit_commit_hash(80, True, SALT_AA, SENDER_A, 3, 1, 7)

    assert base != _audit_commit_hash(80, True, SALT_AA, SENDER_A, 4, 1, 7)
    assert base != _audit_commit_hash(80, True, SALT_AA, SENDER_A, 3, 2, 7)
    assert base != _audit_commit_hash(80, True, SALT_AA, SENDER_A, 3, 1, 8)
