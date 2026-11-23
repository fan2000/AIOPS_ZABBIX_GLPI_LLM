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


def is_unexpanded_macro(val: Any) -> bool:
    """Vérifie si une valeur correspond à une macro Zabbix brute non substituée {MACRO.NAME}."""
    if not val:
        return False
    s = str(val).strip()
    return s.startswith("{") and s.endswith("}") and len(s) >= 3


def compute_idempotency_key(event_id: str, event_type: str, trigger_id: str) -> str:
    """Calcule le hash SHA-256 unique pour la déduplication stricte."""
    raw = f"{event_id}:{event_type}:{trigger_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalize_zabbix_payload(payload: Dict[str, Any]) -> NormalizedIncidentEvent:
    """Transforme un dictionnaire brut Zabbix en événement standardisé avec gestion robuste des macros de test."""
    raw_event_id = payload.get("event_id") or payload.get("EVENT.ID") or payload.get("id") or "0"
    raw_trigger_id = payload.get("trigger_id") or payload.get("TRIGGER.ID") or "0"
    raw_host_id = payload.get("host_id") or payload.get("HOST.ID") or "0"
    raw_host_name = payload.get("host_name") or payload.get("HOST.NAME") or payload.get("host") or "UNKNOWN-HOST"
    
    raw_problem = (
        payload.get("problem")
        or payload.get("problem_title")
        or payload.get("EVENT.NAME")
        or payload.get("TRIGGER.NAME")
        or "Incident détecté"
    )

    # Détection des macros non substituées (par exemple lors d'un test manuel "Test" du Webhook dans Zabbix)
    is_test_payload = (
        is_unexpanded_macro(raw_event_id)
        or is_unexpanded_macro(raw_host_name)
        or is_unexpanded_macro(raw_problem)
        or is_unexpanded_macro(raw_host_id)
    )

    raw_status = payload.get("event_type") or payload.get("EVENT.STATUS") or payload.get("status") or "PROBLEM"
    event_status = parse_event_status(raw_status)
    
    raw_severity = payload.get("severity") or payload.get("TRIGGER.SEVERITY") or "HIGH"
    severity = parse_event_severity(raw_severity)
    
    ts = parse_event_timestamp(payload.get("timestamp") or payload.get("EVENT.DATE"))

    if is_test_payload:
        event_id = str(raw_event_id) if not is_unexpanded_macro(raw_event_id) else f"EVT-TEST-{int(ts.timestamp())}"
        trigger_id = str(raw_trigger_id) if not is_unexpanded_macro(raw_trigger_id) else "9901"
        host_id = str(raw_host_id) if not is_unexpanded_macro(raw_host_id) else "1002"
        host_name = str(raw_host_name) if not is_unexpanded_macro(raw_host_name) else "SRV-TEST-01"
        problem = (
            str(raw_problem)
            if not is_unexpanded_macro(raw_problem)
            else "[Test Webhook Zabbix] Test de connectivité"
        )
    else:
        event_id = str(raw_event_id)
        trigger_id = str(raw_trigger_id)
        host_id = str(raw_host_id)
        host_name = str(raw_host_name)
        problem = str(raw_problem)

    raw_metric = payload.get("metric") or payload.get("ITEM.KEY") or None
    if is_unexpanded_macro(raw_metric) or str(raw_metric).strip().lower() == "none":
        metric = "system.cpu.util" if is_test_payload else None
    else:
        metric = str(raw_metric) if raw_metric else None

    raw_val = payload.get("value") or payload.get("ITEM.VALUE")
    val_float: Optional[float] = None
    if raw_val is not None and not is_unexpanded_macro(raw_val) and str(raw_val).strip().lower() != "none":
        try:
            val_float = float(raw_val)
        except (ValueError, TypeError):
            val_float = None
    elif is_test_payload:
        val_float = 50.0  # Valeur nominale simulée pour test de connectivité

    idempotency_key = compute_idempotency_key(event_id, event_status.value, trigger_id)

    tags_dict = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}

    # Extraction ou inférence multi-sites / topologie réseau complexe
    raw_site = payload.get("site_code") or payload.get("site") or tags_dict.get("site") or tags_dict.get("datacenter")
    if raw_site and not is_unexpanded_macro(raw_site):
        site_code = str(raw_site).strip().upper()
    else:
        hn_upper = host_name.upper()
        if "LYN" in hn_upper:
            site_code = "LYN-DC2"
        elif "MAR" in hn_upper or "EDGE" in hn_upper:
            site_code = "MAR-EDGE-01"
        elif "CLD" in hn_upper or "AWS" in hn_upper or "AZR" in hn_upper:
            site_code = "CLD-EU-WEST"
        else:
            site_code = "PAR-DC1"

    raw_zone = payload.get("network_zone") or payload.get("zone") or tags_dict.get("zone")
    if raw_zone and not is_unexpanded_macro(raw_zone):
        network_zone = str(raw_zone).strip().upper()
    else:
        hn_upper = host_name.upper()
        if "DMZ" in hn_upper or "FW" in hn_upper or "WAF" in hn_upper:
            network_zone = "DMZ"
        elif "EDGE" in hn_upper or "BR" in hn_upper:
            network_zone = "EDGE"
        elif "OT" in hn_upper or "PLC" in hn_upper or "SCADA" in hn_upper:
            network_zone = "OT"
        elif "CLD" in hn_upper:
            network_zone = "CLOUD"
        else:
            network_zone = "CORE"

    raw_proxy = payload.get("zabbix_proxy") or payload.get("proxy") or tags_dict.get("proxy")
    zabbix_proxy = str(raw_proxy).strip() if (raw_proxy and not is_unexpanded_macro(raw_proxy)) else f"zbx-proxy-{site_code.lower()}"

    SITE_ENTITY_MAP = {
        "PAR-DC1": "1",
        "LYN-DC2": "2",
        "MAR-EDGE-01": "3",
        "CLD-EU-WEST": "4",
    }
    raw_entity = payload.get("entity_id") or tags_dict.get("entity_id")
    if raw_entity is not None and not is_unexpanded_macro(raw_entity):
        entity_id = str(raw_entity).strip()
    else:
        entity_id = SITE_ENTITY_MAP.get(site_code, "0")

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
        tags={str(k): str(v) for k, v in tags_dict.items()},
        idempotency_key=idempotency_key,
        site_code=site_code,
        network_zone=network_zone,
        zabbix_proxy=zabbix_proxy,
        entity_id=entity_id,
    )
