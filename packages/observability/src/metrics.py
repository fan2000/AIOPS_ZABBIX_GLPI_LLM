"""Module d'observabilité et d'export de métriques Prometheus pour AIOps."""

import time
from typing import Dict
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Registre Prometheus partagé
REGISTRY = CollectorRegistry(auto_describe=True)

# Compteurs d'incidents
INCIDENTS_TOTAL = Counter(
    "aiops_incidents_total",
    "Nombre total d'incidents enregistrés dans la plateforme AIOps",
    ["status", "severity"],
    registry=REGISTRY,
)

# Compteurs d'événements Zabbix ingérés
EVENTS_INGESTED_TOTAL = Counter(
    "aiops_events_ingested_total",
    "Nombre total d'alertes et événements de supervision ingérés",
    ["source", "event_type"],
    registry=REGISTRY,
)

# Latence d'inférence LLM / Agents LangGraph
LLM_INFERENCE_LATENCY = Histogram(
    "aiops_llm_inference_latency_seconds",
    "Temps d'inférence des agents LangGraph et modèles LLM",
    ["agent", "model"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    registry=REGISTRY,
)

# Exécutions de remédiation
REMEDIATION_EXECUTIONS_TOTAL = Counter(
    "aiops_remediation_executions_total",
    "Nombre d'actions de remédiation exécutées",
    ["status", "runner_type"],
    registry=REGISTRY,
)

# Statut de connectivité des 12 services
SERVICES_HEALTH = Gauge(
    "aiops_service_up",
    "Statut de connectivité des services du système AIOps (1 = UP, 0 = DOWN)",
    ["service_name", "category"],
    registry=REGISTRY,
)


def record_incident_created(status: str = "OPEN", severity: str = "HIGH") -> None:
    """Incrémente le compteur d'incidents."""
    INCIDENTS_TOTAL.labels(status=status.upper(), severity=severity.upper()).inc()


def record_event_ingested(source: str = "zabbix", event_type: str = "PROBLEM") -> None:
    """Incrémente le compteur d'événements ingérés."""
    EVENTS_INGESTED_TOTAL.labels(source=source, event_type=event_type).inc()


def record_remediation_execution(status: str = "SUCCESS", runner_type: str = "powershell") -> None:
    """Incrémente le compteur de remédiations."""
    REMEDIATION_EXECUTIONS_TOTAL.labels(status=status.upper(), runner_type=runner_type).inc()


def set_service_health(service_name: str, category: str, is_up: bool) -> None:
    """Met à jour la jauge d'état du service."""
    SERVICES_HEALTH.labels(service_name=service_name, category=category).set(1 if is_up else 0)


def export_metrics_text() -> bytes:
    """Génère le flux textuel Prometheus standard."""
    return generate_latest(REGISTRY)
