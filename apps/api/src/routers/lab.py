"""Simulateur d'infrastructure de laboratoire pour tests déterministes et démos."""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request, Response
from packages.connectors.redis_streams import redis_streams
from packages.connectors.zabbix.src.normalizer import normalize_zabbix_payload

router = APIRouter(prefix="/api/v1/lab", tags=["Lab Simulator"])

# Scénarios préenregistrés
SCENARIOS_CATALOG: Dict[str, Dict[str, Any]] = {
    "1_disk_full": {
        "event_id": "4001",
        "event_type": "PROBLEM",
        "host_id": "1001",
        "host_name": "SRV-DATA-01",
        "trigger_id": "9001",
        "severity": "HIGH",
        "problem": "Disk space /var/log is critically low (>95%)",
        "metric": "vfs.fs.size[/var/log,pfree]",
        "value": 3.8,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    },
    "2_cpu_high": {
        "event_id": "4002",
        "event_type": "PROBLEM",
        "host_id": "1002",
        "host_name": "SRV-APP-01",
        "trigger_id": "9002",
        "severity": "HIGH",
        "problem": "CPU utilization above 90% for 15 minutes",
        "metric": "system.cpu.util",
        "value": 96.4,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    },
    "3_ram_swap_thrashing": {
        "event_id": "4003",
        "event_type": "PROBLEM",
        "host_id": "1002",
        "host_name": "SRV-APP-01",
        "trigger_id": "9003",
        "severity": "AVERAGE",
        "problem": "Memory usage critical and swap thrashing detected",
        "metric": "vm.memory.util",
        "value": 98.1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    },
    "4_service_down": {
        "event_id": "4004",
        "event_type": "PROBLEM",
        "host_id": "1003",
        "host_name": "SRV-WIN-PRINT",
        "trigger_id": "9004",
        "severity": "HIGH",
        "problem": "Windows Print Spooler service is stopped",
        "metric": "service.info[Spooler,state]",
        "value": 6.0,  # 6 = stopped
        "timestamp": datetime.now(timezone.utc).isoformat(),
    },
    "5_host_unreachable": {
        "event_id": "4005",
        "event_type": "PROBLEM",
        "host_id": "1004",
        "host_name": "SW-CORE-01",
        "trigger_id": "9005",
        "severity": "DISASTER",
        "problem": "Host is unreachable by ICMP ping",
        "metric": "icmpping",
        "value": 0.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    },
    "7_unknown_incident": {
        "event_id": "4007",
        "event_type": "PROBLEM",
        "host_id": "1005",
        "host_name": "SRV-LEGACY-09",
        "trigger_id": "9007",
        "severity": "AVERAGE",
        "problem": "Corrupted proprietary binary trace flag 0xFA3",
        "metric": "custom.app.trace",
        "value": 1.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    },
    "10_recovery_event": {
        "event_id": "4002",
        "event_type": "RECOVERY",
        "host_id": "1002",
        "host_name": "SRV-APP-01",
        "trigger_id": "9002",
        "severity": "HIGH",
        "problem": "RESOLVED: CPU utilization above 90%",
        "metric": "system.cpu.util",
        "value": 34.2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    },
}


@router.get("/scenarios")
async def list_available_scenarios() -> Dict[str, Any]:
    """Liste tous les scénarios de test prêts à être injectés."""
    return {"available_scenarios": list(SCENARIOS_CATALOG.keys())}


@router.post("/scenarios/{scenario_id}/inject")
async def inject_scenario(scenario_id: str) -> Dict[str, Any]:
    """Injecte un scénario dans le flux temps réel de la plateforme."""
    if scenario_id not in SCENARIOS_CATALOG:
        raise HTTPException(status_code=404, detail="Scénario inconnu")

    raw_event = SCENARIOS_CATALOG[scenario_id].copy()
    raw_event["timestamp"] = datetime.now(timezone.utc).isoformat()
    normalized = normalize_zabbix_payload(raw_event)

    msg_id = await redis_streams.publish_event("zabbix:events", normalized.model_dump())
    return {
        "status": "injected",
        "scenario": scenario_id,
        "message_id": msg_id,
        "event_id": normalized.event_id,
        "event_type": normalized.event_type.value,
    }


# --- MOCK GLPI API REST POUR TESTS & DEMOS ---
_MOCK_TICKETS: Dict[int, Dict[str, Any]] = {}
_TICKET_COUNTER = 15200


@router.get("/glpi/initSession")
async def mock_glpi_init_session() -> Dict[str, str]:
    return {"session_token": "mock_session_token_xyz123"}


@router.get("/glpi/search/Computer")
async def mock_glpi_search_computer() -> Dict[str, Any]:
    return {
        "totalcount": 1,
        "data": [
            {
                "1": "SRV-APP-01",
                "2": 42,
                "5": "VMW-SN-998811",
                "80": 0,
            }
        ]
    }


@router.post("/glpi/Ticket")
async def mock_glpi_create_ticket(request: Request) -> Dict[str, int]:
    global _TICKET_COUNTER
    _TICKET_COUNTER += 1
    body = await request.json()
    _MOCK_TICKETS[_TICKET_COUNTER] = body.get("input", {})
    return {"id": _TICKET_COUNTER, "message": "Ticket créé avec succès dans GLPI (Mock)"}


@router.post("/glpi/Ticket/{ticket_id}/ITILFollowup")
async def mock_glpi_followup(ticket_id: int, request: Request) -> Dict[str, int]:
    return {"id": 8801, "message": "Suivi privé enregistré dans GLPI"}


@router.get("/glpi/KnowbaseItem")
async def mock_glpi_knowbase() -> List[Dict[str, Any]]:
    return [
        {
            "id": 12,
            "name": "Diagnostic et remédiation CPU élevé Windows",
            "answer": "<p>En cas de saturation CPU (>90%), collecter les processus consommateurs avec PowerShell 'Get-Process'. Si un service applicatif autorisé s'emballe, exécuter le redémarrage contrôlé.</p>",
            "entities_id": 0,
            "is_faq": 1,
        },
        {
            "id": 14,
            "name": "Procédure saturation disque /var/log Linux",
            "answer": "<p>Pour résoudre une alerte espace disque sur /var/log, purger les archives .gz de plus de 15 jours avec le runbook rb-disk-cleanup-logs après confirmation.</p>",
            "entities_id": 0,
            "is_faq": 1,
        },
    ]
