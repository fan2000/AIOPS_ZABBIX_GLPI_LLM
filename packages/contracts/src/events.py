"""Contrats de données Pydantic v2 pour la plateforme AI IT Operations."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class EventStatus(str, Enum):
    PROBLEM = "PROBLEM"
    RECOVERY = "RECOVERY"
    UPDATE = "UPDATE"


class EventSeverity(str, Enum):
    NOT_CLASSIFIED = "NOT_CLASSIFIED"
    INFORMATION = "INFORMATION"
    WARNING = "WARNING"
    AVERAGE = "AVERAGE"
    HIGH = "HIGH"
    DISASTER = "DISASTER"


class ZabbixWebhookRaw(BaseModel):
    """Payload brut reçu du média webhook de Zabbix Server."""
    model_config = ConfigDict(extra="allow")

    event_id: str = Field(..., description="ID unique d'événement Zabbix")
    event_type: str = Field(..., description="PROBLEM, RECOVERY ou UPDATE")
    host_id: str = Field(..., description="ID hôte Zabbix")
    host_name: str = Field(..., description="Nom visible de l'hôte")
    trigger_id: str = Field(..., description="ID du trigger ayant déclenché l'événement")
    severity: str = Field(..., description="Niveau de gravité Zabbix")
    problem: str = Field(..., description="Titre ou description du problème")
    metric: Optional[str] = Field(None, description="Clé de l'item Zabbix (ex: system.cpu.util)")
    value: Optional[float] = Field(None, description="Valeur numérique au déclenchement")
    timestamp: Optional[str] = Field(None, description="Horodatage ISO-8601 ou epoch")
    ip: Optional[str] = Field(None, description="Adresse IP de l'interface hôte")
    tags: Optional[Dict[str, str]] = Field(default_factory=dict)


class NormalizedIncidentEvent(BaseModel):
    """Contrat normalisé de l'événement conforme au standard AIOps."""
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., description="Identifiant unique Zabbix")
    event_type: EventStatus = Field(..., description="Statut de l'événement")
    host_id: str = Field(..., description="Identifiant de l'équipement dans Zabbix")
    host_name: str = Field(..., description="Nom canonique de la machine")
    trigger_id: str = Field(..., description="Identifiant du déclencheur")
    severity: EventSeverity = Field(..., description="Gravité normalisée")
    problem: str = Field(..., description="Description synthétique de l'anomalie")
    metric: Optional[str] = Field(None, description="Clé de la métrique associée")
    value: Optional[float] = Field(None, description="Valeur observée")
    timestamp: datetime = Field(..., description="Horodatage UTC standardisé")
    ip_address: Optional[str] = Field(None, description="Adresse IP")
    tags: Dict[str, str] = Field(default_factory=dict)
    idempotency_key: str = Field(..., description="Hash unique sha256 pour déduplication")
