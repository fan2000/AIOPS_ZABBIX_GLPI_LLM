"""Utilitaires cryptographiques MFA TOTP (RFC 6238), chiffrement Fernet, codes de secours et politique mot de passe."""

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from typing import List, Optional
from urllib.parse import quote
from cryptography.fernet import Fernet, InvalidToken
from packages.security.src.jwt import SECRET_KEY

_RECOVERY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _fernet_instance() -> Fernet:
    """Dérive une clé Fernet déterministe (32 octets URL-safe) depuis SECRET_KEY."""
    digest = hashlib.sha256(f"aiops-mfa-secret-key:{SECRET_KEY}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_mfa_secret(plain_secret: str) -> str:
    """Chiffre un secret TOTP avec préfixe 'enc:' via Fernet AES-CBC+HMAC."""
    token = _fernet_instance().encrypt(plain_secret.encode("utf-8")).decode("ascii")
    return f"enc:{token}"


def decrypt_mfa_secret(stored_secret: str) -> str:
    """Déchiffre un secret TOTP stocké (rétrocompatible si non chiffré)."""
    if not stored_secret:
        return ""
    if stored_secret.startswith("enc:"):
        raw = stored_secret[4:].encode("ascii")
        try:
            return _fernet_instance().decrypt(raw).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Secret MFA illisible ou altéré") from exc
    return stored_secret


def generate_totp_secret(num_bytes: int = 20) -> str:
    """Génère une clé secrète aléatoire encodée en Base32 RFC 4648 sans padding."""
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode("ascii").rstrip("=")


def build_otpauth_uri(secret: str, username: str, issuer: str = "AI IT Operations") -> str:
    """Construit l'URI standard otpauth:// compatible Google Authenticator, Authy & Microsoft Authenticator."""
    label = quote(f"{issuer}:{username}", safe=":")
    issuer_q = quote(issuer, safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer_q}&algorithm=SHA1&digits=6&period=30"


def _decode_base32_secret(secret: str) -> bytes:
    cleaned = re.sub(r"[\s-]+", "", secret or "").upper()
    if not cleaned:
        raise ValueError("Secret TOTP vide")
    padding = (-len(cleaned)) % 8
    if padding:
        cleaned += "=" * padding
    return base64.b32decode(cleaned, casefold=True)


def generate_totp_code(
    secret: str,
    for_time: Optional[int] = None,
    interval: int = 30,
    digits: int = 6,
) -> str:
    """Calcule un code TOTP RFC 6238 / HOTP RFC 4226 HMAC-SHA1 à 6 chiffres."""
    key = _decode_base32_secret(secret)
    ts = int(for_time if for_time is not None else time.time())
    counter = ts // interval
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    otp = binary % (10 ** digits)
    return f"{otp:0{digits}d}"


def verify_totp_code(
    secret: str,
    code: str,
    window: int = 1,
    for_time: Optional[int] = None,
    interval: int = 30,
    digits: int = 6,
) -> bool:
    """Vérifie un code TOTP en temps constant sur une tolérance de ±window périodes (30s)."""
    normalized = re.sub(r"[\s-]+", "", code or "")
    if not normalized.isdigit() or len(normalized) != digits:
        return False
    base_ts = int(for_time if for_time is not None else time.time())
    try:
        for offset in range(-window, window + 1):
            candidate = generate_totp_code(
                secret=secret,
                for_time=base_ts + offset * interval,
                interval=interval,
                digits=digits,
            )
            if hmac.compare_digest(normalized, candidate):
                return True
    except Exception:
        return False
    return False


def generate_recovery_codes(count: int = 8) -> List[str]:
    """Génère des codes de secours à usage unique lisibles (format XXXX-XXXX)."""
    codes: List[str] = []
    for _ in range(count):
        left = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))
        right = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))
        codes.append(f"{left}-{right}")
    return codes


def normalize_recovery_code(code: str) -> str:
    """Normalise un code de secours saisi (majuscules sans tirets ni espaces)."""
    return re.sub(r"[\s-]+", "", (code or "").strip().upper())


def hash_recovery_code(code: str) -> str:
    """Empreinte SHA-256 d'un code de secours normalisé."""
    return hashlib.sha256(normalize_recovery_code(code).encode("utf-8")).hexdigest()


def hash_refresh_token(raw_token: str) -> str:
    """Empreinte SHA-256 d'un Refresh Token avant persistance PostgreSQL."""
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


def validate_password_strength(password: str) -> Optional[str]:
    """Valide la complexité minimale d'un mot de passe (CWE-521)."""
    if not password or len(password) < 10:
        return "Le mot de passe doit contenir au moins 10 caractères."
    if not re.search(r"[a-z]", password):
        return "Le mot de passe doit contenir au moins une lettre minuscule."
    if not re.search(r"[A-Z]", password):
        return "Le mot de passe doit contenir au moins une lettre majuscule."
    if not re.search(r"[0-9]", password):
        return "Le mot de passe doit contenir au moins un chiffre."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Le mot de passe doit contenir au moins un caractère spécial (!@#$%^&*...)."
    return None
