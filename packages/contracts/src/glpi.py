"""Contrats de données pour l'intégration GLPI REST API."""

from datetime import datetime
from enum import IntEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class GlpiTicketStatus(IntEnum):
    NEW = 1
    PROCESSING_ASSIGNED = 2
    PROCESSING_PLANNED = 3
    PENDING = 4
    SOLVED = 5
    CLOSED = 6


class GlpiTicketUrgency(IntEnum):
    VERY_LOW = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    VERY_HIGH = 5


class GlpiTicketImpact(IntEnum):
    VERY_LOW = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    VERY_HIGH = 5


class GlpiAssetRead(BaseModel):
    """Informations issues de la CMDB GLPI sur un équipement."""
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    item_type: str = "Computer"
    entity_id: int = 0
    serial: Optional[str] = None
    contact: Optional[str] = None
    operatingsystem: Optional[str] = None
    ip_address: Optional[str] = None
    is_deleted: bool = False


class GlpiTicketCreate(BaseModel):
    """Payload pour la création d'un ticket dans GLPI."""
    name: str = Field(..., max_length=255)
    content: str
    status: GlpiTicketStatus = GlpiTicketStatus.NEW
    urgency: GlpiTicketUrgency = GlpiTicketUrgency.HIGH
    impact: GlpiTicketImpact = GlpiTicketImpact.HIGH
    entities_id: int = 0
    items_id: Optional[Dict[str, List[int]]] = None  # Liaison équipement CMDB


class GlpiFollowupCreate(BaseModel):
    """Ajout d'un suivi (privé par défaut pour les analyses IA)."""
    items_id: int = Field(..., description="ID du ticket GLPI")
    itemtype: str = "Ticket"
    content: str = Field(..., description="Corps HTML ou texte du suivi")
    is_private: int = Field(1, description="1 pour suivi interne technicien, 0 public")


class GlpiSolutionCreate(BaseModel):
    """Proposition formelle de solution dans GLPI."""
    items_id: int = Field(..., description="ID du ticket GLPI")
    itemtype: str = "Ticket"
    content: str
    solutiontypes_id: int = 0


class GlpiKnowledgeItemRead(BaseModel):
    """Article extrait de la base de connaissances GLPI."""
    id: int
    name: str
    answer: str
    entities_id: int = 0
    is_faq: bool = False
    date_mod: Optional[datetime] = None
