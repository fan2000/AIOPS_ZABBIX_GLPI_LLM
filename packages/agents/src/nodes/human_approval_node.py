"""Nœud Porte d'Approbation Humaine (Human-in-the-Loop) : Reprise après décision opérateur."""

import time
from typing import Any, Dict, List
from packages.agents.src.state import IncidentAgentState
from packages.observability.src.metrics import record_agent_execution


async def human_approval_gate_node(state: IncidentAgentState) -> Dict[str, Any]:
    """Finalise la décision humaine (approuvé/rejeté), met à jour le rapport et audit avant Feedback."""
    t0 = time.perf_counter()
    approved = state.get("human_approved")
    decided_by = str(state.get("decided_by") or "technician")
    comment = state.get("technician_comment") or ""
    report = dict(state.get("diagnostic_report") or {})
    observations: List[str] = list(state.get("observations") or [])

    if approved is True:
        report["status"] = "approved"
        hitl_status = "resumed_approved"
        msg = f"Décision HITL : Remédiation APPROUVÉE par {decided_by}."
    elif approved is False:
        report["status"] = "rejected"
        hitl_status = "resumed_rejected"
        msg = f"Décision HITL : Remédiation REJETÉE par {decided_by}."
    else:
        hitl_status = "completed"
        msg = f"Décision HITL : Clôturé sans exécution par {decided_by}."

    if comment:
        msg = f"{msg} Note : {comment}"
    observations.append(msg)

    dur_ms = int((time.perf_counter() - t0) * 1000)
    record_agent_execution("human_approval_gate", "approved" if approved else "rejected")

    return {
        "diagnostic_report": report,
        "observations": observations,
        "hitl_status": hitl_status,
        "agent_telemetry": {
            "Human Approval Gate": {
                "duration_ms": dur_ms,
                "status": "ok",
                "approved": approved,
                "decided_by": decided_by,
            }
        },
    }
