"""Tests for dincli.cli.aggregator._agg_commit_hash (issue #156 M-1).

commitT1Aggregation/commitT2Aggregation on DINTaskCoordinator require
commitHash == keccak256(abi.encode(cid, salt, msg.sender, GI, tierKind,
batchId)). This must match byte-for-byte, or every `aggregator reveal-t1`/
`reveal-t2` call ever sent would revert with TC_T1RevealHashMismatch /
TC_T2RevealHashMismatch. Golden values below were computed independently via
`cast abi-encode` + `cast keccak` (not by importing this module's own
encoding logic), so a field-order or type mistake here would be caught
rather than silently agreeing with itself.
"""
from web3 import Web3

from dincli.cli.aggregator import TIER1, TIER2, _agg_commit_hash


def test_agg_commit_hash_matches_cast_golden_vector_tier1():
    cid = Web3.to_bytes(hexstr="0x00000000000000000000000000000000000000000000000000000000000000a1")
    salt = Web3.to_bytes(hexstr="0x0000000000000000000000000000000000000000000000000000000000c0ffee")
    sender = "0x1234567890123456789012345678901234567890"
    gi = 1
    batch_id = 0

    result = _agg_commit_hash(cid, salt, sender, gi, TIER1, batch_id)

    assert result.hex() == "e3d4a8c4ae8d553d5b31a514ea2e99c01ce29e6d0e4949daa9506af57153aa70"


def test_agg_commit_hash_matches_cast_golden_vector_tier2():
    cid = Web3.to_bytes(hexstr="0x00000000000000000000000000000000000000000000000000000000000000b2")
    salt = Web3.to_bytes(hexstr="0x000000000000000000000000000000000000000000000000000000000000dead")
    sender = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    gi = 7
    batch_id = 3

    result = _agg_commit_hash(cid, salt, sender, gi, TIER2, batch_id)

    assert result.hex() == "66a96e7747bc1c4c5a3ca9e051d24e8be0ceff00b21b9ca3be6740db92b59cf0"


def test_agg_commit_hash_changes_with_sender():
    """The entire point of binding msg.sender into the hash (issue #156 M-1,
    hardening #156's own `keccak256(cid, salt)` proposal) is that two
    different senders committing the same (cid, salt) get different hashes
    -- otherwise one could replay the other's commit hash and reveal under
    it. Confirm the Python side actually varies with sender, not just the
    Solidity side."""
    cid = Web3.to_bytes(hexstr="0x00000000000000000000000000000000000000000000000000000000000000a1")
    salt = Web3.to_bytes(hexstr="0x0000000000000000000000000000000000000000000000000000000000c0ffee")
    gi, batch_id = 1, 0

    hash_a = _agg_commit_hash(cid, salt, "0x1234567890123456789012345678901234567890", gi, TIER1, batch_id)
    hash_b = _agg_commit_hash(cid, salt, "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd", gi, TIER1, batch_id)

    assert hash_a != hash_b


def test_agg_commit_hash_changes_with_tier():
    """Same cid/salt/sender/gi/batchId, different tier -> different hash.
    Without this, a T1 commit could be replayed as a T2 reveal (or the
    domain-separation the enum provides would be a no-op)."""
    cid = Web3.to_bytes(hexstr="0x00000000000000000000000000000000000000000000000000000000000000a1")
    salt = Web3.to_bytes(hexstr="0x0000000000000000000000000000000000000000000000000000000000c0ffee")
    sender = "0x1234567890123456789012345678901234567890"
    gi, batch_id = 1, 0

    hash_t1 = _agg_commit_hash(cid, salt, sender, gi, TIER1, batch_id)
    hash_t2 = _agg_commit_hash(cid, salt, sender, gi, TIER2, batch_id)

    assert hash_t1 != hash_t2
