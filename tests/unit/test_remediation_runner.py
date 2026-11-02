"""Tests unitaires pour le moteur de remédiation contrôlée."""

from uuid import uuid4
import pytest
from packages.contracts.src.runbook import (
    ExecutionStatus,
    RunbookDefinition,
    RunbookExecutionRequest,
    RunbookRunnerType,
    TargetOS,
)
from services.remediation_worker.src.runner import RemediationRunner


def test_parameter_validation_success():
    runner = RemediationRunner(simulation_mode=True)
    rb = RunbookDefinition(
        id="rb-win-service-restart",
        name="Redémarrage service Windows",
        description="Restart service",
        runner_type=RunbookRunnerType.POWERSHELL,
        target_os=TargetOS.WINDOWS,
        template_command="Restart-Service -Name {service_name}",
        parameter_schema={
            "type": "object",
            "properties": {"service_name": {"type": "string", "enum": ["Spooler", "nginx"]}},
            "required": ["service_name"],
        },
    )
    # Paramètre autorisé
    runner.validate_parameters(rb, {"service_name": "Spooler"})


def test_parameter_validation_rejection_forbidden_value():
    runner = RemediationRunner(simulation_mode=True)
    rb = RunbookDefinition(
        id="rb-win-service-restart",
        name="Redémarrage service Windows",
        description="Restart service",
        runner_type=RunbookRunnerType.POWERSHELL,
        target_os=TargetOS.WINDOWS,
        template_command="Restart-Service -Name {service_name}",
        parameter_schema={
            "type": "object",
            "properties": {"service_name": {"type": "string", "enum": ["Spooler", "nginx"]}},
            "required": ["service_name"],
        },
    )
    # Tentative d'injection ou de service non autorisé
    with pytest.raises(ValueError, match="n'est pas dans la liste blanche"):
        runner.validate_parameters(rb, {"service_name": "ArbitraryService; rm -rf /"})


@pytest.mark.asyncio
async def test_simulated_execution():
    runner = RemediationRunner(simulation_mode=True)
    rb = RunbookDefinition(
        id="rb-collect-top-processes",
        name="Top processes",
        description="Inspect top cpu",
        runner_type=RunbookRunnerType.POWERSHELL,
        target_os=TargetOS.WINDOWS,
        template_command="Get-Process",
    )
    req = RunbookExecutionRequest(
        runbook_id="rb-collect-top-processes",
        incident_id=uuid4(),
        parameters={},
        approved_by_user_id="operator-1",
    )
    result = await runner.execute(rb, req)
    assert result.status == ExecutionStatus.SUCCESS
    assert result.exit_code == 0
    assert "[Simulation]" in result.stdout
