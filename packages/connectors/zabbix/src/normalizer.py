"""Adaptateur et normalisateur de payloads Zabbix vers le contrat canonique AIOps."""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from packages.contracts.src.events import EventSeverity, EventStatus, NormalizedIncidentEvent


SEVERITY_MAPPING: Dict[str, EventSeverity] = {
    "0": EventSeverity.NOT_CLASSIFIED,
    "1": EventSeverity.INFORMATION,
    "2": EventSeverity.WARNING,
    "3": EventSeverity.AVERAGE,
    "4": EventSeverity.HIGH,
    "5": EventSeverity.DISASTER,
    "NOT_CLASSIFIED": EventSeverity.NOT_CLASSIFIED,
    "INFORMATION": EventSeverity.INFORMATION,
    "WARNING": EventSeverity.WARNING,
    "AVERAGE": EventSeverity.AVERAGE,
    "HIGH": EventSeverity.HIGH,
    "DISASTER": EventSeverity.DISASTER,
}


def parse_event_severity(raw_severity: Any) -> EventSeverity:
    """Mappe la sévérité Zabbix (numérique ou textuelle) en enum canonique."""
    if raw_severity is None:
        return EventSeverity.WARNING
    key = str(raw_severity).strip().upper()
    return SEVERITY_MAPPING.get(key, EventSeverity.WARNING)


def parse_event_status(raw_type: Any) -> EventStatus:
    """Détermine si l'événement est un PROBLEM ou RECOVERY."""
    val = str(raw_type or "").strip().upper()
    if "RECOVER" in val or "OK" in val or "RESOLV" in val or val == "0":
        return EventStatus.RECOVERY
    if "UPDATE" in val or "ACK" in val:
        return EventStatus.UPDATE
    return EventStatus.PROBLEM


def parse_event_timestamp(raw_time: Any) -> datetime:
    """Normalise l'horodatage en datetime UTC."""
    if isinstance(raw_time, datetime):
        return raw_time if raw_time.tzinfo else raw_time.replace(tzinfo=timezone.utc)
    if not raw_time:
        return datetime.now(timezone.utc)
    try:
        # Essai epoch unix
        epoch = float(raw_time)
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        # Essai ISO format
        return datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def compute_idempotency_key(event_id: str, event_type: str, trigger_id: str) -> str:
    """Calcule le hash SHA-256 unique pour la déduplication stricte."""
    raw = f"{event_id}:{event_type}:{trigger_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalize_zabbix_payload(payload: Dict[str, Any]) -> NormalizedIncidentEvent:
    """Transforme un dictionnaire brut Zabbix en événement standardisé."""
    event_id = str(payload.get("event_id") or payload.get("EVENT.ID") or payload.get("id") or "0")
    trigger_id = str(payload.get("trigger_id") or payload.get("TRIGGER.ID") or "0")
    host_id = str(payload.get("host_id") or payload.get("HOST.ID") or "0")
    host_name = str(payload.get("host_name") or payload.get("HOST.NAME") or payload.get("host") or "UNKNOWN-HOST")
    
    raw_status = payload.get("event_type") or payload.get("EVENT.STATUS") or payload.get("status") or "PROBLEM"
    event_status = parse_event_status(raw_status)
    
    raw_severity = payload.get("severity") or payload.get("TRIGGER.SEVERITY") or "HIGH"
    severity = parse_event_severity(raw_severity)
    
    problem = str(
        payload.get("problem")
        or payload.get("problem_title")
        or payload.get("EVENT.NAME")
        or payload.get("TRIGGER.NAME")
        or "Incident détecté"
    )
    metric = payload.get("metric") or payload.get("ITEM.KEY") or None
    raw_val = payload.get("value") or payload.get("ITEM.VALUE")
    val_float: Optional[float] = None
    if raw_val is not None:
        try:
            val_float = float(raw_val)
        except (ValueError, TypeError):
            val_float = None

    ts = parse_event_timestamp(payload.get("timestamp") or payload.get("EVENT.DATE"))
    idempotency_key = compute_idempotency_key(event_id, event_status.value, trigger_id)

    return NormalizedIncidentEvent(
        event_id=event_id,
        event_type=event_status,
        host_id=host_id,
        host_name=host_name,
        trigger_id=trigger_id,
        severity=severity,
        problem=problem,
        metric=str(metric) if metric else None,
        value=val_float,
        timestamp=ts,
        ip_address=payload.get("ip") or payload.get("IP") or payload.get("ip_address"),
        tags=payload.get("tags") or {},
        idempotency_key=idempotency_key,
    )
