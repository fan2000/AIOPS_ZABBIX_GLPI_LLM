"""Gestion et consultation des incidents AIOps et de leurs diagnostics."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import get_db_session
from packages.agents.src.graph import run_incident_analysis
from packages.agents.src.state import IncidentAgentState
from packages.contracts.src.incident import IncidentRead
from packages.domain.models.database import (
    AIAnalysisRun,
    AIRecommendation,
    Incident,
    IncidentEvent,
    IncidentFeedback,
)

router = APIRouter(prefix="/api/v1/incidents", tags=["Incidents"])


@router.get("", response_model=List[IncidentRead])
async def list_incidents(
    status_filter: Optional[str] = Query(None, alias="status"),
    severity_filter: Optional[str] = Query(None, alias="severity"),
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> List[Incident]:
    """Liste les incidents avec filtres optionnels par statut ou sévérité."""
    stmt = select(Incident).order_by(desc(Incident.opened_at)).limit(limit)
    if status_filter:
        stmt = stmt.where(Incident.status == status_filter.upper())
    if severity_filter:
        stmt = stmt.where(Incident.severity == severity_filter.upper())

    results = (await session.execute(stmt)).scalars().all()
    return list(results)


@router.get("/{incident_id}")
async def get_incident(
    incident_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retourne le détail d'un incident, ses événements et sa dernière analyse."""
    stmt = select(Incident).where(Incident.id == incident_id)
    inc = (await session.execute(stmt)).scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident introuvable")

    # Événements associés
    ev_stmt = select(IncidentEvent).where(IncidentEvent.incident_id == incident_id).order_by(desc(IncidentEvent.event_timestamp))
    events = (await session.execute(ev_stmt)).scalars().all()

    # Dernière analyse IA
    ai_stmt = select(AIAnalysisRun).where(AIAnalysisRun.incident_id == incident_id).order_by(desc(AIAnalysisRun.created_at)).limit(1)
    analysis = (await session.execute(ai_stmt)).scalar_one_or_none()

    return {
        "id": str(inc.id),
        "incident_number": inc.incident_number,
        "title": inc.title,
        "severity": inc.severity,
        "status": inc.status,
        "primary_asset_name": inc.primary_asset_name,
        "zabbix_host_id": inc.zabbix_host_id,
        "glpi_ticket_id": inc.glpi_ticket_id,
        "opened_at": inc.opened_at.isoformat(),
        "recovery_at": inc.recovery_at.isoformat() if inc.recovery_at else None,
        "events_count": len(events),
        "events": [
            {
                "event_id": e.zabbix_event_id,
                "status": e.event_status,
                "severity": e.severity,
                "metric": e.metric_key,
                "value": e.metric_value,
                "timestamp": e.event_timestamp.isoformat(),
            }
            for e in events
        ],
        "latest_analysis": {
            "model": analysis.model_name,
            "hypotheses": analysis.hypotheses,
            "checks": analysis.checks,
            "confidence_level": analysis.confidence_level,
            "confidence_explanation": analysis.confidence_explanation,
            "created_at": analysis.created_at.isoformat(),
        } if analysis else None,
    }


@router.post("/{incident_id}/analyze")
async def trigger_incident_analysis(
    incident_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Déclenche manuellement une nouvelle analyse LangGraph pour un incident."""
    stmt = select(Incident).where(Incident.id == incident_id)
    inc = (await session.execute(stmt)).scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident introuvable")

    ev_stmt = select(IncidentEvent).where(IncidentEvent.incident_id == incident_id).order_by(desc(IncidentEvent.event_timestamp))
    events = (await session.execute(ev_stmt)).scalars().all()

    primary_event_data = {
        "problem": inc.title,
        "severity": inc.severity,
        "host_name": inc.primary_asset_name,
        "host_id": inc.zabbix_host_id,
    }

    state: IncidentAgentState = {
        "incident_id": str(inc.id),
        "ticket_id": int(inc.glpi_ticket_id) if inc.glpi_ticket_id and inc.glpi_ticket_id.isdigit() else None,
        "host_name": inc.primary_asset_name,
        "zabbix_host_id": inc.zabbix_host_id,
        "primary_event": primary_event_data,
        "events": [primary_event_data],
        "observations": [],
    }

    result = await run_incident_analysis(state)
    report = result.get("diagnostic_report", {})

    # Persistance de l'analyse
    ai_run = AIAnalysisRun(
        incident_id=inc.id,
        model_name="langgraph_orchestrator",
        hypotheses=report.get("hypotheses", []),
        checks=report.get("checks", []),
        confidence_level=report.get("confidence", {}).get("level", "moderate"),
        confidence_explanation=report.get("confidence", {}).get("explanation", ""),
    )
    session.add(ai_run)
    await session.commit()

    return {"status": "analyzed", "report": report}
