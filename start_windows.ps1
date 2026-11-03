# ==============================================================================
# AI IT OPERATIONS - SCRIPT DE DÉMARRAGE NATIF WINDOWS (PowerShell)
# ==============================================================================
# Ce script lance l'ensemble des composants AIOps directement sous Windows :
# 1. Vérification des prérequis (Python, uv, Node.js, Docker)
# 2. Démarrage des conteneurs de base (PostgreSQL + pgvector sur 5435, Redis sur 6380)
# 3. Initialisation et semences de la base de données
# 4. Démarrage de l'API Gateway FastAPI (Port 8005)
# 5. Démarrage du Worker d'Incidents LangGraph
# 6. Démarrage du Frontend Next.js (Port 3005)
# ==============================================================================

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   AI IT OPERATIONS - Démarrage Plateforme (Windows)      " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Vérification de l'environnement .env
if (-not (Test-Path "$ScriptDir\.env")) {
    Write-Host "[!] Fichier .env manquant. Copie depuis .env.example..." -ForegroundColor Yellow
    Copy-Item "$ScriptDir\.env.example" "$ScriptDir\.env"
}

# 2. Vérification des dépendances Python
Write-Host "[1/6] Vérification des dépendances Python..." -ForegroundColor Green
$env:PYTHONNOUSERSITE = "1"
try {
    uv --version | Out-Null
    Write-Host "   -> Gestionnaire 'uv' détecté." -ForegroundColor DarkGray
} catch {
    Write-Host "[!] 'uv' n'est pas détecté. Veuillez installer uv ou Python." -ForegroundColor Red
    exit 1
}

# 3. Démarrage des services d'infrastructure (Postgres, Redis, GLPI, Zabbix, UIs Web)
Write-Host "[2/6] Démarrage des conteneurs de base, Zabbix 7.0 et GLPI 10..." -ForegroundColor Green
try {
    docker compose up -d postgres redis glpi-db glpi zabbix-server zabbix-web zabbix-agent adminer redis-commander
    Write-Host "   -> PostgreSQL (5435), Redis (6380), GLPI (8088), Zabbix (8089), Adminer (8086), Redis Commander (8087) actifs." -ForegroundColor DarkGray
} catch {
    Write-Host "   [!] Docker Compose n'a pas pu démarrer tous les conteneurs. Utilisation du mode fallback mémoire/lab." -ForegroundColor Yellow
}

# 4. Attente de disponibilité et initialisation de la base
Write-Host "[3/6] Initialisation et amorçage de la base de données..." -ForegroundColor Green
Start-Sleep -Seconds 2
try {
    uv run python -m database.seeds.seed_data
    Write-Host "   -> Schéma et données initiales (rôles, runbooks) amorcés." -ForegroundColor DarkGray
} catch {
    Write-Host "   [!] Initialisation de la base différée : le service sera initialisé au premier appel API." -ForegroundColor Yellow
}

# 5. Démarrage de l'API Gateway FastAPI
Write-Host "[4/6] Démarrage de l'API Gateway FastAPI sur http://localhost:8005..." -ForegroundColor Green
$ApiProcess = Start-Process -FilePath "uv" -ArgumentList "run uvicorn apps.api.src.main:app --host 0.0.0.0 --port 8005" -PassThru -WindowStyle Minimized
Set-Content -Path "$ScriptDir\.api.pid" -Value $ApiProcess.Id
Write-Host "   -> API Gateway lancée (PID: $($ApiProcess.Id))." -ForegroundColor DarkGray

# 6. Démarrage du Worker d'Incidents LangGraph
Write-Host "[5/6] Démarrage de l'Incident Worker LangGraph..." -ForegroundColor Green
$WorkerProcess = Start-Process -FilePath "uv" -ArgumentList "run python -c `"import asyncio; from services.incident_worker.src.worker import incident_worker; asyncio.run(incident_worker.start())`"" -PassThru -WindowStyle Minimized
Set-Content -Path "$ScriptDir\.worker.pid" -Value $WorkerProcess.Id
Write-Host "   -> Incident Worker lancé (PID: $($WorkerProcess.Id))." -ForegroundColor DarkGray

# 7. Démarrage du Frontend Next.js
Write-Host "[6/6] Préparation et lancement du Frontend Next.js sur http://localhost:3005..." -ForegroundColor Green
Set-Location "$ScriptDir\apps\frontend"
$PkgManager = if (Get-Command pnpm -ErrorAction SilentlyContinue) { "pnpm.cmd" } else { "npm.cmd" }
if (-not (Test-Path "$ScriptDir\apps\frontend\node_modules")) {
    Write-Host "   -> Installation des modules ($PkgManager)..." -ForegroundColor DarkGray
    Start-Process -FilePath $PkgManager -ArgumentList "install" -Wait -NoNewWindow
}
$FrontProcess = Start-Process -FilePath $PkgManager -ArgumentList "run dev" -PassThru -WindowStyle Minimized
Set-Content -Path "$ScriptDir\.front.pid" -Value $FrontProcess.Id
Set-Location $ScriptDir
Write-Host "   -> Frontend Next.js lancé avec $PkgManager (PID: $($FrontProcess.Id))." -ForegroundColor DarkGray

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   PLATEFORME AI IT OPERATIONS EN COURS D'EXÉCUTION !     " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "   👉 Interface Web Frontend     : http://localhost:3005" -ForegroundColor Cyan
Write-Host "   👉 GLPI 10 ITSM & CMDB        : http://localhost:8088 (login: glpi / glpi)" -ForegroundColor Cyan
Write-Host "   👉 Zabbix 7.0 Supervision     : http://localhost:8089 (login: Admin / zabbix)" -ForegroundColor Cyan
Write-Host "   👉 Adminer (Web Postgres/DB)  : http://localhost:8086" -ForegroundColor Cyan
Write-Host "   👉 Redis Commander (Web Redis): http://localhost:8087" -ForegroundColor Cyan
Write-Host "   👉 Swagger UI / OpenAPI Docs  : http://localhost:8005/docs" -ForegroundColor Cyan
Write-Host "   👉 Health & Readiness Probe   : http://localhost:8005/health/ready" -ForegroundColor Cyan
Write-Host "   👉 Zabbix Webhook Endpoint    : http://localhost:8005/api/v1/webhooks/zabbix" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pour arrêter tous les processus Windows : exécutez .\stop_windows.ps1" -ForegroundColor Yellow
Write-Host ""
