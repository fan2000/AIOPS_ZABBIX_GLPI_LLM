"""Tests d'intégration du graphe d'orchestration multi-agents LangGraph."""

import pytest
from packages.agents.src.graph import run_incident_analysis
from packages.agents.src.state import IncidentAgentState


@pytest.mark.asyncio
async def test_full_langgraph_workflow_cpu():
    initial_state: IncidentAgentState = {
        "incident_id": "test-inc-01",
        "ticket_id": 15248,
        "host_name": "SRV-APP-01",
        "zabbix_host_id": "10452",
        "primary_event": {
            "problem": "CPU utilization above 90%",
            "severity": "HIGH",
            "metric": "system.cpu.util",
            "value": 96.0,
            "host_name": "SRV-APP-01",
        },
        "events": [],
        "observations": [],
        "asset_info": {"operatingsystem": "Windows Server 2022"},
    }

    final_state = await run_incident_analysis(initial_state)

    assert "diagnostic_report" in final_state
    report = final_state["diagnostic_report"]
    assert report is not None
    assert report["host"] == "SRV-APP-01"
    assert len(report["observations"]) >= 1
    assert len(report["hypotheses"]) >= 1
    assert report["confidence"]["level"] in ["insufficient_evidence", "low", "moderate", "high"]
    assert final_state["validation_passed"] is True
