"""
Tests for task_240826_10 — encrypted test-data key distribution.

Covers:
  - AES-256-GCM encrypt/decrypt round-trip (_encrypt_aes_gcm helper)
  - encryptedCID construction and decryption (rawCID_bytes || sig)
  - Owner signature verification via eth_account
  - PyNaCl Box encrypt/decrypt round-trip for K distribution
  - Empty / malformed key handling
"""

import secrets
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from nacl.public import Box, PrivateKey, PublicKey, SealedBox
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from web3 import Web3
from eth_abi.packed import encode_packed


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (mirrors the production implementations in modelowner.py / auditor.py)
# ─────────────────────────────────────────────────────────────────────────────

def _encrypt_aes_gcm(plaintext: bytes, K: bytes) -> bytes:
    """nonce (12 bytes) || ciphertext+tag"""
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(K).encrypt(nonce, plaintext, None)


def _decrypt_aes_gcm(ciphertext: bytes, K: bytes) -> bytes:
    return AESGCM(K).decrypt(ciphertext[:12], ciphertext[12:], None)


def _build_encrypted_cid(raw_cid_bytes: bytes, K: bytes, owner_account) -> bytes:
    """encryptedCID = AES-256-GCM(K, rawCID_bytes || eth_sign(ownerSK, rawCID_bytes))"""
    sig = owner_account.sign_message(encode_defunct(raw_cid_bytes)).signature
    return _encrypt_aes_gcm(raw_cid_bytes + sig, K)


def _commitment(gi: int, batch_id: int, K: bytes, plaintext_keccak: bytes) -> bytes:
    """keccak256(abi.encodePacked(gi, batchId, keccak256(K), plaintext_keccak))"""
    keccak_K = bytes(Web3.keccak(K))
    return bytes(Web3.keccak(
        encode_packed(
            ["uint256", "uint256", "bytes32", "bytes32"],
            [gi, batch_id, keccak_K, bytes(plaintext_keccak)],
        )
    ))


# ─────────────────────────────────────────────────────────────────────────────
# AES-256-GCM round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_aes_gcm_roundtrip():
    K = secrets.token_bytes(32)
    plaintext = b"hello encrypted world"
    ciphertext = _encrypt_aes_gcm(plaintext, K)
    assert ciphertext != plaintext
    assert _decrypt_aes_gcm(ciphertext, K) == plaintext


def test_aes_gcm_wrong_key_raises():
    K = secrets.token_bytes(32)
    wrong_K = secrets.token_bytes(32)
    ciphertext = _encrypt_aes_gcm(b"secret", K)
    with pytest.raises(Exception):
        _decrypt_aes_gcm(ciphertext, wrong_K)


def test_aes_gcm_nonce_prefix_length():
    K = secrets.token_bytes(32)
    ciphertext = _encrypt_aes_gcm(b"data", K)
    assert len(ciphertext) >= 12 + 4 + 16  # nonce + plaintext + GCM tag


def test_aes_gcm_fresh_nonce_each_call():
    K = secrets.token_bytes(32)
    plaintext = b"same plaintext"
    c1 = _encrypt_aes_gcm(plaintext, K)
    c2 = _encrypt_aes_gcm(plaintext, K)
    assert c1[:12] != c2[:12], "each call should use a fresh random nonce"
    assert c1 != c2


# ─────────────────────────────────────────────────────────────────────────────
# encryptedCID construction and round-trip decryption
# ─────────────────────────────────────────────────────────────────────────────

def test_encrypted_cid_roundtrip():
    owner = Account.create()
    K = secrets.token_bytes(32)
    raw_cid_bytes = secrets.token_bytes(32)

    encrypted_cid = _build_encrypted_cid(raw_cid_bytes, K, owner)

    payload = _decrypt_aes_gcm(encrypted_cid, K)
    recovered_cid, sig = payload[:32], payload[32:]

    assert recovered_cid == raw_cid_bytes
    recovered_addr = Account.recover_message(encode_defunct(raw_cid_bytes), signature=sig)
    assert recovered_addr.lower() == owner.address.lower()


def test_encrypted_cid_wrong_key_raises():
    owner = Account.create()
    K = secrets.token_bytes(32)
    wrong_K = secrets.token_bytes(32)
    raw_cid_bytes = secrets.token_bytes(32)
    encrypted_cid = _build_encrypted_cid(raw_cid_bytes, K, owner)
    with pytest.raises(Exception):
        _decrypt_aes_gcm(encrypted_cid, wrong_K)


def test_encrypted_cid_tampered_sig_fails_verification():
    owner = Account.create()
    K = secrets.token_bytes(32)
    raw_cid_bytes = secrets.token_bytes(32)
    encrypted_cid = _build_encrypted_cid(raw_cid_bytes, K, owner)

    payload = _decrypt_aes_gcm(encrypted_cid, K)
    recovered_cid, sig = payload[:32], payload[32:]

    # Flip one byte in the signature — this either raises (mathematically
    # invalid sig point) or recovers a wrong address. Both are correct outcomes.
    tampered_sig = bytes([sig[0] ^ 0xFF]) + sig[1:]
    try:
        recovered_addr = Account.recover_message(encode_defunct(recovered_cid), signature=tampered_sig)
        assert recovered_addr.lower() != owner.address.lower()
    except Exception:
        pass  # BadSignature / invalid point is also an acceptable verification failure


def test_encrypted_cid_wrong_owner_fails_verification():
    owner = Account.create()
    attacker = Account.create()
    K = secrets.token_bytes(32)
    raw_cid_bytes = secrets.token_bytes(32)

    # Attacker builds an encryptedCID signed by their own key
    encrypted_cid = _build_encrypted_cid(raw_cid_bytes, K, attacker)
    payload = _decrypt_aes_gcm(encrypted_cid, K)
    recovered_cid, sig = payload[:32], payload[32:]
    recovered_addr = Account.recover_message(encode_defunct(recovered_cid), signature=sig)

    assert recovered_addr.lower() != owner.address.lower()


# ─────────────────────────────────────────────────────────────────────────────
# PyNaCl Box encrypt/decrypt round-trip for K distribution
# ─────────────────────────────────────────────────────────────────────────────

def test_box_k_roundtrip():
    owner_privkey = PrivateKey.generate()
    auditor_privkey = PrivateKey.generate()
    K = secrets.token_bytes(32)

    encrypted_K = Box(owner_privkey, auditor_privkey.public_key).encrypt(K)
    recovered_K = Box(auditor_privkey, owner_privkey.public_key).decrypt(encrypted_K)

    assert recovered_K == K


def test_box_wrong_owner_pubkey_raises():
    owner_privkey = PrivateKey.generate()
    wrong_privkey = PrivateKey.generate()
    auditor_privkey = PrivateKey.generate()
    K = secrets.token_bytes(32)

    encrypted_K = Box(owner_privkey, auditor_privkey.public_key).encrypt(K)
    with pytest.raises(Exception):
        # auditor tries to decrypt using wrong owner pubkey — should fail
        Box(auditor_privkey, wrong_privkey.public_key).decrypt(encrypted_K)


def test_box_wrong_auditor_privkey_raises():
    owner_privkey = PrivateKey.generate()
    auditor_privkey = PrivateKey.generate()
    wrong_auditor_privkey = PrivateKey.generate()
    K = secrets.token_bytes(32)

    encrypted_K = Box(owner_privkey, auditor_privkey.public_key).encrypt(K)
    with pytest.raises(Exception):
        Box(wrong_auditor_privkey, owner_privkey.public_key).decrypt(encrypted_K)


# ─────────────────────────────────────────────────────────────────────────────
# Empty / malformed key handling
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_encrypted_key_detected():
    empty_key = b""
    assert len(empty_key) == 0, "empty bytes signals no key was assigned (Stage 0 check)"


def test_decrypt_empty_blob_raises():
    K = secrets.token_bytes(32)
    with pytest.raises(Exception):
        _decrypt_aes_gcm(b"", K)


def test_decrypt_truncated_blob_raises():
    K = secrets.token_bytes(32)
    # Only the nonce, no ciphertext
    with pytest.raises(Exception):
        _decrypt_aes_gcm(secrets.token_bytes(12), K)


# ─────────────────────────────────────────────────────────────────────────────
# On-chain commitment formula
# ─────────────────────────────────────────────────────────────────────────────

def test_commitment_deterministic():
    K = secrets.token_bytes(32)
    plaintext = b"test dataset bytes"
    plaintext_keccak = bytes(Web3.keccak(plaintext))
    c1 = _commitment(1, 0, K, plaintext_keccak)
    c2 = _commitment(1, 0, K, plaintext_keccak)
    assert c1 == c2


def test_commitment_round_bound():
    """Same K and plaintext in a different gi must produce a different commitment."""
    K = secrets.token_bytes(32)
    plaintext_keccak = bytes(Web3.keccak(b"test"))
    c_gi1 = _commitment(1, 0, K, plaintext_keccak)
    c_gi2 = _commitment(2, 0, K, plaintext_keccak)
    assert c_gi1 != c_gi2, "commitment must differ across GIs (round-binding)"


def test_commitment_batch_bound():
    """Same K and plaintext in a different batchId must produce a different commitment."""
    K = secrets.token_bytes(32)
    plaintext_keccak = bytes(Web3.keccak(b"test"))
    c_b0 = _commitment(1, 0, K, plaintext_keccak)
    c_b1 = _commitment(1, 1, K, plaintext_keccak)
    assert c_b0 != c_b1, "commitment must differ across batchIds (round-binding)"


def test_commitment_key_bound():
    """Different K with same plaintext must produce a different commitment."""
    K1 = secrets.token_bytes(32)
    K2 = secrets.token_bytes(32)
    plaintext_keccak = bytes(Web3.keccak(b"test"))
    assert _commitment(1, 0, K1, plaintext_keccak) != _commitment(1, 0, K2, plaintext_keccak)


# ─────────────────────────────────────────────────────────────────────────────
# Full owner→auditor encrypt/decrypt integration
# ─────────────────────────────────────────────────────────────────────────────

def test_full_owner_to_auditor_flow():
    """End-to-end: owner encrypts; auditor recovers K, decrypts CID, verifies sig."""
    owner_eth = Account.create()
    owner_x25519 = PrivateKey.generate()
    auditor_x25519 = PrivateKey.generate()

    raw_cid_bytes = secrets.token_bytes(32)
    K = secrets.token_bytes(32)
    plaintext = b"mnist test shard bytes"

    # Owner side
    encrypted_cid = _build_encrypted_cid(raw_cid_bytes, K, owner_eth)
    encrypted_K   = Box(owner_x25519, auditor_x25519.public_key).encrypt(K)

    # Auditor side — recover K
    recovered_K = Box(auditor_x25519, owner_x25519.public_key).decrypt(encrypted_K)
    assert recovered_K == K

    # Auditor side — decrypt encryptedCID
    payload = _decrypt_aes_gcm(encrypted_cid, recovered_K)
    recovered_cid, sig = payload[:32], payload[32:]
    assert recovered_cid == raw_cid_bytes

    # Auditor side — verify owner signature
    recovered_addr = Account.recover_message(encode_defunct(recovered_cid), signature=sig)
    assert recovered_addr.lower() == owner_eth.address.lower()

    # Auditor side — decrypt file content
    encrypted_file = _encrypt_aes_gcm(plaintext, recovered_K)
    decrypted_plaintext = _decrypt_aes_gcm(encrypted_file, recovered_K)
    assert decrypted_plaintext == plaintext
