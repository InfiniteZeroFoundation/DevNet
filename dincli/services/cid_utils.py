"""
CID ↔ bytes32 conversion utilities.

Kept in a separate module (no imports from dincli.cli) so that both
dincli.cli.utils and dincli.services.ipfs can import from here without
creating a circular dependency.
"""
import cid as _cid


def get_bytes32_from_cid(cid_str: str) -> str:
    """
    Extracts the raw 32-byte SHA2-256 digest (hex) from a CID string.
    Returns 64 hex characters (without the '1220' multihash prefix).
    """
    cid_obj = _cid.make_cid(cid_str)

    # Full multihash bytes include '1220' prefix (12 = sha2-256, 20 = 32-byte length)
    full_multihash_hex = cid_obj.multihash.hex()

    # Strip the first 4 hex characters ('1220') to get only the 32-byte digest
    return full_multihash_hex[4:]


def get_cid_from_bytes32(byte32_hex: str, version: int = 1, encoding: str = "base32") -> str:
    """
    Converts a raw 32-byte SHA2-256 digest (hex) back into a CID.

    Args:
        byte32_hex: 64-character hex string (raw digest, NO '1220' prefix).
        version: 0 or 1.
        encoding: 'base32' (recommended for v1) or 'base58btc'.

    Returns:
        The CID string.
    """
    from multibase import encode  # local import keeps top-level deps minimal

    # Reconstruct the full multihash: 12 = sha2-256, 20 = 32-byte length
    multihash_hex = "1220" + str(byte32_hex)
    multihash_bytes = bytes.fromhex(multihash_hex)

    # Build CIDv1 (dag-pb is standard for IPFS file data)
    cid_v1 = _cid.CIDv1(codec="dag-pb", multihash=multihash_bytes)

    if version == 0:
        return str(cid_v1.to_v0())

    if version == 1:
        if encoding == "base32":
            # CIDv1 raw bytes: <version varint 0x01><codec varint 0x70><multihash>
            raw_cid_bytes = b"\x01" + b"\x70" + multihash_bytes
            return encode("base32", raw_cid_bytes).decode("ascii")
        if encoding == "base58btc":
            return str(cid_v1)
        raise ValueError("encoding must be 'base32' or 'base58btc'")

    raise ValueError("version must be 0 or 1")

def get_cidv1base32_from_cid(cid_str: str) -> str:
    """
    Extracts the CIDv1 from a CID string.
    """

    # Base32 CIDv1 starts with 'bafy' and uses [a-z2-7]
    if cid_str.startswith('bafy') and all(c in 'abcdefghijklmnopqrstuvwxyz234567' for c in cid_str[4:]):
        return cid_str

    bytes32_hex = get_bytes32_from_cid(cid_str)
    return get_cid_from_bytes32(bytes32_hex, version=1, encoding="base32")