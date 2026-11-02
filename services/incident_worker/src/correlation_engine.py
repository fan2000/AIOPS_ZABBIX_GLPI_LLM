"""Moteur de corrélation déterministe pour regrouper les événements d'incidents."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from packages.contracts.src.events import EventStatus, NormalizedIncidentEvent
from packages.domain.models.database import Incident, IncidentCorrelation, IncidentEvent

WINDOW_MINUTES = int(os.getenv("CORRELATION_WINDOW_MINUTES", "15"))


class CorrelationEngine:
    """Évalue et rattache les alertes Zabbix à un incident existant ou en crée un nouveau."""

    def __init__(self, window_minutes: int = WINDOW_MINUTES):
        self.window_minutes = window_minutes

    async def find_correlated_incident(
        self,
        event: NormalizedIncidentEvent,
        session: AsyncSession,
    ) -> Optional[Tuple[Incident, str, float]]:
        """Recherche un incident actif auquel rattacher l'événement selon les règles déterministes."""
        cutoff_time = event.timestamp - timedelta(minutes=self.window_minutes)

        # Règle 1: Même équipement (host_name ou zabbix_host_id) et statut ouvert/en cours
        stmt = (
            select(Incident)
            .where(
                (Incident.zabbix_host_id == event.host_id) | (Incident.primary_asset_name == event.host_name),
                Incident.status.in_(["OPEN", "INVESTIGATING", "CORRELATED", "WAITING_APPROVAL"]),
                Incident.opened_at >= cutoff_time,
            )
            .order_by(desc(Incident.opened_at))
            .limit(1)
        )
        existing_incident = (await session.execute(stmt)).scalar_one_or_none()

        if existing_incident:
            return existing_incident, "SAME_HOST_TIME_WINDOW", 1.0

        # Règle 2: Recherche par trigger si RECOVERY
        if event.event_type == EventStatus.RECOVERY:
            rec_stmt = (
                select(Incident)
                .join(IncidentEvent, IncidentEvent.incident_id == Incident.id)
                .where(
                    IncidentEvent.zabbix_trigger_id == event.trigger_id,
                    Incident.status.in_(["OPEN", "INVESTIGATING", "CORRELATED", "WAITING_APPROVAL", "REMEDIATING"]),
                )
                .order_by(desc(Incident.opened_at))
                .limit(1)
            )
            matched_rec = (await session.execute(rec_stmt)).scalar_one_or_none()
            if matched_rec:
                return matched_rec, "RECOVERY_TRIGGER_MATCH", 1.0

        return None

    async def link_event_to_incident(
        self,
        incident: Incident,
        event: NormalizedIncidentEvent,
        session: AsyncSession,
        correlation_type: str,
        confidence: float,
        reason: str,
    ) -> None:
        """Enregistre la relation de corrélation et incrémente le compteur d'événements de l'incident."""
        incident.events_count += 1
        # Si RECOVERY, mise à jour du statut en RECOVERY_OBSERVED
        if event.event_type == EventStatus.RECOVERY:
            incident.status = "RECOVERY_OBSERVED"
            incident.recovery_at = event.timestamp

        correlation = IncidentCorrelation(
            incident_id=incident.id,
            correlated_event_id=event.event_id,
            correlation_type=correlation_type,
            confidence_score=confidence,
            reason=reason,
        )
        session.add(correlation)


correlation_engine = CorrelationEngine()
