"""Worker asynchrone de traitement et d'orchestration des incidents Zabbix / GLPI."""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy import select
from database.connection import async_session_maker
from packages.agents.src.graph import run_incident_analysis
from packages.agents.src.state import IncidentAgentState
from packages.connectors.glpi.src.client import glpi_client
from packages.connectors.redis_streams import redis_streams
from packages.connectors.zabbix.src.client import zabbix_client
from packages.connectors.zabbix.src.normalizer import normalize_zabbix_payload
from packages.contracts.src.events import EventStatus, NormalizedIncidentEvent
from packages.contracts.src.glpi import GlpiFollowupCreate, GlpiTicketCreate
from packages.domain.models.database import (
    AIAnalysisRun,
    AIRecommendation,
    Asset,
    Incident,
    IncidentEvent,
    RecommendationSource,
)
from services.incident_worker.src.correlation_engine import correlation_engine


class IncidentWorker:
    """Consommateur Redis Streams coordonnant GLPI, Zabbix et LangGraph."""

    def __init__(self):
        self.stream_name = "zabbix:events"
        self.group_name = "orchestrator-group"
        self.consumer_name = f"worker-{os.getpid()}"
        self.is_running = False

    async def start(self) -> None:
        """Démarre la boucle de consommation des événements."""
        self.is_running = True
        await redis_streams.ensure_consumer_group(self.stream_name, self.group_name)

        while self.is_running:
            try:
                messages = await redis_streams.consume_events(
                    self.stream_name,
                    self.group_name,
                    self.consumer_name,
                    count=5,
                    block_ms=3000,
                )
                for msg_id, payload in messages:
                    await self.process_event(msg_id, payload)
                    await redis_streams.ack_event(self.stream_name, self.group_name, msg_id)
            except Exception as e:
                await asyncio.sleep(2.0)

    async def process_event(self, msg_id: str, raw_payload: Dict[str, Any]) -> None:
        """Traite un événement unique : normalisation, corrélation, GLPI, LangGraph."""
        event: NormalizedIncidentEvent = normalize_zabbix_payload(raw_payload)

        async with async_session_maker() as session:
            # 1. Vérification d'idempotence stricte en base
            check_dup = await session.execute(
                select(IncidentEvent).where(IncidentEvent.idempotency_hash == event.idempotency_key)
            )
            if check_dup.scalar_one_or_none():
                return  # Doublon ignoré

            # 2. Corrélation
            correl_match = await correlation_engine.find_correlated_incident(event, session)
            incident: Incident

            if correl_match:
                incident, c_type, conf = correl_match
                await correlation_engine.link_event_to_incident(
                    incident, event, session, c_type, conf, f"Corrélation {c_type}"
                )
            else:
                # 3. Nouvel Incident : recherche CMDB GLPI
                asset_info = await glpi_client.search_computer(event.host_name)
                entity_id = str(asset_info.entity_id) if asset_info else "0"

                # Création du ticket GLPI
                glpi_ticket_id = None
                try:
                    ticket_id_int = await glpi_client.create_ticket(
                        GlpiTicketCreate(
                            name=f"[AIOps] {event.severity.value} - {event.problem} sur {event.host_name}",
                            content=f"Incident détecté par Zabbix.\nHôte: {event.host_name}\nDéclencheur: {event.problem}\nMétrique: {event.metric} = {event.value}",
                            entities_id=int(entity_id),
                        )
                    )
                    glpi_ticket_id = str(ticket_id_int)
                except Exception:
                    pass

                inc_number = f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
                incident = Incident(
                    id=uuid.uuid4(),
                    incident_number=inc_number,
                    title=f"{event.problem} sur {event.host_name}",
                    severity=event.severity.value,
                    status="OPEN",
                    primary_asset_name=event.host_name,
                    zabbix_host_id=event.host_id,
                    glpi_ticket_id=glpi_ticket_id,
                    entity_id=entity_id,
                )
                session.add(incident)
                await session.flush()

            # Enregistrement de l'événement lié
            db_event = IncidentEvent(
                id=uuid.uuid4(),
                incident_id=incident.id,
                zabbix_event_id=event.event_id,
                zabbix_trigger_id=event.trigger_id,
                event_status=event.event_type.value,
                severity=event.severity.value,
                host_name=event.host_name,
                metric_key=event.metric,
                metric_value=event.value,
                event_timestamp=event.timestamp,
                raw_payload=raw_payload,
                idempotency_hash=event.idempotency_key,
            )
            session.add(db_event)
            await session.commit()

            # 4. Exécution du graphe LangGraph (si problème actif)
            if event.event_type == EventStatus.PROBLEM:
                initial_state: IncidentAgentState = {
                    "incident_id": str(incident.id),
                    "ticket_id": int(incident.glpi_ticket_id) if incident.glpi_ticket_id and incident.glpi_ticket_id.isdigit() else None,
                    "host_name": event.host_name,
                    "zabbix_host_id": event.host_id,
                    "primary_event": event.model_dump(),
                    "events": [event.model_dump()],
                    "observations": [],
                }
                final_state = await run_incident_analysis(initial_state)
                report = final_state.get("diagnostic_report")

                if report and incident.glpi_ticket_id:
                    # Envoi d'un suivi privé dans le ticket GLPI
                    followup_text = (
                        f"<strong>[AI IT Operations - Analyse Diagnostique]</strong><br/>"
                        f"<strong>Hypothèses :</strong> {', '.join(h['description'] for h in report.get('hypotheses', []))}<br/>"
                        f"<strong>Contrôles recommandés :</strong> {', '.join(report.get('checks', []))}<br/>"
                        f"<strong>Actions proposées :</strong> {', '.join(a['action'] for a in report.get('recommended_actions', []))}<br/>"
                        f"<strong>Confiance :</strong> {report.get('confidence', {}).get('level')} ({report.get('confidence', {}).get('explanation')})"
                    )
                    try:
                        await glpi_client.add_private_followup(
                            GlpiFollowupCreate(
                                items_id=int(incident.glpi_ticket_id),
                                content=followup_text,
                                is_private=1,
                            )
                        )
                    except Exception:
                        pass


incident_worker = IncidentWorker()
