"""Réception et normalisation rapide des webhooks Zabbix."""

import json
import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from packages.connectors.redis_streams import redis_streams
from packages.connectors.zabbix.src.normalizer import normalize_zabbix_payload
from packages.observability.src.metrics import record_event_ingested
from packages.security.src.hmac_auth import verify_bearer_token, verify_hmac_signature
from packages.security.src.rate_limiter import auth_limiter

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])
LAB_MODE = os.getenv("LAB_MODE_ENABLED", "false").lower() == "true"
MAX_WEBHOOK_BODY_BYTES = 1_048_576  # 1 Mo max (CWE-770)


@router.post("/zabbix", status_code=status.HTTP_202_ACCEPTED)
async def receive_zabbix_webhook(
    request: Request,
    response: Response,
    x_zabbix_signature: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Point d'entrée HTTPS pour les alertes Zabbix. Valide et met en file Redis Streams."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="En-tête Content-Length invalide",
            ) from exc
        if declared_size < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="En-tête Content-Length négatif",
            )
        if declared_size > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Corps de requête trop volumineux (max: {MAX_WEBHOOK_BODY_BYTES} octets)",
            )

    body_bytes = await request.body()
    if not body_bytes:
        raise HTTPException(status_code=400, detail="Corps de requête vide")

    if len(body_bytes) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Corps de requête trop volumineux (max: {MAX_WEBHOOK_BODY_BYTES} octets)",
        )

    # Vérification d'authenticité avec rate-limiting sur échec HMAC/Bearer (CWE-307)
    if not LAB_MODE:
        is_hmac_valid = verify_hmac_signature(body_bytes, x_zabbix_signature)
        is_bearer_valid = verify_bearer_token(authorization)
        if not (is_hmac_valid or is_bearer_valid):
            client_ip = request.client.host if request.client else "unknown"
            if not auth_limiter.is_allowed(f"webhook_auth_fail:{client_ip}"):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Trop de tentatives webhook non authentifiées.",
                    headers={"Retry-After": "60"},
                )
            raise HTTPException(status_code=401, detail="Signature ou jeton webhook invalide")

    try:
        raw_json = json.loads(body_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="JSON malformé ou encodage non UTF-8")

    if not isinstance(raw_json, dict):
        raise HTTPException(status_code=400, detail="Le payload webhook doit être un objet JSON valide")

    # Normalisation et calcul de clé d'idempotence
    normalized = normalize_zabbix_payload(raw_json)

    # Mise en file asynchrone ultra-rapide (< 30ms)
    msg_id = await redis_streams.publish_event("zabbix:events", normalized.model_dump())
    record_event_ingested(source="zabbix", event_type=normalized.event_type.value)

    return {
        "status": "accepted",
        "message_id": msg_id,
        "event_id": normalized.event_id,
        "event_type": normalized.event_type.value,
        "idempotency_key": normalized.idempotency_key,
    }
