"""Réception et normalisation rapide des webhooks Zabbix."""

import json
import os
from typing import Any, Dict
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from packages.connectors.redis_streams import redis_streams
from packages.connectors.zabbix.src.normalizer import normalize_zabbix_payload
from packages.security.src.hmac_auth import verify_bearer_token, verify_hmac_signature

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])
LAB_MODE = os.getenv("LAB_MODE_ENABLED", "false").lower() == "true"


@router.post("/zabbix", status_code=status.HTTP_202_ACCEPTED)
async def receive_zabbix_webhook(
    request: Request,
    response: Response,
    x_zabbix_signature: str = Header(None),
    authorization: str = Header(None),
) -> Dict[str, Any]:
    """Point d'entrée HTTPS pour les alertes Zabbix. Valide et met en file Redis Streams."""
    body_bytes = await request.body()
    if not body_bytes:
        raise HTTPException(status_code=400, detail="Corps de requête vide")

    # Vérification d'authenticité (désactivable en mode lab pour faciliter les tests)
    if not LAB_MODE:
        is_hmac_valid = verify_hmac_signature(body_bytes, x_zabbix_signature)
        is_bearer_valid = verify_bearer_token(authorization)
        if not (is_hmac_valid or is_bearer_valid):
            raise HTTPException(status_code=401, detail="Signature ou jeton webhook invalide")

    try:
        raw_json = json.loads(body_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON malformé")

    # Normalisation et calcul de clé d'idempotence
    normalized = normalize_zabbix_payload(raw_json)

    # Mise en file asynchrone ultra-rapide (< 30ms)
    msg_id = await redis_streams.publish_event("zabbix:events", normalized.model_dump())

    return {
        "status": "accepted",
        "message_id": msg_id,
        "event_id": normalized.event_id,
        "event_type": normalized.event_type.value,
        "idempotency_key": normalized.idempotency_key,
    }
