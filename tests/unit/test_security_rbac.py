"""Tests unitaires pour la sécurité, tokens JWT et signatures HMAC."""

from datetime import timedelta
import pytest
from packages.security.src.hmac_auth import get_webhook_secret, verify_hmac_signature
from packages.security.src.jwt import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from packages.security.src.rate_limiter import InMemoryRateLimiter


def test_password_hashing():
    raw = "SuperSecretPassword123!"
    hashed = get_password_hash(raw)
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_create_and_decode():
    data = {"sub": "admin", "role": "operator"}
    token = create_access_token(data, expires_delta=timedelta(minutes=30))
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "admin"
    assert decoded["role"] == "operator"


def test_rate_limiter_in_memory():
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=10)
    client_ip = "10.0.0.1"
    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True
    assert limiter.is_allowed(client_ip) is True
    # 4ème requête dépasse la limite
    assert limiter.is_allowed(client_ip) is False
