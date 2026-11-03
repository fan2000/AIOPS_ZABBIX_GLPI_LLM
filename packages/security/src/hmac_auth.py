"""Validation HMAC et authentification des webhooks entrants Zabbix."""

import hmac
import hashlib
import os
from typing import Optional


def get_webhook_secret() -> str:
    """Retourne la clé secrète configurée pour les webhooks Zabbix."""
    return os.getenv("ZABBIX_WEBHOOK_SECRET", "zabbix-webhook-shared-hmac-secret-key-32chars")


def verify_hmac_signature(payload_bytes: bytes, signature_header: Optional[str]) -> bool:
    """Vérifie la signature HMAC SHA-256 du webhook Zabbix ou le jeton secret partagé."""
    if not signature_header:
        return False

    secret = get_webhook_secret()
    if hmac.compare_digest(signature_header.strip(), secret):
        return True

    secret_bytes = secret.encode("utf-8")
    expected_mac = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
    
    # Gestion du préfixe sha256= si présent
    received_signature = signature_header.strip()
    if received_signature.startswith("sha256="):
        received_signature = received_signature[7:]

    return hmac.compare_digest(expected_mac.lower(), received_signature.lower())


def verify_bearer_token(auth_header: Optional[str]) -> bool:
    """Vérifie un jeton Bearer partagé si HMAC n'est pas utilisé par le webhook Zabbix."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return False
    token = auth_header[7:].strip()
    return hmac.compare_digest(token, get_webhook_secret())
