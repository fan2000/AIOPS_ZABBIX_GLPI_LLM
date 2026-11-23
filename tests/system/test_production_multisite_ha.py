"""Tests de validation de mise en production (PROD), Haute Disponibilité (HA) et architectures Multi-Sites."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest
import yaml
from apps.api.src.main import app
from packages.connectors.redis_streams import RedisStreamsClient
from packages.connectors.zabbix.src.normalizer import normalize_zabbix_payload
from packages.domain.models.database import Incident
from services.incident_worker.src.correlation_engine import CorrelationEngine


@pytest.mark.asyncio
async def test_production_readiness_and_security_headers():
    """Vérifie l'endpoint d'audit PROD (/api/v1/system/production-readiness) et les en-têtes OWASP."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        custom_req_id = "req-prod-audit-998877"
        resp = await client.get(
            "/api/v1/system/production-readiness",
            headers={"X-Request-ID": custom_req_id},
        )
        assert resp.status_code == 200

        # Vérification des en-têtes de sécurité OWASP et traçabilité distribuée
        assert resp.headers.get("X-Request-ID") == custom_req_id
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "max-age=63072000" in resp.headers.get("Strict-Transport-Security", "")
        assert resp.headers.get("X-AIOps-Node") is not None

        data = resp.json()
        assert data["ready_for_production"] is True
        assert data["overall_score"] == 100
        assert data["deployment_grade"] == "ENTERPRISE_MULTI_SITE_HA"

        pillars = data["pillars"]
        for key in (
            "security_zero_trust",
            "high_availability_resilience",
            "multi_site_complex_networks",
            "business_continuity_dr",
            "observability_monitoring",
        ):
            assert key in pillars
            assert pillars[key]["status"] == "VALIDATED"
            assert pillars[key]["score"] == 100


@pytest.mark.asyncio
async def test_multi_site_topology_endpoint():
    """Vérifie la fédération multi-sites, proxies Zabbix et entités GLPI (/api/v1/system/multi-site-topology)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/system/multi-site-topology")
        assert resp.status_code == 200
        data = resp.json()
        assert data["architecture_mode"] == "FEDERATED_MULTI_SITE_HA"
        assert data["total_sites"] == 4
        site_codes = {s["site_code"] for s in data["sites"]}
        assert site_codes == {"PAR-DC1", "LYN-DC2", "MAR-EDGE-01", "CLD-EU-WEST"}


def test_multi_site_normalization_and_network_zones():
    """Vérifie la qualification automatique des sites, zones réseaux (CORE/DMZ/OT/CLOUD), proxies et entités GLPI."""
    # 1. Routeur cœur sur site Lyon DR
    ev_lyon = normalize_zabbix_payload({
        "event_id": "EVT-LYN-001",
        "event_type": "PROBLEM",
        "host_id": "2001",
        "host_name": "LYN-CORE-RTR-01",
        "trigger_id": "9100",
        "severity": "DISASTER",
        "problem": "Core Router BGP peer down on LYN-CORE-RTR-01",
        "metric": "net.if.status",
        "value": 0,
    })
    assert ev_lyon.site_code == "LYN-DC2"
    assert ev_lyon.network_zone == "CORE"
    assert ev_lyon.zabbix_proxy == "zbx-proxy-lyn-dc2"
    assert ev_lyon.entity_id == "2"

    # 2. Automate industriel OT sur site régional Marseille
    ev_ot = normalize_zabbix_payload({
        "event_id": "EVT-MAR-002",
        "event_type": "PROBLEM",
        "host_id": "3001",
        "host_name": "MAR-OT-SCADA-01",
        "trigger_id": "9200",
        "severity": "HIGH",
        "problem": "Modbus gateway latency high",
    })
    assert ev_ot.site_code == "MAR-EDGE-01"
    assert ev_ot.network_zone == "OT"
    assert ev_ot.zabbix_proxy == "zbx-proxy-mar-edge-01"
    assert ev_ot.entity_id == "3"

    # 3. Firewall WAF en DMZ Paris
    ev_dmz = normalize_zabbix_payload({
        "event_id": "EVT-PAR-003",
        "event_type": "PROBLEM",
        "host_id": "1050",
        "host_name": "PAR-DMZ-WAF-01",
        "trigger_id": "9300",
        "severity": "HIGH",
        "problem": "TLS handshake spike in DMZ",
    })
    assert ev_dmz.site_code == "PAR-DC1"
    assert ev_dmz.network_zone == "DMZ"
    assert ev_dmz.entity_id == "1"


@pytest.mark.asyncio
async def test_multi_site_storm_correlation_engine():
    """Vérifie que le moteur de corrélation regroupe une tempête d'alertes réseau sur un même site distant."""
    engine = CorrelationEngine(window_minutes=15)

    # Incident racine : Panne du routeur WAN/Core du site de Lyon (LYN-DC2, entité 2)
    root_site_incident = Incident(
        incident_number="INC-20261118-LYNROOT",
        title="Core Router WAN Gateway unreachable sur LYN-CORE-GW-01",
        severity="DISASTER",
        status="OPEN",
        primary_asset_name="LYN-CORE-GW-01",
        zabbix_host_id="2001",
        entity_id="2",
        incident_metadata={"site_code": "LYN-DC2", "network_zone": "CORE"},
    )

    # Événement dépendant sur un serveur du même site (LYN-APP-02) signalant une perte ping ICMP
    dependent_event = normalize_zabbix_payload({
        "event_id": "EVT-LYN-STORM-02",
        "event_type": "PROBLEM",
        "host_id": "2055",
        "host_name": "LYN-APP-02",
        "trigger_id": "9555",
        "severity": "HIGH",
        "problem": "Host unreachable via ICMP ping",
        "metric": "icmpping",
        "value": 0,
    })

    # Simulation de la session SQLAlchemy : Règle 1 (même hôte) renvoie None, Règle 3 (même site) renvoie root_site_incident
    mock_session = AsyncMock()
    res_rule1 = MagicMock()
    res_rule1.scalar_one_or_none.return_value = None

    res_rule3 = MagicMock()
    res_rule3.scalars.return_value.all.return_value = [root_site_incident]

    mock_session.execute.side_effect = [res_rule1, res_rule3]

    correl = await engine.find_correlated_incident(dependent_event, mock_session)
    assert correl is not None
    matched_inc, corr_type, confidence = correl
    assert matched_inc.incident_number == "INC-20261118-LYNROOT"
    assert corr_type == "SITE_TOPOLOGY_CORRELATION"
    assert confidence == 0.92


@pytest.mark.asyncio
async def test_redis_ha_failover_and_dlq_continuity():
    """Vérifie la continuité RPO=0 en cas de perte Redis et l'isolation en Dead-Letter Queue (DLQ)."""
    # Client pointant vers un port fermé pour simuler une bascule cluster Redis
    ha_client = RedisStreamsClient(redis_url="redis://localhost:6399/0")
    msg_id = await ha_client.publish_event("zabbix:events", {"event_id": "HA-1", "problem": "Test failover"})
    assert msg_id is not None

    consumed = await ha_client.consume_events("zabbix:events", "orchestrator-group", "worker-ha", count=5)
    assert len(consumed) == 1
    assert consumed[0][1]["event_id"] == "HA-1"

    # Vérification de l'isolation Dead-Letter Queue (DLQ)
    dlq_id = await ha_client.publish_to_dlq("zabbix:events", msg_id, {"corrupted": True}, "Schema validation error")
    assert dlq_id is not None
    dlq_items = ha_client.get_dlq_messages("zabbix:events")
    assert len(dlq_items) == 1
    assert dlq_items[0]["original_msg_id"] == msg_id


def test_production_manifests_and_dockerfiles_hardening():
    """Vérifie la validité syntaxique et le durcissement sécurité des manifestes Docker PROD et Kubernetes."""
    root = Path(__file__).resolve().parents[2]

    # 1. Vérification docker-compose.prod.yml
    prod_compose = root / "docker-compose.prod.yml"
    assert prod_compose.exists()
    compose_data = yaml.safe_load(prod_compose.read_text(encoding="utf-8"))
    assert "api-gateway" in compose_data["services"]
    assert "no-new-privileges:true" in compose_data["services"]["api-gateway"]["security_opt"]

    # 2. Vérification Kubernetes Multi-Site HA manifest
    k8s_manifest = root / "infrastructure" / "kubernetes" / "aiops-multi-site-ha.yaml"
    assert k8s_manifest.exists()
    docs = list(yaml.safe_load_all(k8s_manifest.read_text(encoding="utf-8")))
    kinds = {d["kind"] for d in docs if d}
    assert {"Namespace", "ConfigMap", "Deployment", "PodDisruptionBudget", "HorizontalPodAutoscaler", "NetworkPolicy"}.issubset(kinds)

    # 3. Vérification utilisateur non-root (USER aiops) et HEALTHCHECK dans les Dockerfiles
    for df_name in ("Dockerfile.api", "Dockerfile.worker", "Dockerfile.frontend"):
        content = (root / "infrastructure" / "docker" / df_name).read_text(encoding="utf-8")
        assert "USER aiops" in content, f"{df_name} doit s'exécuter avec un utilisateur non-root"
        assert "HEALTHCHECK" in content, f"{df_name} doit définir une sonde HEALTHCHECK"
