# AI IT Operations Platform (AIOps)

> **Plateforme AIOps intelligente, modulaire et sécurisée connectant Zabbix, GLPI 10, LangGraph, pgvector et Next.js 15.**

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15.5-black.svg)](https://nextjs.org/)
[![GLPI](https://img.shields.io/badge/GLPI-10.0-008080.svg)](https://glpi-project.org/)
[![Zabbix](https://img.shields.io/badge/Zabbix-7.0-red.svg)](https://www.zabbix.com/)
[![Tests](https://img.shields.io/badge/Tests-33%2F33%20Passed-brightgreen.svg)]()

---

## 🌟 Présentation

**AI IT Operations** est une plateforme industrielle conçue pour les équipes **NOC, SOC et Service Desk**, qui automatise la détection, la corrélation, le diagnostic et la remédiation assistée des incidents d'infrastructure.

### Capacités clés :
- ⚡ **Ingestion & Normalisation ultra-rapide** : Réception des webhooks Zabbix en `< 30 ms` avec signature HMAC SHA-256 et hash d'idempotence.
- 🔗 **Corrélation Déterministe** : Agrégation intelligente multi-alertes (même hôte, dépendances réseau, signatures connues) pour éviter les tempêtes de tickets.
- 📋 **Synchronisation GLPI 10 & CMDB** : Recherche automatique des équipements dans la CMDB, création de tickets dédupliqués et publication de diagnostics en suivis privés.
- 🧠 **RAG Hybride & pgvector** : Recherche hybride (cosinus dense 768d + mots-clés) dans la base documentaire GLPI avec seuils de confiance qualitatifs anti-hallucination.
- 🤖 **Orchestration Multi-Agents LangGraph** : 7 agents spécialisés coopérants (Incident, Corrélation, Knowledge, Diagnostic, Résolution, Validation des commandes, Feedback d'apprentissage).
- 🛡️ **Remédiation Contrôlée Niveau 3 (Human-in-the-Loop)** : Catalogue de runbooks déclaratifs (Ansible, PowerShell, SSH). Aucune commande arbitraire générée par LLM ; validation obligatoire par un technicien.
- 🔍 **Vérification de Résolution** : Contrôle automatique post-remédiation via les métriques Zabbix et gestion des alertes `RECOVERY`.

---

## 🚀 Démarrage Rapide

### Option A : Démarrage Natif sous Windows (Recommandé)

Lance la plateforme directement sous Windows avec Python (`uv`), Node.js (`pnpm`/`npm`) et conteneurs de données :

```powershell
# Cloner ou naviguer dans le dossier du projet
cd C:\IA_ENV_LAB\AIOPS_ZABBIX_GLPI_LLM

# Lancer la plateforme complète en un clic
.\start_windows.ps1
# (ou double-cliquer sur start_windows.bat)
```

Pour arrêter proprement tous les processus sans laisser de ports orphelins :
```powershell
.\stop_windows.ps1
# (ou double-cliquer sur stop_windows.bat)
```

### Option B : Déploiement Conteneurisé avec Docker Compose

```bash
# Copier les variables d'environnement
cp .env.example .env

# Construire et démarrer l'ensemble des conteneurs
docker compose up -d --build
```

---

## 🌐 Annuaire des Services & Ports

Tous les ports ont été configurés pour éviter tout conflit avec des services existants sur la machine hôte :

### 1. Applications & Interfaces Web (Accessibles dans le Navigateur)

| Application Web | Port | URL d'Accès | Rôle & Identifiants |
| :--- | :---: | :--- | :--- |
| **Frontend Web Next.js** | `3005` | [http://localhost:3005](http://localhost:3005) | Console des opérations AIOps (Accès libre) |
| **API Gateway FastAPI** | `8005` | [http://localhost:8005](http://localhost:8005) | Documentation Swagger OpenAPI : `/docs` |
| **GLPI 10 ITSM & CMDB** | `8088` | [http://localhost:8088](http://localhost:8088) | Identifiants : `glpi` / `glpi` |
| **Zabbix 7.0 Web UI** | `8089` | [http://localhost:8089](http://localhost:8089) | Supervision Zabbix : `Admin` / `zabbix` |
| **Adminer (Web UI Bases de Données)** | `8086` | [http://localhost:8086](http://localhost:8086) | Interface visuelle pour **PostgreSQL** & **MariaDB** |
| **Redis Commander (Web UI Cache)** | `8087` | [http://localhost:8087](http://localhost:8087) | Exploration visuelle des clés et **Redis Streams** |
| **Grafana Dashboards** | `3006` | [http://localhost:3006](http://localhost:3006) | Supervision : `admin` / `admin_aiops_pass` |
| **Prometheus Metrics** | `9095` | [http://localhost:9095](http://localhost:9095) | Métriques brutes & cibles de scraping |

### 2. Services Réseau TCP (Bases de Données & Caches)
> *Note technique : Ces moteurs écoutent sur des protocoles binaires TCP dédiés (non HTTP). Pour les explorer dans votre navigateur web, utilisez les interfaces **Adminer** (`:8086`) et **Redis Commander** (`:8087`) ci-dessus.*

| Service | Port TCP | Chaîne de Connexion Client | Identifiants de Connexion |
| :--- | :---: | :--- | :--- |
| **PostgreSQL 16 + pgvector** | `5435` | `postgresql://localhost:5435/aiops_db` | `aiops_user` / `aiops_secure_password` |
| **MariaDB 10.11 (GLPI)** | `3307` | `mysql://localhost:3307/glpi_db` | `glpi_user` / `glpi_secure_password` |
| **Redis Streams** | `6380` | `redis://localhost:6380/0` | Mot de passe : `aiops_redis_password` |
| **Zabbix Server Trapper** | `10051` | `tcp://localhost:10051` | Port d'écoute agents & proxies Zabbix |

---

## 🏗️ Architecture du Système

```text
                 INFRASTRUCTURE IT
                         |
       Windows / Linux / Network / Apps
                         |
                         v
                    ZABBIX SERVER
                         |
                   Webhook HTTPS
                         |
                         v
                 FASTAPI API GATEWAY (Port 8005)
                         |
              Validation HMAC / Auth / RBAC
                         |
                         v
                   REDIS STREAMS (Port 6380)
                         |
                         v
                INCIDENT ORCHESTRATOR (LangGraph)
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
     ZABBIX API       GLPI API     CORRÉLATION DÉTERMINISTE
          |              |              |
          +--------------+--------------+
                         |
                         v
                   RAG PIPELINE (pgvector)
                         |
                    LLM ENGINE (Ollama / Qwen / Mistral)
                         |
                  DIAGNOSIS ENGINE (Hypothèses sourcées)
                         |
                 RESOLUTION ENGINE (Catalogue Runbooks)
                         |
                         v
                    GLPI TICKET (Suivis privés ITIL)
                         |
                         v
               TECHNICIEN D'EXPLOITATION
              (Approuver / Modifier / Refuser)
                         |
                         v
                 ACTION CONTRÔLÉE (Sandbox Ansible / PowerShell)
                         |
                 VÉRIFICATION MÉTRIQUES ZABBIX
                         |
                 FEEDBACK BASE DE CONNAISSANCES
```

---

## ⚙️ Configuration & Intégration de GLPI 10

Le conteneur **GLPI 10** (`glpi/glpi:latest`) s'initialise automatiquement avec sa base MariaDB. Pour relier le GLPI officiel à l'AIOps :

1. Connectez-vous sur **[http://localhost:8088](http://localhost:8088)** avec les identifiants `glpi` / `glpi`.
2. Allez dans **Configuration** > **Générale** > onglet **API** :
   - Cochez **Activer la connexion avec identifiants (login)** : `Oui`
   - Cochez **Activer la connexion avec jeton d'utilisateur (user_token)** : `Oui`
3. Dans **Clients API**, cliquez sur **`+`** :
   - Nom : `AIOps Platform`
   - Actif : `Oui`
   - Cliquez sur **Ajouter**, puis **Régénérer** le **Jeton d'application (App Token)**.
4. Allez dans **Administration** > **Utilisateurs** > utilisateur **`glpi`** > onglet **Paramètres** :
   - Générez et copiez le **Jeton d'API (User Token)**.
5. Reportez les jetons dans votre fichier `.env` :
   ```env
   LAB_MODE_ENABLED=false
   GLPI_API_URL=http://localhost:8088/apirest.php
   GLPI_APP_TOKEN=votre_jeton_application
   GLPI_USER_TOKEN=votre_jeton_utilisateur
   ```

*(Note : Si vous laissez `LAB_MODE_ENABLED=true`, la plateforme utilise le simulateur GLPI REST v9/v10 interne sans prérequis).*

---

## 🛡️ Configuration & Intégration de Zabbix 7.0

Le serveur **Zabbix 7.0 LTS** est accessible sur **[http://localhost:8089](http://localhost:8089)** (`Admin` / `zabbix`).

### 1. Configuration du Webhook d'Alerte vers l'API Gateway AIOps
Dans Zabbix, allez dans **Alerts** > **Media types** > cliquez sur **Create media type** (ou éditez un type Webhook existant) :

- **Name** : `AIOps Webhook`
- **Type** : `Webhook`
- **Parameters** : Cliquez sur **`Add`** pour renseigner les paramètres ci-dessous :

| Name | Value | Description |
| :--- | :--- | :--- |
| **`URL`** | `http://api-gateway:8000/api/v1/webhooks/zabbix` *(ou `http://host.docker.internal:8005/api/v1/webhooks/zabbix` en natif Windows)* | Endpoint API |
| **`event_id`** | `{EVENT.ID}` | ID de l'événement |
| **`event_type`** | `{EVENT.VALUE}` | `1` pour Problem, `0` pour Recovery |
| **`host_id`** | `{HOST.ID}` | ID de l'équipement |
| **`host_name`** | `{HOST.NAME}` | Nom d'hôte CMDB |
| **`trigger_id`** | `{TRIGGER.ID}` | ID du trigger |
| **`severity`** | `{TRIGGER.SEVERITY}` | Sévérité Zabbix |
| **`problem`** | `{EVENT.NAME}` | Description de l'alerte |
| **`metric`** | `{ITEM.KEY}` | Clé de métrique |
| **`value`** | `{ITEM.VALUE}` | Valeur mesurée |
| **`secret`** | `zabbix-webhook-shared-hmac-secret-key-32chars` | Clé secrète HMAC (.env) |

### 2. Script JavaScript Zabbix (Champ `Script`)
Collez ce code dans le champ **Script** (les en-têtes HTTP `Content-Type` et `X-Zabbix-Signature` y sont gérés automatiquement) :

```javascript
try {
    Zabbix.log(4, '[AIOps Webhook] Réception: ' + value);
    var params = JSON.parse(value);

    if (!params.URL) {
        throw 'Le paramètre URL est requis.';
    }

    var req = new HttpRequest();
    if (params.HTTPProxy) {
        req.setProxy(params.HTTPProxy);
    }

    // En-têtes HTTP (Signature HMAC et Content-Type)
    req.addHeader('Content-Type: application/json');
    if (params.secret) {
        req.addHeader('X-Zabbix-Signature: ' + params.secret);
    }

    // Formatage du payload normalisé AIOps
    var payload = {
        event_id: String(params.event_id || '0'),
        event_type: params.event_type === '0' ? 'RECOVERY' : 'PROBLEM',
        host_id: String(params.host_id || '0'),
        host_name: params.host_name || 'UNKNOWN-HOST',
        trigger_id: String(params.trigger_id || '0'),
        severity: params.severity || 'HIGH',
        problem: params.problem || params.Subject || 'Incident détecté',
        metric: params.metric || null,
        value: params.value ? parseFloat(params.value) : null,
        timestamp: new Date().toISOString()
    };

    var response = req.post(params.URL, JSON.stringify(payload));
    Zabbix.log(4, '[AIOps Webhook] Réponse HTTP ' + req.getStatus() + ': ' + response);

    if (req.getStatus() < 200 || req.getStatus() >= 300) {
        throw 'Échec HTTP ' + req.getStatus() + ': ' + response;
    }

    return response;
} catch (error) {
    Zabbix.log(3, '[AIOps Webhook] Erreur: ' + error);
    throw 'Erreur Webhook AIOps: ' + error;
}
```

### 3. Test Rapide du Webhook en 1 Clic
Dans la liste **Media types**, cliquez sur le lien bleu **Test** en face de `AIOps Webhook`, puis sur **Test**. L'API Gateway AIOps répond instantanément avec le code `202 Accepted` et transmet l'alerte à Redis Streams.

### 4. Configuration de l'API Token JSON-RPC (Interrogation inverse par l'AIOps)
1. Allez dans **Users** > **API tokens** > **Create API token**.
2. Nommez le token `AIOps Platform Token` et sauvegardez.
3. Renseignez-le dans votre fichier `.env` :
   ```env
   ZABBIX_API_URL=http://localhost:8089/api_jsonrpc.php
   ZABBIX_API_TOKEN=votre_token_genere
   ```

---

## 🧪 Validation & Suite de Tests (24/24 Tests Passants)

Exécutez la suite complète de tests unitaires, d'intégration et de scénarios :

```powershell
$env:PYTHONNOUSERSITE = "1"
uv run --extra dev pytest -v
```

### Couverture des 10 Scénarios ITIL Validés :
1. ✅ **Saturation Disque** (`/var/log > 95%`) : Détection volumétrique, sélection du runbook de purge des logs archivés.
2. ✅ **CPU Saturé en continu** : Corrélation chronologique > 15 min, formulation de l'hypothèse de boucle applicative.
3. ✅ **RAM + Swap thrashing** : Agrégation multi-triggers dans un incident majeur unique.
4. ✅ **Service arrêté** : Sélection du runbook de redémarrage avec approbation humaine obligatoire.
5. ✅ **Hôte inaccessible** : Détection sévérité `DISASTER` sur sonde ICMP Ping.
6. ✅ **Rafale d'alertes dépendantes** : Déduplication glissante de 15 min sans flood de tickets.
7. ✅ **Incident sans article KB** : Qualifié en `insufficient_evidence` avec zéro hallucination.
8. ✅ **GLPI temporairement hors-ligne** : Tolérance aux pannes réseau et mise en file d'attente sécurisée.
9. ✅ **LLM indisponible** : Bascule transparente en mode dégradé heuristique basé sur règles.
10. ✅ **Alerte RECOVERY Zabbix** : Mise à jour du ticket sans clôture prématurée avant validation humaine.

---

## 🧰 Intégration du Multi-Agent Harness (ECC)

Le référentiel [affaan-m/ecc](https://github.com/affaan-m/ecc) (*Everything Claude Code / Universal Agent Harness*) est intégré et disponible :

- **Profil** : `full`
- **Dépôt local** : [`.agents/`](file:///c:/IA_ENV_LAB/AIOPS_ZABBIX_GLPI_LLM/.agents/) (281 skills, 122 rules, 68 agents, 94 workflows).
- **Profil utilisateur global** : `C:\Users\fanmed\.agents\` et `~/.claude/` (actif automatiquement sur tous vos projets).

Pour réinstaller ou synchroniser sur un nouveau projet :
```powershell
npx --yes ecc-universal --target antigravity --profile full --no-hooks
```

---

## 📁 Arborescence du Projet

```text
AIOPS_ZABBIX_GLPI_LLM/
├── apps/
│   ├── api/                     # API Gateway FastAPI (Webhooks, Incidents, RAG, Lab)
│   └── frontend/                # Application Web Next.js 15 (Console NOC, Flow, KB)
├── packages/
│   ├── agents/                  # Graphe LangGraph & les 7 agents spécialisés
│   ├── connectors/              # Connecteurs Zabbix JSON-RPC, GLPI REST, Redis
│   ├── contracts/               # Schémas Pydantic v2 (Events, Incident, GLPI, Runbooks)
│   ├── domain/                  # Modèles SQLAlchemy 2.0 & pgvector (20 tables)
│   ├── rag/                     # Moteur RAG Hybride, Chunking & Embeddings
│   └── security/                # HMAC SHA-256, JWT, Hachage PBKDF2/bcrypt, RBAC
├── services/
│   ├── incident_worker/         # Worker asynchrone Redis Streams & Corrélation
│   ├── knowledge_worker/        # Indexation vectorielle de la base GLPI
│   └── remediation_worker/      # Sandbox d'exécution sécurisée des runbooks
├── database/                    # Scripts de migration et d'amorçage (Seeds)
├── infrastructure/
│   ├── docker/                  # Dockerfiles durcis pour API, Worker et Frontend
│   └── monitoring/              # Configs Prometheus & Grafana Dashboards
├── tests/                       # 24 tests unitaires, d'intégration et 10 scénarios
├── docker-compose.yml           # Déploiement multi-services conteneurisé
├── pyproject.toml               # Configuration Python, dépendances et build Hatchling
├── start_windows.ps1 / .bat     # Lanceurs natifs Windows
└── stop_windows.ps1 / .bat      # Scripts d'arrêt propre
```

---

## 📄 Licence & Conformité
Plateforme conçue selon les règles **DevSecOps**, **Clean Architecture** et **ITIL v4**. Tous les accès, logs d'audit et exécutions d'actions sont tracés en base de données.
