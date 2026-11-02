"""Script d'initialisation des données de base (Rôles, Utilisateurs, Runbooks)."""

import asyncio
import os
import uuid
from passlib.context import CryptContext
from sqlalchemy import select
from database.connection import async_session_maker, init_database
from packages.domain.models.database import Role, Runbook, User

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")

INITIAL_ROLES = [
    {
        "name": "admin",
        "description": "Administrateur système avec privilèges totaux",
        "permissions": ["all", "runbook:execute", "runbook:manage", "admin:all"],
    },
    {
        "name": "operator",
        "description": "Technicien d'exploitation autorisé à valider et exécuter les runbooks",
        "permissions": ["incident:read", "incident:update", "runbook:execute"],
    },
    {
        "name": "viewer",
        "description": "Consultation en lecture seule des incidents et tableaux de bord",
        "permissions": ["incident:read", "dashboard:read"],
    },
]

INITIAL_RUNBOOKS = [
    {
        "identifier": "rb-collect-top-processes",
        "name": "Collecte des processus les plus consommateurs",
        "description": "Exécute une inspection en lecture seule des 10 processus consommant le plus de CPU/RAM",
        "runner_type": "powershell",
        "target_os": "windows",
        "template_command": "Get-Process | Sort-Object -Property CPU -Descending | Select-Object -First 10 -Property Id, ProcessName, CPU, WorkingSet64",
        "parameter_schema": {"type": "object", "properties": {}},
        "timeout_seconds": 30,
        "required_role": "viewer",
        "is_enabled": True,
    },
    {
        "identifier": "rb-win-service-restart",
        "name": "Redémarrage de service Windows supervisé",
        "description": "Redémarre un service Windows figurant sur la liste blanche autorisée",
        "runner_type": "powershell",
        "target_os": "windows",
        "template_command": "Restart-Service -Name {service_name} -Force -ErrorAction Stop",
        "parameter_schema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "enum": ["Spooler", "wuauserv", "W32Time", "nginx", "apache2"],
                }
            },
            "required": ["service_name"],
        },
        "timeout_seconds": 60,
        "required_role": "operator",
        "is_enabled": True,
    },
    {
        "identifier": "rb-linux-service-restart",
        "name": "Redémarrage de service Linux systemd",
        "description": "Redémarre un service Linux systemd figurant sur la liste blanche autorisée",
        "runner_type": "bash_ssh",
        "target_os": "linux",
        "template_command": "sudo systemctl restart {service_name}",
        "parameter_schema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "enum": ["nginx", "apache2", "zabbix-agent", "postfix", "docker"],
                }
            },
            "required": ["service_name"],
        },
        "timeout_seconds": 60,
        "required_role": "operator",
        "is_enabled": True,
    },
    {
        "identifier": "rb-disk-cleanup-logs",
        "name": "Purge préventive des logs archivés",
        "description": "Supprime les journaux applicatifs archivés (.gz, .log.old) de plus de 15 jours",
        "runner_type": "bash_ssh",
        "target_os": "linux",
        "template_command": "find /var/log -type f -name '*.gz' -mtime +15 -delete",
        "parameter_schema": {"type": "object", "properties": {}},
        "timeout_seconds": 120,
        "required_role": "operator",
        "is_enabled": True,
    },
]


async def seed_database() -> None:
    """Insère les données de démarrage si elles sont absentes."""
    await init_database()
    async with async_session_maker() as session:
        # 1. Rôles
        role_map = {}
        for role_data in INITIAL_ROLES:
            stmt = select(Role).where(Role.name == role_data["name"])
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                new_role = Role(
                    id=uuid.uuid4(),
                    name=role_data["name"],
                    description=role_data["description"],
                    permissions=role_data["permissions"],
                )
                session.add(new_role)
                await session.flush()
                role_map[role_data["name"]] = new_role
            else:
                role_map[role_data["name"]] = existing

        # 2. Utilisateur Admin par défaut
        admin_stmt = select(User).where(User.username == "admin")
        admin_user = (await session.execute(admin_stmt)).scalar_one_or_none()
        if not admin_user:
            new_admin = User(
                id=uuid.uuid4(),
                username="admin",
                email="admin@aiops.local",
                hashed_password=pwd_context.hash("admin_aiops_pass"),
                role_id=role_map["admin"].id,
                is_active=True,
            )
            session.add(new_admin)

        # 3. Runbooks
        for rb_data in INITIAL_RUNBOOKS:
            rb_stmt = select(Runbook).where(Runbook.identifier == rb_data["identifier"])
            existing_rb = (await session.execute(rb_stmt)).scalar_one_or_none()
            if not existing_rb:
                session.add(Runbook(id=uuid.uuid4(), **rb_data))

        await session.commit()
        print("✅ Données initiales (rôles, admin, runbooks) insérées avec succès.")


if __name__ == "__main__":
    asyncio.run(seed_database())
