"""Tests d'intégration API P1 #5 : Endpoints HITL /approvals, /checkpoint, /decide et RBAC."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user
from apps.api.src.main import app
from database.connection import get_db_session
from packages.contracts.src.runbook import ExecutionStatus, RunbookExecutionResult


def _mock_result(scalar=None, all_rows=None):
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalars.return_value.all.return_value = all_rows or []
    res.all.return_value = all_rows or []
    return res


def _build_entities(required_role: str = "operator", entity_id: str = "0"):
    inc_id = uuid4()
    app_id = uuid4()
    now = datetime.now(timezone.utc)

    approval = SimpleNamespace(
        id=app_id,
        incident_id=inc_id,
        runbook_identifier="rb-disk-cleanup-logs",
        parameters={"days": 15},
        status="pending_approval",
        thread_id=f"incident-{inc_id}-abcd",
        checkpoint_id="ckpt-001",
        risk_level="MEDIUM",
        action_summary="Purge logs > 15j",
        execution_id=None,
        requested_at=now,
        decided_at=None,
        decided_by_user=None,
        rejection_reason=None,
    )
    incident = SimpleNamespace(
        id=inc_id,
        incident_number="INC-20261120-HITL01",
        title="Disk usage above 95% on /var/log",
        severity="HIGH",
        status="WAITING_APPROVAL",
        primary_asset_name="SRV-WEB-01",
        entity_id=entity_id,
        glpi_ticket_id=None,
        recovery_at=None,
    )
    runbook = SimpleNamespace(
        identifier="rb-disk-cleanup-logs",
        name="Purge préventive logs",
        description="Purge fichiers anciens",
        runner_type="bash_ssh",
        target_os="linux",
        timeout_seconds=60,
        required_role=required_role,
        parameter_schema={},
        template_command="echo ok",
        is_enabled=True,
    )
    return approval, incident, runbook


def _fake_session_with_side_effect(side_effects):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute.side_effect = side_effects
    return session


def test_hitl_decide_viewer_forbidden():
    """Un utilisateur viewer ne peut jamais approuver ou rejeter une remédiation HITL (HTTP 403)."""
    viewer = AuthenticatedUserContext(
        id=uuid4(),
        username="viewer_noc",
        role="viewer",
        permissions=["incidents:read"],
        allowed_entities=["*"],
    )
    app.dependency_overrides[get_current_user] = lambda: viewer
    app.dependency_overrides[get_db_session] = lambda: _fake_session_with_side_effect([])

    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/actions/approvals/{uuid4()}/decide",
            json={"approved": True, "comment": "Tentative viewer"},
        )
        assert resp.status_code == 403
        assert "Opérateur ou administrateur requis" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_hitl_decide_operator_forbidden_when_runbook_requires_admin():
    """Un opérateur est bloqué si le runbook ciblé exige required_role='admin'."""
    approval, incident, runbook = _build_entities(required_role="admin")
    operator = AuthenticatedUserContext(
        id=uuid4(),
        username="op_l1",
        role="operator",
        permissions=["incidents:read", "actions:execute"],
        allowed_entities=["*"],
    )
    session = _fake_session_with_side_effect(
        [
            _mock_result(scalar=approval),
            _mock_result(scalar=incident),
            _mock_result(scalar=runbook),
        ]
    )
    app.dependency_overrides[get_current_user] = lambda: operator
    app.dependency_overrides[get_db_session] = lambda: session

    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/actions/approvals/{approval.id}/decide",
            json={"approved": True, "comment": "Escalade test"},
        )
        assert resp.status_code == 403
        assert "requis: admin" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_hitl_decide_approve_executes_and_resumes_langgraph(monkeypatch):
    """L'approbation par un opérateur exécute la sandbox, met à jour l'incident et reprend LangGraph."""
    approval, incident, runbook = _build_entities(required_role="operator")
    operator = AuthenticatedUserContext(
        id=uuid4(),
        username="op_senior",
        role="operator",
        permissions=["incidents:read", "actions:execute"],
        allowed_entities=["*"],
    )
    session = _fake_session_with_side_effect(
        [
            _mock_result(scalar=approval),
            _mock_result(scalar=incident),
            _mock_result(scalar=runbook),
        ]
    )

    exec_id = uuid4()
    mock_runner = AsyncMock(
        return_value=RunbookExecutionResult(
            execution_id=exec_id,
            runbook_id="rb-disk-cleanup-logs",
            incident_id=incident.id,
            status=ExecutionStatus.SUCCESS,
            exit_code=0,
            stdout="Cleanup completed cleanly",
            stderr="",
            duration_seconds=0.45,
            post_check_verified=True,
            verification_details="OK",
        )
    )
    mock_resume = AsyncMock(
        return_value={
            "thread_id": approval.thread_id,
            "paused": False,
            "next_nodes": [],
            "checkpoint_id": "ckpt-002",
            "state": {
                "hitl_status": "resumed_approved",
                "kb_proposal": {
                    "title": "Procédure purge /var/log",
                    "category": "AIOps - Retours d'expérience",
                    "content": "<p>Cleanup completed cleanly</p>",
                },
            },
        }
    )
    mock_upsert_kb = AsyncMock(return_value=SimpleNamespace(id=uuid4()))

    monkeypatch.setattr("apps.api.src.routers.actions.remediation_runner.execute", mock_runner)
    monkeypatch.setattr("apps.api.src.routers.actions.resume_hitl_incident_analysis", mock_resume)
    monkeypatch.setattr("apps.api.src.routers.actions.upsert_kb_proposal_from_state", mock_upsert_kb)

    app.dependency_overrides[get_current_user] = lambda: operator
    app.dependency_overrides[get_db_session] = lambda: session

    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/actions/approvals/{approval.id}/decide",
            json={"approved": True, "comment": "Purge approuvée"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["approval"]["status"] == "approved"
        assert body["approval"]["decided_by_user"] == "op_senior"
        assert body["execution"]["status"] == "success"
        assert body["hitl_resumed"]["paused"] is False
        assert body["hitl_resumed"]["hitl_status"] == "resumed_approved"
        assert body["hitl_resumed"]["kb_proposal_generated"] is True
        assert incident.status == "RESOLVED"
        mock_runner.assert_awaited_once()
        mock_resume.assert_awaited_once()
        assert session.add.call_count >= 2  # ActionExecution + AuditLog
    finally:
        app.dependency_overrides.clear()


def test_hitl_decide_reject_resumes_without_execution(monkeypatch):
    """Le rejet ne déclenche pas remediation_runner mais reprend le graphe jusqu'au feedback et écrit AuditLog."""
    approval, incident, runbook = _build_entities(required_role="operator")
    operator = AuthenticatedUserContext(
        id=uuid4(),
        username="op_night",
        role="operator",
        permissions=["incidents:read", "actions:execute"],
        allowed_entities=["*"],
    )
    session = _fake_session_with_side_effect(
        [
            _mock_result(scalar=approval),
            _mock_result(scalar=incident),
            _mock_result(scalar=runbook),
        ]
    )

    mock_runner = AsyncMock()
    mock_resume = AsyncMock(
        return_value={
            "thread_id": approval.thread_id,
            "paused": False,
            "next_nodes": [],
            "checkpoint_id": "ckpt-003",
            "state": {"hitl_status": "resumed_rejected"},
        }
    )
    mock_upsert_kb = AsyncMock(return_value=None)

    monkeypatch.setattr("apps.api.src.routers.actions.remediation_runner.execute", mock_runner)
    monkeypatch.setattr("apps.api.src.routers.actions.resume_hitl_incident_analysis", mock_resume)
    monkeypatch.setattr("apps.api.src.routers.actions.upsert_kb_proposal_from_state", mock_upsert_kb)

    app.dependency_overrides[get_current_user] = lambda: operator
    app.dependency_overrides[get_db_session] = lambda: session

    try:
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/actions/approvals/{approval.id}/decide",
            json={"approved": False, "comment": "Faux positif maintenance"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["approval"]["status"] == "rejected"
        assert body["approval"]["rejection_reason"] == "Faux positif maintenance"
        assert body["execution"] is None
        assert body["hitl_resumed"]["hitl_status"] == "resumed_rejected"
        assert incident.status == "IN_PROGRESS"
        mock_runner.assert_not_awaited()
        mock_resume.assert_awaited_once()
        assert session.add.call_count >= 1  # AuditLog
    finally:
        app.dependency_overrides.clear()


def test_hitl_list_and_checkpoint_enforce_multi_entity_isolation(monkeypatch):
    """Un utilisateur restreint à l'entité 10 ne voit pas les approbations d'une entité 20 (HTTP 403 sur /checkpoint)."""
    app_allowed, inc_allowed, _ = _build_entities(entity_id="10")
    app_foreign, inc_foreign, _ = _build_entities(entity_id="20")

    scoped_user = AuthenticatedUserContext(
        id=uuid4(),
        username="tech_site_10",
        role="operator",
        permissions=["incidents:read"],
        allowed_entities=["10"],
    )

    session_list = _fake_session_with_side_effect(
        [_mock_result(all_rows=[(app_allowed, inc_allowed), (app_foreign, inc_foreign)])]
    )
    app.dependency_overrides[get_current_user] = lambda: scoped_user
    app.dependency_overrides[get_db_session] = lambda: session_list

    try:
        client = TestClient(app)
        resp_list = client.get("/api/v1/actions/approvals")
        assert resp_list.status_code == 200
        items = resp_list.json()
        assert len(items) == 1
        assert items[0]["id"] == str(app_allowed.id)

        session_ckpt = _fake_session_with_side_effect(
            [
                _mock_result(scalar=app_foreign),
                _mock_result(scalar=inc_foreign),
            ]
        )
        app.dependency_overrides[get_db_session] = lambda: session_ckpt
        resp_ckpt = client.get(f"/api/v1/actions/approvals/{app_foreign.id}/checkpoint")
        assert resp_ckpt.status_code == 403
        assert "entité GLPI" in resp_ckpt.json()["detail"]
    finally:
        app.dependency_overrides.clear()
