"""Tests d'intégration de non-régression pour les correctifs d'audit sécurité API & HTTP."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user
from database.connection import get_db_session
from apps.api.src.main import app


def _make_user(role: str = "operator", allowed_entities=None) -> AuthenticatedUserContext:
    return AuthenticatedUserContext(
        id=uuid4(),
        username=f"test-{role}",
        role=role,
        permissions=["*"],
        allowed_entities=["1"] if allowed_entities is None else allowed_entities,
    )


def _mock_session_sequence(*items):
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    results = []
    for item in items:
        res = MagicMock()
        res.scalar_one_or_none.return_value = item
        results.append(res)
    session.execute = AsyncMock(side_effect=results)
    return session


@contextmanager
def _with_overrides(user=None, session=None):
    prev = dict(app.dependency_overrides)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    if session is not None:
        async def _fake_db():
            yield session
        app.dependency_overrides[get_db_session] = _fake_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides = prev


def test_incident_analyze_requires_auth_role_and_entity_isolation():
    inc_id = uuid4()

    with _with_overrides() as client:
        resp_unauth = client.post(f"/api/v1/incidents/{inc_id}/analyze")
        assert resp_unauth.status_code == 401

    viewer = _make_user(role="viewer", allowed_entities=["0", "1"])
    with _with_overrides(user=viewer, session=_mock_session_sequence()) as client:
        resp_viewer = client.post(f"/api/v1/incidents/{inc_id}/analyze")
        assert resp_viewer.status_code == 403

    inc_other_entity = SimpleNamespace(id=inc_id, entity_id="99")
    operator_entity_1 = _make_user(role="operator", allowed_entities=["1"])
    session = _mock_session_sequence(inc_other_entity)
    with _with_overrides(user=operator_entity_1, session=session) as client:
        resp_idor = client.post(f"/api/v1/incidents/{inc_id}/analyze")
        assert resp_idor.status_code == 403
        assert "entité GLPI" in resp_idor.json()["detail"]
        session.add.assert_called_once()
        assert session.add.call_args.args[0].action == "INCIDENT_IDOR_BLOCKED"


def test_execute_runbook_blocks_cross_entity_idor():
    inc_id = uuid4()
    inc_other = SimpleNamespace(id=inc_id, entity_id="99")
    rb = SimpleNamespace(identifier="rb-collect-top-processes", is_enabled=True, required_role="operator")
    session = _mock_session_sequence(inc_other, rb)
    operator_entity_1 = _make_user(role="operator", allowed_entities=["1"])

    with _with_overrides(user=operator_entity_1, session=session) as client:
        resp = client.post(
            "/api/v1/actions/execute",
            json={
                "runbook_id": "rb-collect-top-processes",
                "incident_id": str(inc_id),
                "parameters": {},
                "approved_by_user_id": "test-operator",
            },
        )
        assert resp.status_code == 403
        assert "entité GLPI" in resp.json()["detail"]
        session.add.assert_called_once()
        assert session.add.call_args.args[0].action == "RUNBOOK_IDOR_BLOCKED"


def test_incident_feedback_blocks_cross_entity_idor():
    inc_id = uuid4()
    inc_other = SimpleNamespace(id=inc_id, entity_id="99")
    session = _mock_session_sequence(inc_other)
    operator_entity_1 = _make_user(role="operator", allowed_entities=["1"])

    with _with_overrides(user=operator_entity_1, session=session) as client:
        resp = client.post(
            f"/api/v1/incidents/{inc_id}/feedback",
            json={
                "is_recommendation_accepted": True,
                "rating_score": 5,
                "feedback_notes": "Test cross-tenant",
                "generate_kb_proposal": False,
            },
        )
        assert resp.status_code == 403
        assert "entité GLPI" in resp.json()["detail"]
        session.add.assert_called_once()
        assert session.add.call_args.args[0].action == "INCIDENT_IDOR_BLOCKED"


def test_decide_approval_returns_400_on_invalid_parameter_override(monkeypatch):
    import apps.api.src.routers.actions as act_mod

    approval_id = uuid4()
    inc_id = uuid4()
    approval = SimpleNamespace(
        id=approval_id,
        incident_id=inc_id,
        runbook_identifier="rb-restart-service",
        parameters={"host": "srv-01", "service_name": "nginx"},
        status="pending_approval",
        risk_level="HIGH",
    )
    inc = SimpleNamespace(id=inc_id, entity_id="1", status="IN_PROGRESS")
    rb = SimpleNamespace(
        identifier="rb-restart-service",
        name="Restart service",
        description="Restart Linux service",
        runner_type="bash_ssh",
        target_os="linux",
        timeout_seconds=30,
        required_role="operator",
        parameter_schema={},
        template_command="systemctl restart {{service_name}}",
        is_enabled=True,
    )
    session = _mock_session_sequence(approval, inc, rb)
    monkeypatch.setattr(
        act_mod.remediation_runner,
        "execute",
        AsyncMock(side_effect=ValueError("Caractères dangereux détectés dans le paramètre (CWE-78)")),
    )

    operator = _make_user(role="operator", allowed_entities=["1"])
    with _with_overrides(user=operator, session=session) as client:
        resp = client.post(
            f"/api/v1/actions/approvals/{approval_id}/decide",
            json={
                "approved": True,
                "comment": "Override malformé",
                "parameters_override": {"service_name": "nginx; rm -rf /"},
            },
        )
        assert resp.status_code == 400
        assert "CWE-78" in resp.json()["detail"]


def test_lab_inject_requires_auth_operator_and_blocks_production(monkeypatch):
    with _with_overrides() as client:
        resp_unauth = client.post("/api/v1/lab/scenarios/2_cpu_high/inject")
        assert resp_unauth.status_code == 401

    viewer = _make_user(role="viewer")
    with _with_overrides(user=viewer) as client:
        resp_viewer = client.post("/api/v1/lab/scenarios/2_cpu_high/inject")
        assert resp_viewer.status_code == 403

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LAB_MODE_ENABLED", "false")
    admin = _make_user(role="admin", allowed_entities=["*"])
    with _with_overrides(user=admin) as client:
        resp_prod = client.post("/api/v1/lab/scenarios/2_cpu_high/inject")
        assert resp_prod.status_code == 403
        assert "production" in resp_prod.json()["detail"].lower()


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_and_negative_content_length_with_400():
    async def _raw_asgi_post(content_length_value: bytes) -> tuple[int, dict]:
        captured_status = None
        body_chunks = []

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/webhooks/zabbix",
            "raw_path": b"/api/v1/webhooks/zabbix",
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", b"application/json"),
                (b"content-length", content_length_value),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }

        sent_body = False

        async def receive():
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": b"{}", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            nonlocal captured_status
            if message["type"] == "http.response.start":
                captured_status = message["status"]
            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))

        await app(scope, receive, send)
        import json
        return captured_status, json.loads(b"".join(body_chunks).decode("utf-8"))

    status_alpha, body_alpha = await _raw_asgi_post(b"invalid-int")
    assert status_alpha == 400
    assert "Content-Length" in body_alpha["detail"]

    status_neg, body_neg = await _raw_asgi_post(b"-10")
    assert status_neg == 400
    assert "Content-Length" in body_neg["detail"]


def test_health_live_sets_content_security_policy_header():
    with _with_overrides() as client:
        resp = client.get("/health/live")
        assert resp.status_code == 200
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
