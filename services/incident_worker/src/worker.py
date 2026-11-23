"""Worker asynchrone de traitement et d'orchestration des incidents Zabbix / GLPI."""

import asyncio
import html
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy import select
from database.connection import async_session_maker
from packages.agents.src.graph import start_hitl_incident_analysis
from packages.agents.src.state import IncidentAgentState
from packages.connectors.glpi.src.client import glpi_client
from packages.connectors.redis_streams import redis_streams
from packages.connectors.zabbix.src.client import zabbix_client
from packages.connectors.zabbix.src.normalizer import normalize_zabbix_payload
from packages.contracts.src.events import EventStatus, NormalizedIncidentEvent
from packages.contracts.src.glpi import GlpiFollowupCreate, GlpiTicketCreate
from packages.domain.models.database import (
    Asset,
    AuditLog,
    GlpiTicketLink,
    Incident,
    IncidentEvent,
)
from services.incident_worker.src.context_enrichment import (
    create_pending_approval_if_paused,
    enrich_incident_context,
    persist_analysis_result,
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
        print(f"🚀 [IncidentWorker] Démarrage sur le flux '{self.stream_name}' (groupe: {self.group_name}, consumer: {self.consumer_name})", flush=True)
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
                    print(f"📥 [IncidentWorker] Événement reçu #{msg_id} : {payload.get('problem')} sur {payload.get('host_name')}", flush=True)
                    try:
                        await self.process_event(msg_id, payload)
                        await redis_streams.ack_event(self.stream_name, self.group_name, msg_id)
                        print(f"✅ [IncidentWorker] Événement #{msg_id} acquitté avec succès.", flush=True)
                    except Exception as proc_err:
                        print(f"⚠️ [IncidentWorker] Isolation DLQ pour #{msg_id}: {proc_err}", flush=True)
                        await redis_streams.publish_to_dlq(self.stream_name, msg_id, payload, str(proc_err))
                        await redis_streams.ack_event(self.stream_name, self.group_name, msg_id)
            except Exception as e:
                print(f"❌ [IncidentWorker] Erreur dans la boucle de consommation: {e}", flush=True)
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
                # 3. Nouvel Incident : recherche CMDB GLPI et résolution multi-entités / multi-sites
                asset_info = await glpi_client.search_computer(event.host_name)
                if asset_info and str(asset_info.entity_id) != "0":
                    entity_id = str(asset_info.entity_id)
                else:
                    entity_id = event.entity_id or "0"

                # Formatage propre du titre sans redondance d'hôte
                if event.host_name and event.host_name.lower() in event.problem.lower():
                    clean_title = event.problem
                else:
                    clean_title = f"{event.problem} sur {event.host_name}"

                # Création du ticket GLPI avec contexte multi-sites
                glpi_ticket_id = None
                try:
                    ticket_id_int = await glpi_client.create_ticket(
                        GlpiTicketCreate(
                            name=f"[AIOps][{event.site_code}] {event.severity.value} - {clean_title}",
                            content=(
                                f"Incident détecté par Zabbix.\n"
                                f"Site / Datacenter: {event.site_code} (Zone: {event.network_zone})\n"
                                f"Proxy Zabbix: {event.zabbix_proxy}\n"
                                f"Hôte: {event.host_name}\n"
                                f"Déclencheur: {event.problem}\n"
                                f"Métrique: {event.metric} = {event.value}"
                            ),
                            entities_id=int(entity_id) if entity_id.isdigit() else 0,
                        )
                    )
                    glpi_ticket_id = str(ticket_id_int)
                except Exception:
                    pass

                inc_number = f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
                incident = Incident(
                    id=uuid.uuid4(),
                    incident_number=inc_number,
                    title=clean_title,
                    severity=event.severity.value,
                    status="OPEN",
                    primary_asset_name=event.host_name,
                    zabbix_host_id=event.host_id,
                    glpi_ticket_id=glpi_ticket_id,
                    entity_id=entity_id,
                    incident_metadata={
                        "site_code": event.site_code,
                        "network_zone": event.network_zone,
                        "zabbix_proxy": event.zabbix_proxy,
                        "ip_address": event.ip_address,
                    },
                )
                session.add(incident)
                await session.flush()

                if glpi_ticket_id:
                    ticket_link = GlpiTicketLink(
                        id=uuid.uuid4(),
                        incident_id=incident.id,
                        glpi_ticket_id=glpi_ticket_id,
                        entity_id=entity_id,
                        glpi_status=1,
                    )
                    session.add(ticket_link)

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

            # 4. Exécution enrichie du graphe LangGraph (si problème actif)
            if event.event_type == EventStatus.PROBLEM:
                enriched = await enrich_incident_context(incident, event.model_dump(), session)
                initial_state: IncidentAgentState = {
                    "incident_id": str(incident.id),
                    "ticket_id": int(incident.glpi_ticket_id) if incident.glpi_ticket_id and incident.glpi_ticket_id.isdigit() else None,
                    "entity_id": str(incident.entity_id or "0"),
                    "host_name": event.host_name,
                    "zabbix_host_id": event.host_id,
                    "primary_event": event.model_dump(),
                    "events": enriched["events"],
                    "asset_info": enriched["asset_info"],
                    "metric_history": enriched["metric_history"],
                    "approved_runbook_ids": enriched["approved_runbook_ids"],
                    "observations": [],
                }
                import time
                analysis_start = time.time()
                thread_id = f"incident-{incident.id}-{uuid.uuid4().hex[:8]}"
                hitl_res = await start_hitl_incident_analysis(initial_state, thread_id=thread_id)
                final_state = hitl_res["state"]
                report = final_state.get("diagnostic_report")
                analysis_duration_ms = int((time.time() - analysis_start) * 1000)

                if report:
                    await persist_analysis_result(incident, final_state, analysis_duration_ms, session)
                    await create_pending_approval_if_paused(incident, hitl_res, session)

                    audit_entry = AuditLog(
                        id=uuid.uuid4(),
                        action="INCIDENT_AI_DIAGNOSED",
                        resource_type="incident",
                        resource_id=str(incident.id),
                        details={
                            "incident_number": incident.incident_number,
                            "severity": incident.severity,
                            "duration_ms": analysis_duration_ms,
                            "execution_mode": final_state.get("execution_mode", "deterministic"),
                            "tokens": int(final_state.get("prompt_tokens") or 0) + int(final_state.get("completion_tokens") or 0),
                            "hitl_paused": bool(hitl_res.get("paused")),
                            "thread_id": thread_id,
                        },
                    )
                    session.add(audit_entry)
                    await session.commit()

                if report and incident.glpi_ticket_id:
                    # Envoi d'un suivi privé dans le ticket GLPI avec assainissement HTML (CWE-79)
                    escaped_hypotheses = ", ".join(html.escape(str(h.get('description', ''))) for h in report.get('hypotheses', []))
                    escaped_checks = ", ".join(html.escape(str(c)) for c in report.get('checks', []))
                    escaped_actions = ", ".join(html.escape(str(a.get('action', ''))) for a in report.get('recommended_actions', []))
                    conf_level = html.escape(str(report.get('confidence', {}).get('level', '')))
                    conf_expl = html.escape(str(report.get('confidence', {}).get('explanation', '')))

                    followup_text = (
                        f"<strong>[AI IT Operations - Analyse Diagnostique]</strong><br/>"
                        f"<strong>Hypothèses :</strong> {escaped_hypotheses}<br/>"
                        f"<strong>Contrôles recommandés :</strong> {escaped_checks}<br/>"
                        f"<strong>Actions proposées :</strong> {escaped_actions}<br/>"
                        f"<strong>Confiance :</strong> {conf_level} ({conf_expl})"
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
