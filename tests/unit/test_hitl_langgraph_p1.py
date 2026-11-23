"""Tests unitaires P1 #5 : Boucle d'investigation lecture seule bornée et HITL LangGraph persistant."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
import pytest
from packages.agents.src import checkpointer as checkpointer_mod
from packages.agents.src.graph import (
    get_hitl_thread_state,
    resume_hitl_incident_analysis,
    start_hitl_incident_analysis,
)
from packages.agents.src.nodes import investigation_node
from packages.agents.src.state import IncidentAgentState
from packages.contracts.src.ai import KnowledgeSourceCitation


class _NonPostgresSession:
    """Fausse session asynchrone sans dialecte postgresql pour isoler le fallback InMemorySaver."""

    bind = None


@asynccontextmanager
async def _fake_non_pg_session_maker():
    yield _NonPostgresSession()


def _base_state(problem: str, host_name: str = "SRV-APP-01", metric: str = "system.cpu.util") -> IncidentAgentState:
    return {
        "incident_id": "inc-unit-p1-001",
        "ticket_id": 42,
        "entity_id": "0",
        "host_name": host_name,
        "zabbix_host_id": "host-text-id",
        "primary_event": {
            "event_id": "evt-900",
            "problem": problem,
            "severity": "HIGH",
            "metric": metric,
            "value": "97%",
        },
        "events": [
            {
                "event_id": "evt-900",
                "status": "PROBLEM",
                "severity": "HIGH",
                "metric": metric,
                "value": "97%",
            }
        ],
        "asset_info": {"operatingsystem": "Ubuntu Linux 22.04"},
        "metric_history": [],
        "approved_runbook_ids": [
            "rb-collect-top-processes",
            "rb-win-service-restart",
            "rb-linux-service-restart",
            "rb-disk-cleanup-logs",
        ],
        "observations": [],
    }


@pytest.mark.asyncio
async def test_investigation_loop_early_stop_when_no_evidence(monkeypatch):
    """Quand aucune nouvelle preuve n'est trouvée, l'investigation s'arrête dès l'itération 1."""
    monkeypatch.setenv("AIOPS_FAST_DIAGNOSIS", "true")
    monkeypatch.setattr(checkpointer_mod, "async_session_maker", _fake_non_pg_session_maker)
    monkeypatch.setattr(
        "packages.agents.src.nodes.knowledge_node.hybrid_retriever.search",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        investigation_node.hybrid_retriever,
        "search",
        AsyncMock(return_value=[]),
    )

    state = _base_state(
        problem="Anomalie métier propriétaire Z99 inconnue",
        host_name="SRV-APP-99",
        metric="custom.app.health",
    )
    res = await start_hitl_incident_analysis(state, thread_id="unit-inv-early-stop")
    final_state = res["state"]

    assert res["paused"] is False
    assert final_state["investigation_iterations"] == 1
    assert final_state["investigation_exhausted"] is True
    assert final_state["investigation_findings"] == []


@pytest.mark.asyncio
async def test_investigation_loop_bounded_to_max_two_iterations(monkeypatch):
    """Même avec insuffisance de preuves persistante, la boucle est strictement bornée à 2 itérations."""
    monkeypatch.setenv("AIOPS_FAST_DIAGNOSIS", "true")
    monkeypatch.setattr(checkpointer_mod, "async_session_maker", _fake_non_pg_session_maker)
    monkeypatch.setattr(
        "packages.agents.src.nodes.knowledge_node.hybrid_retriever.search",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        investigation_node.hybrid_retriever,
        "search",
        AsyncMock(return_value=[]),
    )

    # CORE-RTR-01 fournit un indice topologique au tour 1 -> relance diagnosis -> tour 2 sans nouvelle preuve -> arrêt
    state = _base_state(
        problem="Erreur propriétaire obscure Q77",
        host_name="CORE-RTR-01",
        metric="net.custom.check",
    )
    res = await start_hitl_incident_analysis(state, thread_id="unit-inv-max-2")
    final_state = res["state"]

    assert res["paused"] is False
    assert final_state["investigation_iterations"] == 2
    assert final_state["investigation_exhausted"] is True
    assert len(final_state["investigation_findings"]) == 1
    assert "CORE-RTR-01" in final_state["investigation_findings"][0]
    assert "Investigation Agent" in final_state.get("agent_telemetry", {})


@pytest.mark.asyncio
async def test_hitl_pauses_before_gate_and_resumes_on_approval(monkeypatch):
    """Un runbook MEDIUM (rb-disk-cleanup-logs) suspend le graphe avant human_approval_gate et reprend à l'approbation."""
    monkeypatch.setenv("AIOPS_FAST_DIAGNOSIS", "true")
    monkeypatch.setattr(checkpointer_mod, "async_session_maker", _fake_non_pg_session_maker)
    monkeypatch.setattr(
        "packages.agents.src.nodes.knowledge_node.hybrid_retriever.search",
        AsyncMock(
            return_value=[
                KnowledgeSourceCitation(
                    article_id="KB-DISK-01",
                    title="Saturation /var/log",
                    source_type="glpi_kb",
                    snippet="Purger /var/log/*.gz > 15j via rb-disk-cleanup-logs",
                    relevance_score=0.91,
                )
            ]
        ),
    )

    thread_id = "unit-hitl-approve-01"
    state = _base_state(
        problem="Disk usage above 95% on /var/log",
        host_name="SRV-WEB-01",
        metric="vfs.fs.size[/var/log,pused]",
    )

    started = await start_hitl_incident_analysis(state, thread_id=thread_id)
    assert started["paused"] is True
    assert started["next_nodes"] == ["human_approval_gate"]
    assert started["state"]["requires_human_approval"] is True
    assert started["state"]["hitl_status"] == "waiting_human_approval"
    assert started["state"]["pending_approval_action"]["runbook_id"] == "rb-disk-cleanup-logs"

    inspected = await get_hitl_thread_state(thread_id)
    assert inspected["exists"] is True
    assert inspected["paused"] is True
    assert inspected["next_nodes"] == ["human_approval_gate"]

    resumed = await resume_hitl_incident_analysis(
        thread_id=thread_id,
        human_approved=True,
        decided_by="operator_qa",
        technician_comment="Purge validée sur /var/log",
        action_execution_result={"stdout": "2.4 GB freed", "exit_code": 0},
    )
    assert resumed["paused"] is False
    assert resumed["next_nodes"] == []
    assert resumed["state"]["hitl_status"] == "resumed_approved"
    assert resumed["state"]["diagnostic_report"]["status"] == "approved"
    assert "2.4 GB freed" in resumed["state"]["kb_proposal"]["content"]
    assert "Purge validée sur /var/log" in resumed["state"]["kb_proposal"]["content"]


@pytest.mark.asyncio
async def test_hitl_resumes_on_rejection_without_execution(monkeypatch):
    """Un rejet opérateur reprend le graphe proprement jusqu'à feedback_agent sans résultat d'exécution."""
    monkeypatch.setenv("AIOPS_FAST_DIAGNOSIS", "true")
    monkeypatch.setattr(checkpointer_mod, "async_session_maker", _fake_non_pg_session_maker)
    monkeypatch.setattr(
        "packages.agents.src.nodes.knowledge_node.hybrid_retriever.search",
        AsyncMock(return_value=[]),
    )

    thread_id = "unit-hitl-reject-01"
    state = _base_state(
        problem="Service nginx down unexpectedly",
        host_name="SRV-WEB-02",
        metric="systemd.service.active[nginx]",
    )
    started = await start_hitl_incident_analysis(state, thread_id=thread_id)
    assert started["paused"] is True
    assert started["state"]["pending_approval_action"]["runbook_id"] == "rb-linux-service-restart"

    resumed = await resume_hitl_incident_analysis(
        thread_id=thread_id,
        human_approved=False,
        decided_by="admin_sec",
        technician_comment="Maintenance planifiée en cours",
        action_execution_result=None,
    )
    assert resumed["paused"] is False
    assert resumed["state"]["hitl_status"] == "resumed_rejected"
    assert resumed["state"]["diagnostic_report"]["status"] == "rejected"
    assert "Maintenance planifiée en cours" in resumed["state"]["kb_proposal"]["content"]


@pytest.mark.asyncio
async def test_read_only_low_risk_runbook_completes_without_hitl_pause(monkeypatch):
    """Un diagnostic CPU (rb-collect-top-processes, read_only) ne déclenche pas de pause HITL."""
    monkeypatch.setenv("AIOPS_FAST_DIAGNOSIS", "true")
    monkeypatch.setattr(checkpointer_mod, "async_session_maker", _fake_non_pg_session_maker)
    monkeypatch.setattr(
        "packages.agents.src.nodes.knowledge_node.hybrid_retriever.search",
        AsyncMock(
            return_value=[
                KnowledgeSourceCitation(
                    article_id="KB-CPU-01",
                    title="Diagnostic pic CPU",
                    source_type="glpi_kb",
                    snippet="Collecter le top processus",
                    relevance_score=0.89,
                )
            ]
        ),
    )

    state = _base_state(
        problem="CPU utilization above 95%",
        host_name="SRV-CPU-01",
        metric="system.cpu.util",
    )
    res = await start_hitl_incident_analysis(state, thread_id="unit-hitl-readonly-01")
    assert res["paused"] is False
    assert res["next_nodes"] == []
    assert res["state"]["requires_human_approval"] is False
    assert res["state"]["hitl_status"] == "completed"
    assert res["state"]["kb_proposal"] is not None
