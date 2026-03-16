"""Gerenciamento de certificados A1 (.pfx) — cifragem AES-256-GCM.

Versioning scheme for encrypted data:
  v1: = legacy AES-256-CBC (read-only, for migration)
  v2: = AES-256-GCM with random salt, PBKDF2 @ 600k iterations

v2 binary layout (stored as hex string):
  salt(16 bytes) + nonce(12 bytes) + ciphertext + tag(16 bytes)
"""

import hashlib
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime

from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import pkcs12

_PBKDF2_ITERATIONS_V2 = 600_000
_PBKDF2_ITERATIONS_V1 = 100_000
_SALT_LEN = 16
_NONCE_LEN = 12
_VERSION_PREFIX_V1 = "v1:"
_VERSION_PREFIX_V2 = "v2:"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _derive_key_v1(tenant_id: str) -> bytes:
    """Legacy key derivation (v1) — hardcoded salt, 100k iterations."""
    secret = os.environ["CERT_MASTER_SECRET"]
    return hashlib.pbkdf2_hmac(
        "sha256",
        (tenant_id + secret).encode(),
        b"dfeaxis_salt_v1",
        _PBKDF2_ITERATIONS_V1,
    )


def _derive_key_v2(tenant_id: str, salt: bytes) -> bytes:
    """v2 key derivation — random salt, 600k iterations, domain-separated."""
    secret = os.environ["CERT_MASTER_SECRET"]
    # Domain separation: use structured input instead of simple concatenation
    ikm = f"dfeaxis:cert:v2:{tenant_id}:{secret}".encode()
    return hashlib.pbkdf2_hmac(
        "sha256",
        ikm,
        salt,
        _PBKDF2_ITERATIONS_V2,
    )


# ---------------------------------------------------------------------------
# v1 (legacy) helpers — decrypt only
# ---------------------------------------------------------------------------

def _decrypt_cbc(ciphertext: bytes, iv: bytes, key: bytes) -> bytes:
    """AES-256-CBC decrypt with PKCS7 unpadding (v1 legacy)."""
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


# ---------------------------------------------------------------------------
# v2 (GCM) helpers
# ---------------------------------------------------------------------------

def _encrypt_gcm(plaintext: bytes, key: bytes) -> tuple[bytes, bytes]:
    """AES-256-GCM encrypt. Returns (nonce, ciphertext_with_tag)."""
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, None)
    return nonce, ct_with_tag


def _decrypt_gcm(nonce: bytes, ct_with_tag: bytes, key: bytes) -> bytes:
    """AES-256-GCM decrypt."""
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct_with_tag, None)


# ---------------------------------------------------------------------------
# PFX encrypt / decrypt  (public API)
# ---------------------------------------------------------------------------

def encrypt_pfx(pfx_bytes: bytes, tenant_id: str) -> tuple[bytes, dict]:
    """Encrypt PFX content with AES-256-GCM (v2).

    Returns:
        (encrypted_blob, metadata) where:
          - encrypted_blob is the raw bytes: salt(16) + nonce(12) + ciphertext + tag(16)
          - metadata is {"version": "v2"}
    """
    salt = os.urandom(_SALT_LEN)
    key = _derive_key_v2(tenant_id, salt)
    nonce, ct_with_tag = _encrypt_gcm(pfx_bytes, key)

    # Pack: salt + nonce + ciphertext_with_tag
    blob = salt + nonce + ct_with_tag

    return blob, {"version": "v2"}


def decrypt_pfx(encrypted: bytes, iv_or_none, tenant_id: str) -> bytes:
    """Decrypt PFX content, auto-detecting version.

    For backwards compatibility this accepts two calling conventions:
      - v2: iv_or_none can be None (all data is in `encrypted`)
      - v1 legacy: iv_or_none is the 16-byte CBC IV

    The version is determined by checking if the data stored in the DB has a
    version prefix. Callers that read from the DB should pass the hex-decoded
    blob as `encrypted`. If the DB row still has a separate `pfx_iv` column
    (legacy v1 data), pass it as `iv_or_none`.
    """
    # Try to detect version from the encrypted blob size / structure.
    # v2 blobs are at least SALT_LEN + NONCE_LEN + 16 (tag) = 44 bytes,
    # and the caller sets iv_or_none to None for v2 data.
    if iv_or_none is None:
        # v2 path
        salt = encrypted[:_SALT_LEN]
        nonce = encrypted[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
        ct_with_tag = encrypted[_SALT_LEN + _NONCE_LEN :]
        key = _derive_key_v2(tenant_id, salt)
        return _decrypt_gcm(nonce, ct_with_tag, key)
    else:
        # v1 legacy path
        key = _derive_key_v1(tenant_id)
        return _decrypt_cbc(encrypted, iv_or_none, key)


# ---------------------------------------------------------------------------
# Password encrypt / decrypt  (public API)
# ---------------------------------------------------------------------------

def encrypt_password(password: str, tenant_id: str) -> str:
    """Encrypt a password string with AES-256-GCM (v2).

    Returns a version-prefixed hex string: "v2:<salt+nonce+ct+tag as hex>"
    """
    salt = os.urandom(_SALT_LEN)
    key = _derive_key_v2(tenant_id, salt)
    nonce, ct_with_tag = _encrypt_gcm(password.encode("utf-8"), key)
    blob = salt + nonce + ct_with_tag
    return _VERSION_PREFIX_V2 + blob.hex()


def decrypt_password(encrypted_hex: str, tenant_id: str) -> str:
    """Decrypt a password string, auto-detecting version.

    Accepts:
      "v2:..." — new GCM format
      "v1:..." — legacy CBC format (iv_hex:ciphertext_hex)
      bare hex  — treated as legacy v1 with embedded iv (first 32 hex chars = 16 bytes IV)
    """
    if encrypted_hex.startswith(_VERSION_PREFIX_V2):
        blob = bytes.fromhex(encrypted_hex[len(_VERSION_PREFIX_V2) :])
        salt = blob[:_SALT_LEN]
        nonce = blob[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
        ct_with_tag = blob[_SALT_LEN + _NONCE_LEN :]
        key = _derive_key_v2(tenant_id, salt)
        return _decrypt_gcm(nonce, ct_with_tag, key).decode("utf-8")

    elif encrypted_hex.startswith(_VERSION_PREFIX_V1):
        payload = encrypted_hex[len(_VERSION_PREFIX_V1) :]
        iv_hex, ct_hex = payload.split(":", 1)
        iv = bytes.fromhex(iv_hex)
        ct = bytes.fromhex(ct_hex)
        key = _derive_key_v1(tenant_id)
        return _decrypt_cbc(ct, iv, key).decode("utf-8")

    else:
        # Bare legacy: first 32 hex chars (16 bytes) = IV, rest = ciphertext
        iv = bytes.fromhex(encrypted_hex[:32])
        ct = bytes.fromhex(encrypted_hex[32:])
        key = _derive_key_v1(tenant_id)
        return _decrypt_cbc(ct, iv, key).decode("utf-8")


# ---------------------------------------------------------------------------
# Certificate info extraction (unchanged)
# ---------------------------------------------------------------------------

def extract_cert_info(pfx_bytes: bytes, password: str) -> dict:
    """Extrai informações do certificado A1 (.pfx)."""
    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        pfx_bytes, password.encode()
    )

    if certificate is None:
        raise ValueError("Certificado não encontrado no arquivo .pfx")

    subject = certificate.subject
    # Extrai CN (Common Name) do subject
    cn = None
    for attr in subject:
        if attr.oid.dotted_string == "2.5.4.3":  # CN OID
            cn = attr.value
            break

    return {
        "subject_cn": cn,
        "valid_from": certificate.not_valid_before_utc.date(),
        "valid_until": certificate.not_valid_after_utc.date(),
        "serial_number": str(certificate.serial_number),
    }


# ---------------------------------------------------------------------------
# Temp cert files context manager (unchanged)
# ---------------------------------------------------------------------------

@contextmanager
def temp_cert_files(pfx_bytes: bytes, password: str):
    """Context manager que extrai cert e key do .pfx para arquivos temporários.

    Usa tempfile com cleanup garantido — NUNCA deixa arquivos em disco.
    Yield: (cert_path, key_path)
    """
    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        pfx_bytes, password.encode()
    )

    if private_key is None or certificate is None:
        raise ValueError("Certificado ou chave privada não encontrados no .pfx")

    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )

    cert_file = None
    key_file = None
    try:
        cert_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False, mode="wb"
        )
        cert_file.write(cert_pem)
        cert_file.flush()
        cert_file.close()

        key_file = tempfile.NamedTemporaryFile(
            suffix=".pem", delete=False, mode="wb"
        )
        key_file.write(key_pem)
        key_file.flush()
        key_file.close()

        yield cert_file.name, key_file.name
    finally:
        if cert_file and os.path.exists(cert_file.name):
            os.unlink(cert_file.name)
        if key_file and os.path.exists(key_file.name):
            os.unlink(key_file.name)
