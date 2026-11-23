"""Tests d'intégration IAM : Sign-Up, Sign-In + MFA TOTP, Refresh Rotation, Profil & Admin Users/Roles."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import httpx
import pytest
from apps.api.src.dependencies.auth import AuthenticatedUserContext, get_current_user
from apps.api.src.main import app
from database.connection import get_db_session
from packages.domain.models.database import Role, User, UserSession
from packages.security.src.jwt import create_access_token, get_password_hash
from packages.security.src.mfa import decrypt_mfa_secret, generate_totp_code
from packages.security.src.rate_limiter import auth_limiter


def _mock_result(scalar=None, all_rows=None, rowcount=1):
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalar.return_value = scalar
    res.scalars.return_value.all.return_value = all_rows or []
    res.all.return_value = all_rows or []
    res.rowcount = rowcount
    return res


def _session_with_side_effects(effects):
    s = AsyncMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    s.commit = AsyncMock()
    s.execute.side_effect = effects
    return s


@pytest.mark.asyncio
async def test_register_viewer_success_weak_password_and_conflict():
    """POST /api/v1/auth/register crée un viewer actif, rejette mot de passe faible (400) et doublon (409)."""
    auth_limiter._history.clear()
    viewer_role = Role(
        id=uuid4(),
        name="viewer",
        description="Lecture seule",
        permissions=["incident:read", "knowledge:read"],
    )

    session_ok = _session_with_side_effects(
        [
            _mock_result(scalar=None),  # Aucun doublon
            _mock_result(scalar=viewer_role),  # Role viewer
        ]
    )

    async def override_ok():
        yield session_ok

    app.dependency_overrides[get_db_session] = override_ok
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Mot de passe faible rejeté 400
            bad_resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": "new_ops",
                    "email": "new_ops@aiops.local",
                    "password": "weak",
                },
            )
            assert bad_resp.status_code == 400

            # 2. Inscription valide -> 201 + rôle viewer + access & refresh tokens
            ok_resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": "nadia_noc",
                    "email": "nadia@aiops.local",
                    "password": "StrongPass#2026",
                    "full_name": "Nadia Benali",
                },
            )
            assert ok_resp.status_code == 201
            body = ok_resp.json()
            assert body["access_token"]
            assert body["refresh_token"].startswith("aiops_rt_")
            assert body["user"]["role"] == "viewer"
            assert body["user"]["allowed_entities"] == ["0"]
            assert body["user"]["full_name"] == "Nadia Benali"
            assert session_ok.add.call_count >= 3  # User + UserSession + AuditLog
    finally:
        app.dependency_overrides.clear()

    # 3. Conflit username/email existant -> 409
    existing_user = User(
        id=uuid4(),
        username="nadia_noc",
        email="nadia@aiops.local",
        hashed_password=get_password_hash("StrongPass#2026"),
        role_id=viewer_role.id,
        allowed_entities=["0"],
        is_active=True,
    )
    session_dup = _session_with_side_effects([_mock_result(scalar=existing_user)])

    async def override_dup():
        yield session_dup

    app.dependency_overrides[get_db_session] = override_dup
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            dup_resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": "nadia_noc",
                    "email": "nadia@aiops.local",
                    "password": "StrongPass#2026",
                },
            )
            assert dup_resp.status_code == 409
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_mfa_setup_enable_login_challenge_verify_and_disable():
    """Cycle complet MFA : setup -> enable -> login challenge -> verify TOTP & code secours -> disable."""
    auth_limiter._history.clear()
    op_role = Role(id=uuid4(), name="operator", description="Ops", permissions=["incident:read", "runbook:execute"])
    user = User(
        id=uuid4(),
        username="ops_mfa",
        email="ops_mfa@aiops.local",
        hashed_password=get_password_hash("OperatorPass#2026"),
        role_id=op_role.id,
        allowed_entities=["0", "1"],
        is_active=True,
        mfa_enabled=False,
        mfa_recovery_codes=[],
        created_at=datetime.now(timezone.utc),
    )

    op_ctx = AuthenticatedUserContext(
        id=user.id,
        username=user.username,
        role="operator",
        permissions=op_role.permissions,
        allowed_entities=["0", "1"],
    )

    # Phase 1 : Setup + Enable + Login sans code -> challenge -> Verify TOTP -> Verify Backup Code -> Disable
    session = _session_with_side_effects(
        [
            _mock_result(scalar=user),  # mfa/setup -> _load_real_user
            _mock_result(scalar=user),  # mfa/enable -> _load_real_user
            _mock_result(scalar=user),  # login -> user lookup
            _mock_result(scalar=op_role),  # login -> role lookup
            _mock_result(scalar=user),  # mfa/verify (TOTP) -> user lookup
            _mock_result(scalar=op_role),  # mfa/verify (TOTP) -> role lookup
            _mock_result(scalar=user),  # mfa/verify (recovery) -> user lookup
            _mock_result(scalar=op_role),  # mfa/verify (recovery) -> role lookup
            _mock_result(scalar=user),  # mfa/disable -> _load_real_user
        ]
    )

    app.dependency_overrides[get_current_user] = lambda: op_ctx

    async def override_db():
        yield session

    app.dependency_overrides[get_db_session] = override_db

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Setup MFA
            r_setup = await client.post("/api/v1/auth/mfa/setup")
            assert r_setup.status_code == 200
            setup_data = r_setup.json()
            secret = setup_data["secret"]
            assert setup_data["otpauth_uri"].startswith("otpauth://totp/")
            assert user.mfa_enabled is False

            # 2. Enable MFA avec code TOTP calculé
            totp_now = generate_totp_code(decrypt_mfa_secret(user.mfa_secret))
            r_enable = await client.post("/api/v1/auth/mfa/enable", json={"code": totp_now})
            assert r_enable.status_code == 200
            recovery_codes = r_enable.json()["recovery_codes"]
            assert len(recovery_codes) == 8
            assert user.mfa_enabled is True

            # 3. Login par email -> retourne challenge MFA sans access_token
            r_login = await client.post(
                "/api/v1/auth/login",
                json={"username": "ops_mfa@aiops.local", "password": "OperatorPass#2026"},
            )
            assert r_login.status_code == 200
            login_body = r_login.json()
            assert login_body["mfa_required"] is True
            assert login_body["access_token"] == ""
            challenge_token = login_body["mfa_challenge_token"]
            assert challenge_token

            # 4. Vérification via TOTP 6 chiffres -> JWT émis
            r_ver1 = await client.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_challenge_token": challenge_token, "code": generate_totp_code(secret)},
            )
            assert r_ver1.status_code == 200
            assert r_ver1.json()["access_token"]
            assert r_ver1.json()["user"]["mfa_enabled"] is True

            # 5. Vérification via code de secours -> consommé (7 restants)
            r_ver2 = await client.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_challenge_token": challenge_token, "code": recovery_codes[0]},
            )
            assert r_ver2.status_code == 200
            assert len(user.mfa_recovery_codes) == 7

            # 6. Désactivation MFA
            r_dis = await client.post(
                "/api/v1/auth/mfa/disable",
                json={"password": "OperatorPass#2026", "code": recovery_codes[1]},
            )
            assert r_dis.status_code == 200
            assert user.mfa_enabled is False
            assert user.mfa_secret is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_refresh_token_rotation_profile_change_password_and_logout():
    """Vérifie rotation Refresh Token, mise à jour profil, change-password et logout."""
    op_role = Role(id=uuid4(), name="operator", description="Ops", permissions=["incident:read"])
    user = User(
        id=uuid4(),
        username="ops_rot",
        email="ops_rot@aiops.local",
        full_name="Ancien Nom",
        hashed_password=get_password_hash("OldPassword#2026"),
        role_id=op_role.id,
        allowed_entities=["0"],
        is_active=True,
        mfa_enabled=False,
    )
    old_sess = UserSession(
        id=uuid4(),
        user_id=user.id,
        refresh_token_hash="hash_placeholder",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        revoked_at=None,
    )

    op_ctx = AuthenticatedUserContext(id=user.id, username=user.username, role="operator", permissions=["incident:read"])
    session = _session_with_side_effects(
        [
            _mock_result(scalar=old_sess),  # /refresh -> UserSession lookup
            _mock_result(scalar=user),  # /refresh -> User lookup
            _mock_result(scalar=op_role),  # /refresh -> Role lookup
            _mock_result(scalar=user),  # /profile -> _load_real_user
            _mock_result(scalar=None),  # /profile -> dup email check
            _mock_result(scalar=op_role),  # /profile -> role lookup
            _mock_result(scalar=user),  # /change-password -> _load_real_user
            _mock_result(),  # /change-password -> update(UserSession)
            _mock_result(scalar=old_sess),  # /logout -> session lookup
        ]
    )

    app.dependency_overrides[get_current_user] = lambda: op_ctx

    async def override_db():
        yield session

    app.dependency_overrides[get_db_session] = override_db

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r_ref = await client.post("/api/v1/auth/refresh", json={"refresh_token": "aiops_rt_dummy_token_value"})
            assert r_ref.status_code == 200
            assert r_ref.json()["access_token"]
            assert r_ref.json()["refresh_token"].startswith("aiops_rt_")
            assert old_sess.revoked_at is not None

            r_prof = await client.patch(
                "/api/v1/auth/profile",
                json={"full_name": "Karim Mansour", "email": "karim@aiops.local"},
            )
            assert r_prof.status_code == 200
            assert r_prof.json()["full_name"] == "Karim Mansour"
            assert r_prof.json()["email"] == "karim@aiops.local"

            r_pwd = await client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "OldPassword#2026", "new_password": "NewStrongPass#2027"},
            )
            assert r_pwd.status_code == 200
            assert r_pwd.json()["sessions_revoked"] is True

            r_out = await client.post("/api/v1/auth/logout", json={"refresh_token": "aiops_rt_dummy_token_value"})
            assert r_out.status_code == 200
            assert r_out.json()["status"] == "logged_out"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_users_admin_rbac_and_management_guards():
    """Seul le rôle admin accède à /api/v1/users, crée/promut des comptes et est protégé contre l'auto-blocage."""
    admin_id = uuid4()
    target_id = uuid4()
    admin_role = Role(id=uuid4(), name="admin", description="Admin", permissions=["all"])
    op_role = Role(id=uuid4(), name="operator", description="Ops", permissions=["incident:read", "runbook:execute"])
    viewer_role = Role(id=uuid4(), name="viewer", description="Viewer", permissions=["incident:read"])

    admin_user = User(
        id=admin_id,
        username="root_admin",
        email="root@aiops.local",
        hashed_password="h",
        role_id=admin_role.id,
        allowed_entities=["*"],
        is_active=True,
    )
    target_user = User(
        id=target_id,
        username="j_martin",
        email="j.martin@aiops.local",
        hashed_password="h",
        role_id=viewer_role.id,
        allowed_entities=["0"],
        is_active=True,
        mfa_enabled=True,
        mfa_secret="enc:dummy",
    )

    # 1. Operator rejeté HTTP 403
    op_ctx = AuthenticatedUserContext(id=uuid4(), username="ops1", role="operator", permissions=["incident:read"])
    app.dependency_overrides[get_current_user] = lambda: op_ctx
    app.dependency_overrides[get_db_session] = lambda: _session_with_side_effects([])
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/api/v1/users")).status_code == 403
            assert (await client.get("/api/v1/users/roles")).status_code == 403
    finally:
        app.dependency_overrides.clear()

    # 2. Admin opérations CRUD + garde anti-auto-verrouillage
    admin_ctx = AuthenticatedUserContext(id=admin_id, username="root_admin", role="admin", permissions=["all"])
    admin_session = _session_with_side_effects(
        [
            _mock_result(all_rows=[admin_role, op_role, viewer_role]),  # GET /users -> roles
            _mock_result(all_rows=[admin_user, target_user]),  # GET /users -> users
            _mock_result(scalar=None),  # POST /users -> dup check
            _mock_result(scalar=op_role),  # POST /users -> role lookup
            _mock_result(scalar=target_user),  # PATCH /{target_id} -> user lookup
            _mock_result(scalar=viewer_role),  # PATCH /{target_id} -> current role lookup
            _mock_result(scalar=op_role),  # PATCH /{target_id} -> new role lookup
            _mock_result(scalar=target_user),  # POST /{target_id}/reset-mfa -> user lookup
            _mock_result(scalar=admin_user),  # PATCH /{admin_id} self-lock guard -> user lookup
        ]
    )

    app.dependency_overrides[get_current_user] = lambda: admin_ctx

    async def override_admin_db():
        yield admin_session

    app.dependency_overrides[get_db_session] = override_admin_db

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r_list = await client.get("/api/v1/users")
            assert r_list.status_code == 200
            assert len(r_list.json()) == 2

            r_create = await client.post(
                "/api/v1/users",
                json={
                    "username": "sre_mar",
                    "email": "sre@aiops.local",
                    "password": "SreStrongPass#2026",
                    "role": "operator",
                    "allowed_entities": ["0", "3"],
                },
            )
            assert r_create.status_code == 201
            assert r_create.json()["role"] == "operator"
            assert r_create.json()["allowed_entities"] == ["0", "3"]

            r_patch = await client.patch(
                f"/api/v1/users/{target_id}",
                json={"role": "operator", "allowed_entities": ["0", "2"]},
            )
            assert r_patch.status_code == 200
            assert r_patch.json()["role"] == "operator"

            r_reset_mfa = await client.post(f"/api/v1/users/{target_id}/reset-mfa")
            assert r_reset_mfa.status_code == 200
            assert target_user.mfa_enabled is False

            # Garde anti-auto-lockout
            r_self = await client.patch(f"/api/v1/users/{admin_id}", json={"is_active": False})
            assert r_self.status_code == 400
    finally:
        app.dependency_overrides.clear()
