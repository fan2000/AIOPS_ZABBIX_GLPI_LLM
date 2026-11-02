# ==============================================================================
# AI IT OPERATIONS - SCRIPT D'ARRÊT PROPRE WINDOWS (PowerShell)
# ==============================================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "Arrêt des services AI IT Operations sous Windows..." -ForegroundColor Yellow

function Stop-StoredProcess($PidFile, $Name) {
    if (Test-Path $PidFile) {
        $pId = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($pId) {
            try {
                Stop-Process -Id ([int]$pId) -Force -ErrorAction SilentlyContinue
                Write-Host "   -> Processus $Name (PID: $pId) arrêté." -ForegroundColor DarkGray
            } catch {}
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

Stop-StoredProcess "$ScriptDir\.api.pid" "API Gateway (FastAPI)"
Stop-StoredProcess "$ScriptDir\.worker.pid" "Incident Worker"
Stop-StoredProcess "$ScriptDir\.front.pid" "Frontend Next.js"

# Nettoyage des ports 8005 et 3005 si processus orphelins résiduels
@(8005, 3005) | ForEach-Object {
    $port = $_
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($connections) {
        $connections | ForEach-Object {
            try {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
                Write-Host "   -> Processus orphelin sur port $port arrêté." -ForegroundColor DarkGray
            } catch {}
        }
    }
}

Write-Host "Tous les services AI IT Operations Windows ont été arrêtés avec succès." -ForegroundColor Green
