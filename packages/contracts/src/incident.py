"""Contrats de données pour la gestion des Incidents et de la Corrélation."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from packages.contracts.src.events import EventSeverity, NormalizedIncidentEvent


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    CORRELATED = "CORRELATED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REMEDIATING = "REMEDIATING"
    RECOVERY_OBSERVED = "RECOVERY_OBSERVED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class IncidentCorrelationType(str, Enum):
    SAME_HOST = "SAME_HOST"
    TOPOLOGY_DEPENDENCY = "TOPOLOGY_DEPENDENCY"
    KNOWN_SIGNATURE = "KNOWN_SIGNATURE"
    AI_SUGGESTED = "AI_SUGGESTED"


class IncidentRead(BaseModel):
    """Représentation publique d'un incident consolidé."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_number: str
    title: str
    severity: EventSeverity
    status: IncidentStatus
    primary_asset_name: str
    zabbix_host_id: str
    glpi_ticket_id: Optional[str] = None
    entity_id: Optional[str] = "0"
    events_count: int = 1
    opened_at: datetime
    recovery_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IncidentCorrelationLink(BaseModel):
    """Lien entre un incident et un événement ou un autre incident."""
    primary_incident_id: UUID
    correlated_event_id: str
    correlation_type: IncidentCorrelationType
    confidence_score: float = Field(1.0, ge=0.0, le=1.0)
    reason: str
