"""get_cid_from_bytes32 must accept a 0x-prefixed digest.

`auditor lms-evaluation evaluate` once built "1220" + "0x<digest>", which
fromhex() rejects at position 5, so every auditor failed to decrypt its test
data and nobody committed a score.
"""

import pytest

from dincli.services.cid_utils import get_bytes32_from_cid, get_cid_from_bytes32

# A raw test-data CID the model owner uploaded in a full-GI run.
RAW_CID = "bafybeieoufpd24dlkgvf73tkk4bmuf2snfcs5skw34yashifrwvtoc3qsm"


@pytest.mark.parametrize("prefix", ["", "0x", "0X"])
def test_digest_round_trips_with_or_without_0x(prefix):
    digest = get_bytes32_from_cid(RAW_CID)
    assert get_cid_from_bytes32(prefix + digest) == RAW_CID


def test_raw_bytes_hex_as_evaluate_passes_it():
    raw_cid_bytes = bytes.fromhex(get_bytes32_from_cid(RAW_CID))
    assert get_cid_from_bytes32(raw_cid_bytes.hex()) == RAW_CID
    assert get_cid_from_bytes32("0x" + raw_cid_bytes.hex()) == RAW_CID
