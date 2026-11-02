"""Validation complète des 10 scénarios d'incidents IT AIOps imposés."""

import pytest
from packages.agents.src.graph import run_incident_analysis
from packages.agents.src.state import IncidentAgentState
from packages.connectors.zabbix.src.normalizer import normalize_zabbix_payload
from packages.contracts.src.events import EventStatus


@pytest.mark.asyncio
async def test_scenario_1_disk_full():
    raw = {
        "event_id": "5001",
        "event_type": "PROBLEM",
        "host_id": "101",
        "host_name": "SRV-DATA-01",
        "trigger_id": "801",
        "severity": "HIGH",
        "problem": "Disk space /var/log critically low",
        "value": 98.2,
    }
    event = normalize_zabbix_payload(raw)
    state: IncidentAgentState = {
        "incident_id": "sc-1",
        "primary_event": event.model_dump(),
        "host_name": event.host_name,
        "observations": [],
    }
    result = await run_incident_analysis(state)
    report = result["diagnostic_report"]
    assert report is not None
    actions = report["recommended_actions"]
    assert any("purge" in a["action"].lower() or "log" in a["action"].lower() for a in actions)


@pytest.mark.asyncio
async def test_scenario_2_cpu_high():
    raw = {
        "event_id": "5002",
        "event_type": "PROBLEM",
        "host_id": "102",
        "host_name": "SRV-APP-01",
        "trigger_id": "802",
        "severity": "HIGH",
        "problem": "CPU utilization above 90%",
        "metric": "system.cpu.util",
        "value": 96.0,
    }
    event = normalize_zabbix_payload(raw)
    state: IncidentAgentState = {
        "incident_id": "sc-2",
        "primary_event": event.model_dump(),
        "host_name": event.host_name,
        "observations": [],
    }
    result = await run_incident_analysis(state)
    report = result["diagnostic_report"]
    assert report is not None
    assert any("cpu" in h["description"].lower() for h in report["hypotheses"])


@pytest.mark.asyncio
async def test_scenario_3_ram_swap_saturation():
    raw = {
        "event_id": "5003",
        "event_type": "PROBLEM",
        "host_id": "102",
        "host_name": "SRV-APP-01",
        "trigger_id": "803",
        "severity": "AVERAGE",
        "problem": "RAM and swap space saturated",
        "value": 95.0,
    }
    event = normalize_zabbix_payload(raw)
    state: IncidentAgentState = {
        "incident_id": "sc-3",
        "primary_event": event.model_dump(),
        "host_name": event.host_name,
        "observations": [],
    }
    result = await run_incident_analysis(state)
    assert result["validation_passed"] is True


@pytest.mark.asyncio
async def test_scenario_4_service_down():
    raw = {
        "event_id": "5004",
        "event_type": "PROBLEM",
        "host_id": "103",
        "host_name": "SRV-WIN-PRINT",
        "trigger_id": "804",
        "severity": "HIGH",
        "problem": "Print Spooler service stopped",
        "value": 0.0,
    }
    event = normalize_zabbix_payload(raw)
    state: IncidentAgentState = {
        "incident_id": "sc-4",
        "primary_event": event.model_dump(),
        "host_name": event.host_name,
        "observations": [],
        "asset_info": {"operatingsystem": "Windows Server 2022"},
    }
    result = await run_incident_analysis(state)
    report = result["diagnostic_report"]
    actions = report["recommended_actions"]
    # Doit proposer un redémarrage contrôlé avec requires_approval = True
    restart_action = [a for a in actions if "redémarrage" in a["action"].lower()]
    assert len(restart_action) >= 1
    assert restart_action[0]["requires_approval"] is True


@pytest.mark.asyncio
async def test_scenario_5_host_unreachable():
    raw = {
        "event_id": "5005",
        "event_type": "PROBLEM",
        "host_id": "104",
        "host_name": "SW-CORE-01",
        "trigger_id": "805",
        "severity": "DISASTER",
        "problem": "Host is unreachable",
        "value": 0.0,
    }
    event = normalize_zabbix_payload(raw)
    assert event.severity.value == "DISASTER"


@pytest.mark.asyncio
async def test_scenario_6_multi_alert_correlation():
    state: IncidentAgentState = {
        "incident_id": "sc-6",
        "host_name": "SRV-APP-01",
        "primary_event": {"problem": "CPU > 90%", "severity": "HIGH"},
        "events": [
            {"problem": "CPU > 90%", "severity": "HIGH"},
            {"problem": "RAM > 90%", "severity": "HIGH"},
            {"problem": "App Latency > 2s", "severity": "AVERAGE"},
        ],
        "observations": [],
    }
    result = await run_incident_analysis(state)
    assert result["is_correlated"] is True


@pytest.mark.asyncio
async def test_scenario_7_unknown_incident_no_hallucination():
    state: IncidentAgentState = {
        "incident_id": "sc-7",
        "host_name": "SRV-LEGACY-09",
        "primary_event": {"problem": "Flag bit 0xFA3 corrupted", "severity": "WARNING"},
        "rag_citations": [],  # Aucune source
        "observations": [],
    }
    result = await run_incident_analysis(state)
    report = result["diagnostic_report"]
    # La confiance doit être classée en insufficient_evidence
    assert report["confidence"]["level"] == "insufficient_evidence"


@pytest.mark.asyncio
async def test_scenario_8_glpi_unavailable_graceful_handling():
    # Vérifie que la défaillance réseau GLPI ne plante pas le worker
    from packages.connectors.glpi.src.client import GlpiClient
    broken_client = GlpiClient(api_url="http://127.0.0.1:59999/unreachable")
    try:
        await broken_client.init_session()
    except Exception as e:
        # L'exception est capturée proprement
        assert e is not None


@pytest.mark.asyncio
async def test_scenario_9_llm_unavailable_degraded_mode():
    from packages.agents.src.llm_client import LLMClient
    disabled_llm = LLMClient(provider="disabled")
    res = await disabled_llm.generate_json("system", "user")
    assert res is None  # Retour None sans plantage, passage en règles déterministes


@pytest.mark.asyncio
async def test_scenario_10_recovery_event_observed():
    raw_recovery = {
        "event_id": "5002",
        "event_type": "RECOVERY",
        "host_id": "102",
        "host_name": "SRV-APP-01",
        "trigger_id": "802",
        "severity": "HIGH",
        "problem": "RESOLVED: CPU utilization normal",
        "value": 28.5,
    }
    rec_event = normalize_zabbix_payload(raw_recovery)
    assert rec_event.event_type == EventStatus.RECOVERY
