"""Gerenciamento de certificados A1 (.pfx) — cifragem AES-256-CBC."""

import hashlib
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime

from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import pkcs12


def _derive_key(tenant_id: str, purpose: str = "pfx") -> bytes:
    """Deriva chave AES-256 do tenant_id + CERT_MASTER_SECRET."""
    secret = os.environ["CERT_MASTER_SECRET"]
    salt = f"dfeaxis_{purpose}_v1".encode()
    return hashlib.pbkdf2_hmac(
        "sha256",
        (tenant_id + secret).encode(),
        salt,
        100_000,
    )


def encrypt_pfx(pfx_bytes: bytes, tenant_id: str) -> tuple[bytes, bytes]:
    """Cifra o conteúdo do .pfx com AES-256-CBC. Retorna (encrypted, iv)."""
    key = _derive_key(tenant_id)
    iv = os.urandom(16)

    padder = padding.PKCS7(128).padder()
    padded = padder.update(pfx_bytes) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    return encrypted, iv


def decrypt_pfx(encrypted: bytes, iv: bytes, tenant_id: str) -> bytes:
    """Decifra o conteúdo do .pfx."""
    key = _derive_key(tenant_id)

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def encrypt_password(password: str, tenant_id: str) -> str:
    """Cifra a senha do .pfx com AES-256-CBC. Retorna iv_hex:encrypted_hex."""
    key = _derive_key(tenant_id, purpose="pwd")
    iv = os.urandom(16)

    padder = padding.PKCS7(128).padder()
    padded = padder.update(password.encode()) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    return f"{iv.hex()}:{encrypted.hex()}"


def decrypt_password(encrypted_str: str, tenant_id: str) -> str:
    """Decifra a senha do .pfx. Formato: iv_hex:encrypted_hex."""
    iv_hex, enc_hex = encrypted_str.split(":", 1)
    iv = bytes.fromhex(iv_hex)
    encrypted = bytes.fromhex(enc_hex)

    key = _derive_key(tenant_id, purpose="pwd")

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode()


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
