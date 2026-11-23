"""Tests unitaires P2/IAM : TOTP RFC 6238, chiffrement Fernet, codes de secours, force mot de passe."""

from unittest.mock import AsyncMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import pytest
from apps.api.src.dependencies.auth import get_current_user
from packages.security.src.jwt import create_mfa_challenge_token, generate_refresh_token
from packages.security.src.mfa import (
    build_otpauth_uri,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_recovery_codes,
    generate_totp_code,
    generate_totp_secret,
    hash_recovery_code,
    hash_refresh_token,
    validate_password_strength,
    verify_totp_code,
)


def test_totp_rfc6238_generation_and_window_tolerance():
    """Valide génération Base32, URI otpauth:// et fenêtre de tolérance ±30s en temps constant."""
    secret = generate_totp_secret()
    assert len(secret) >= 32
    uri = build_otpauth_uri(secret, "ops_admin", "AI IT Operations")
    assert uri.startswith("otpauth://totp/")
    assert f"secret={secret}" in uri

    base_time = 1_700_000_010
    code = generate_totp_code(secret, for_time=base_time)
    assert len(code) == 6 and code.isdigit()
    assert verify_totp_code(secret, code, window=1, for_time=base_time) is True
    assert verify_totp_code(secret, code, window=1, for_time=base_time + 28) is True
    assert verify_totp_code(secret, code, window=1, for_time=base_time - 25) is True
    assert verify_totp_code(secret, code, window=1, for_time=base_time + 95) is False
    assert verify_totp_code(secret, "000000" if code != "000000" else "999999", window=1, for_time=base_time) is False


def test_fernet_mfa_secret_encryption_roundtrip():
    """Le secret TOTP chiffré en base commence par 'enc:' et détecte toute altération."""
    plain = generate_totp_secret()
    encrypted = encrypt_mfa_secret(plain)
    assert encrypted.startswith("enc:")
    assert encrypted != plain
    assert decrypt_mfa_secret(encrypted) == plain
    assert decrypt_mfa_secret(plain) == plain  # Rétrocompatibilité si non chiffré

    with pytest.raises(ValueError):
        decrypt_mfa_secret("enc:not-a-valid-fernet-token")


def test_recovery_codes_and_refresh_token_hashing():
    """Les codes de secours sont normalisés (casse/tirets) et les refresh tokens hachés SHA-256."""
    codes = generate_recovery_codes(8)
    assert len(codes) == 8
    assert all("-" in c and len(c) == 9 for c in codes)
    c0 = codes[0]
    assert hash_recovery_code(c0) == hash_recovery_code(c0.lower().replace("-", " "))

    rt = generate_refresh_token()
    assert rt.startswith("aiops_rt_")
    assert len(hash_refresh_token(rt)) == 64


def test_password_strength_policy():
    """Impose 10+ caractères, majuscule, minuscule, chiffre et caractère spécial."""
    assert validate_password_strength("short1!A") is not None
    assert validate_password_strength("alllowercase123!") is not None
    assert validate_password_strength("ALLUPPERCASE123!") is not None
    assert validate_password_strength("NoDigitsPassword!") is not None
    assert validate_password_strength("NoSpecialChar1234") is not None
    assert validate_password_strength("ValidAIOps#2026") is None


@pytest.mark.asyncio
async def test_mfa_challenge_token_rejected_by_get_current_user():
    """Un jeton éphémère mfa_challenge ne doit jamais donner accès aux routes protégées."""
    challenge = create_mfa_challenge_token(user_id="00000000-0000-0000-0000-000000000001", username="admin")
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=challenge)
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(auth=cred, session=session)
    assert exc_info.value.status_code == 401
