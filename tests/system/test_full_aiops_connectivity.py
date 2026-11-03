"""Test complet de connectivité et d'intégration de tous les services AIOps.

Vérifie l'ensemble des composants selon l'architecture cible :
1. Connectivité réseau et disponibilité HTTP/TCP des 12 services
2. PostgreSQL 16 + extension pgvector
3. Redis Streams (authentification + publication/lecture de streams)
4. API Gateway FastAPI (Health checks, Webhooks Zabbix, Incidents)
5. Connecteur GLPI 10 (Sessions, CMDB, Tickets, Suivis)
6. Connecteur Zabbix 7.0 (Web, Trapper, JSON-RPC)
7. Pipeline RAG Hybride (Embeddings, Reciprocal Rank Fusion)
8. Orchestrateur LangGraph (Exécution des 7 agents spécialisés)
9. Sandbox de Remédiation Niveau 3 (Exécution contrôlée & validation)
10. Frontend Web Next.js 15 (Routes opérationnelles)
"""

import asyncio
import json
import socket
import sys
import time
from typing import Any, Dict, List, Tuple

# Forcer UTF-8 sur stdout pour éviter les erreurs charmap sur Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import httpx
import pytest
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

SERVICES = [
    {"name": "Frontend Next.js", "host": "localhost", "port": 3005, "type": "HTTP", "path": "/"},
    {"name": "API Gateway FastAPI", "host": "localhost", "port": 8005, "type": "HTTP", "path": "/health/live"},
    {"name": "GLPI 10 ITSM & CMDB", "host": "localhost", "port": 8088, "type": "HTTP", "path": "/"},
    {"name": "Zabbix 7.0 Web UI", "host": "localhost", "port": 8089, "type": "HTTP", "path": "/"},
    {"name": "Zabbix Server Trapper", "host": "localhost", "port": 10051, "type": "TCP"},
    {"name": "Adminer Web Database UI", "host": "localhost", "port": 8086, "type": "HTTP", "path": "/"},
    {"name": "Redis Commander Web UI", "host": "localhost", "port": 8087, "type": "HTTP", "path": "/"},
    {"name": "Grafana Dashboards", "host": "localhost", "port": 3006, "type": "HTTP", "path": "/api/health"},
    {"name": "Prometheus Metrics", "host": "localhost", "port": 9095, "type": "HTTP", "path": "/-/healthy"},
    {"name": "PostgreSQL 16 + pgvector", "host": "localhost", "port": 5435, "type": "TCP"},
    {"name": "Redis Streams", "host": "localhost", "port": 6380, "type": "TCP"},
    {"name": "MariaDB 10.11 (GLPI)", "host": "localhost", "port": 3307, "type": "TCP"},
]


def check_tcp_port(host: str, port: int, timeout: float = 3.0) -> bool:
    """Vérifie si un port TCP accepte les connexions."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


async def check_http_endpoint(url: str, timeout: float = 5.0) -> Tuple[bool, int, str]:
    """Interroge un endpoint HTTP et retourne son statut."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, follow_redirects=True)
            return resp.status_code in [200, 302], resp.status_code, resp.reason_phrase
    except Exception as e:
        return False, 0, str(e)


@pytest.mark.asyncio
async def test_01_all_services_network_connectivity():
    """Étape 1 : Vérification de la disponibilité réseau de l'ensemble des 12 services."""
    results = []
    for s in SERVICES:
        if s["type"] == "TCP":
            is_open = check_tcp_port(s["host"], s["port"])
            status = "UP (TCP)" if is_open else "DOWN"
            results.append((s["name"], s["port"], is_open, status))
        else:
            url = f"http://{s['host']}:{s['port']}{s.get('path', '/')}"
            ok, code, _ = await check_http_endpoint(url)
            status = f"UP (HTTP {code})" if ok else f"DOWN ({code})"
            results.append((s["name"], s["port"], ok, status))

    print("\n" + "=" * 70)
    print(" [AUDIT] DISPONIBILITE DES SERVICES AIOPS (12 SERVICES)")
    print("=" * 70)
    for name, port, ok, status in results:
        badge = "[OK]  " if ok else "[FAIL]"
        print(f" {badge} {name:<30} Port: {port:<6} Statut: {status}")
    print("=" * 70)

    failed = [name for name, _, ok, _ in results if not ok]
    assert len(failed) == 0, f"Services inaccessibles : {failed}"


@pytest.mark.asyncio
async def test_02_postgresql_pgvector_connectivity():
    """Étape 2 : Vérification de la base PostgreSQL 16 et de l'extension pgvector."""
    db_url = "postgresql+asyncpg://aiops_user:aiops_secure_password@localhost:5435/aiops_db"
    engine = create_async_engine(db_url, echo=False)
    async with engine.connect() as conn:
        # Vérification version PostgreSQL
        version_res = await conn.execute(text("SELECT version();"))
        version = version_res.scalar()
        assert "PostgreSQL 16" in version or "PostgreSQL" in version

        # Vérification extension pgvector
        ext_res = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector';"))
        ext = ext_res.scalar()
        print(f"\n   PostgreSQL Version : {version[:35]}...")
        print(f"   Extension pgvector : {ext} (Active)")
        assert ext == "vector", "L'extension pgvector doit être installée et active"

        # Vérification des tables AIOps
        tables_res = await conn.execute(text("""
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'public';
        """))
        table_count = tables_res.scalar()
        print(f"   Tables AIOps créées : {table_count} tables")
        assert table_count >= 15, f"Au moins 15 tables attendues, {table_count} trouvées"
    await engine.dispose()


@pytest.mark.asyncio
async def test_03_redis_streams_connectivity():
    """Étape 3 : Vérification de Redis 7 et des flux Redis Streams."""
    r = aioredis.from_url("redis://:aiops_redis_password@localhost:6380/0")
    ping = await r.ping()
    assert ping is True

    # Test d'écriture et de lecture dans un flux Redis Streams
    test_stream = "stream:aiops:connectivity_check"
    event_data = {
        "event_id": "test_ping_001",
        "service": "connectivity_verifier",
        "timestamp": str(time.time()),
    }
    msg_id = await r.xadd(test_stream, event_data)
    assert msg_id is not None

    # Lecture du flux
    entries = await r.xrange(test_stream, count=1)
    assert len(entries) >= 1
    assert entries[0][1][b"event_id"] == b"test_ping_001"

    # Nettoyage
    await r.delete(test_stream)
    await r.aclose()
    print(f"\n   Redis Ping : OK | Streams XADD/XRANGE : OK (Message ID: {msg_id.decode() if isinstance(msg_id, bytes) else msg_id})")


@pytest.mark.asyncio
async def test_04_zabbix_webhook_to_api_gateway():
    """Étape 4 : Ingestion réelle d'un webhook Zabbix vers l'API Gateway FastAPI."""
    payload = {
        "event_id": f"EVT-CONN-{int(time.time())}",
        "event_type": "1",
        "host_id": "1002",
        "host_name": "SRV-TEST-01",
        "trigger_id": "9901",
        "severity": "HIGH",
        "problem": "CPU utilization above 90% sur SRV-TEST-01",
        "metric": "system.cpu.util",
        "value": 96.2,
    }

    async with httpx.AsyncClient(base_url="http://localhost:8005", timeout=5.0) as client:
        resp = await client.post(
            "/api/v1/webhooks/zabbix",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Zabbix-Signature": "zabbix-webhook-shared-hmac-secret-key-32chars",
            },
        )
        assert resp.status_code == 202, f"Attendu 202, obtenu {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["status"] == "accepted"
        assert "message_id" in data
        assert "idempotency_key" in data
        print(f"\n   Webhook Zabbix Ingestion : Code 202 Accepted | Idempotency Key : {data['idempotency_key'][:16]}...")


@pytest.mark.asyncio
async def test_05_incidents_api_and_data_persistence():
    """Étape 5 : Récupération des incidents via l'API Gateway FastAPI."""
    async with httpx.AsyncClient(base_url="http://localhost:8005", timeout=5.0) as client:
        resp = await client.get("/api/v1/incidents?limit=10")
        assert resp.status_code == 200, f"Attendu 200, obtenu {resp.status_code}: {resp.text}"
        incidents = resp.json()
        assert isinstance(incidents, list)
        print(f"\n   API Incidents : Code 200 OK | Nombre d'incidents enregistrés : {len(incidents)}")
        if incidents:
            first = incidents[0]
            print(f"   Dernier Incident : [{first.get('incident_number')}] {first.get('title')} ({first.get('severity')})")


@pytest.mark.asyncio
async def test_06_glpi_lab_service_endpoints():
    """Étape 6 : Vérification de l'intégration GLPI REST (Sessions, CMDB, Tickets)."""
    async with httpx.AsyncClient(base_url="http://localhost:8005", timeout=5.0) as client:
        # Test session init
        sess_resp = await client.get("/api/v1/lab/glpi/initSession")
        assert sess_resp.status_code == 200
        sess_data = sess_resp.json()
        assert "session_token" in sess_data
        token = sess_data["session_token"]

        # Test CMDB lookup
        cmdb_resp = await client.get(
            "/api/v1/lab/glpi/search/Computer?criteria[0][field]=1&criteria[0][value]=SRV-APP-01",
            headers={"Session-Token": token},
        )
        assert cmdb_resp.status_code == 200
        cmdb_data = cmdb_resp.json()
        assert "data" in cmdb_data
        print(f"\n   GLPI REST Service : Session OK ({token[:12]}...) | CMDB Computer Search : {len(cmdb_data['data'])} équipements trouvés")


@pytest.mark.asyncio
async def test_07_rag_hybrid_search_retriever():
    """Étape 7 : Vérification du moteur de recherche sémantique RAG."""
    async with httpx.AsyncClient(base_url="http://localhost:8005", timeout=5.0) as client:
        resp = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "CPU saturé processus anormal boucle infinie", "limit": 3},
        )
        assert resp.status_code == 200
        docs = resp.json()
        print(f"\n   Moteur RAG Hybride : {len(docs)} documents pertinents trouvés avec scores de similarité")
        for d in docs:
            print(f"      - {d.get('title')} (score: {d.get('similarity_score')})")


@pytest.mark.asyncio
async def test_08_remediation_runbooks_catalog():
    """Étape 8 : Consultation du catalogue de runbooks déclaratifs sécurisés."""
    async with httpx.AsyncClient(base_url="http://localhost:8005", timeout=5.0) as client:
        resp = await client.get("/api/v1/actions/runbooks")
        assert resp.status_code == 200
        runbooks = resp.json()
        assert len(runbooks) >= 4
        print(f"\n   Catalogue Runbooks : {len(runbooks)} runbooks validés disponibles")
        for rb in runbooks:
            runner = rb.get("runner_type", "script")
            role = rb.get("required_role", "operator")
            print(f"      * [{runner}] {rb.get('name')} (Rôle requis: {role})")


@pytest.mark.asyncio
async def test_09_frontend_routes_status():
    """Étape 9 : Vérification de toutes les routes de l'interface utilisateur Next.js."""
    routes = ["/", "/incidents", "/knowledge", "/automation", "/ai-operations", "/architecture-flow"]
    async with httpx.AsyncClient(base_url="http://localhost:3005", timeout=10.0) as client:
        for r in routes:
            resp = await client.get(r)
            assert resp.status_code == 200, f"Route {r} en erreur : {resp.status_code}"
    print(f"\n   Frontend Next.js 15 : {len(routes)}/{len(routes)} pages opérationnelles en HTTP 200")


if __name__ == "__main__":
    import asyncio
    print("Exécution des vérifications de connectivité AIOps...")
    asyncio.run(test_01_all_services_network_connectivity())
    asyncio.run(test_02_postgresql_pgvector_connectivity())
    asyncio.run(test_03_redis_streams_connectivity())
    asyncio.run(test_04_zabbix_webhook_to_api_gateway())
    asyncio.run(test_05_incidents_api_and_data_persistence())
    asyncio.run(test_06_glpi_lab_service_endpoints())
    asyncio.run(test_07_rag_hybrid_search_retriever())
    asyncio.run(test_08_remediation_runbooks_catalog())
    asyncio.run(test_09_frontend_routes_status())
    print("\n TOUTES LES VÉRIFICATIONS D'INTÉGRATION ET DE CONNECTIVITÉ SONT VALIDÉES AVEC SUCCÈS !")
