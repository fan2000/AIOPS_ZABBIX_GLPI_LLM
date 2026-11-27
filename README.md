# AI IT Operations Platform (AIOps) — Enterprise Multi-Site & High Availability

> **Plateforme AIOps industrielle, modulaire, multi-sites et sécurisée Zero-Trust connectant Zabbix 7.0 (Server & Proxies), GLPI 10 (Multi-Entités & CMDB), LangGraph (Agents IA, Investigation & HITL Persistant), PostgreSQL 16 + pgvector HNSW/FTS, Contextual Retrieval v2, GraphRAG léger, Eval Harness Continu, Redis Streams HA et Next.js 15.**

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15.5-black.svg)](https://nextjs.org/)
[![GLPI](https://img.shields.io/badge/GLPI-10.0%20Multi--Entit%C3%A9s-008080.svg)](https://glpi-project.org/)
[![Zabbix](https://img.shields.io/badge/Zabbix-7.0%20LTS-red.svg)](https://www.zabbix.com/)
[![Security](https://img.shields.io/badge/OWASP%202025-Zero--Trust%20Hardened-success.svg)](SECURITY.md)
[![ProdReadiness](https://img.shields.io/badge/PROD%20Readiness-100%2F100%20Multi--Site%20HA-emerald.svg)]()
[![Tests](https://img.shields.io/badge/Tests-127%2F127%20Passed%20(100%25)-brightgreen.svg)]()
[![EvalHarness](https://img.shields.io/badge/Eval%20Harness-14%2F14%20Release%20Gate%20PASSED-06b6d4.svg)]()

---

## 🌟 Présentation & Proposition de Valeur

**AI IT Operations** est une plateforme d'exploitation autonome et assistée conçue pour les équipes **NOC, SOC, SRE et Service Desk**, capable de superviser, diagnostiquer, documenter et remédier en condition opérationnelle des **infrastructures critiques complexes et multi-sites** (Datacenters Core/DR, agences régionales Edge, réseaux industriels OT/SCADA et environnements Cloud hybrides).

### Capacités Clés :
- ⚡ **Ingestion & Normalisation Ultra-Rapide (`< 30 ms`)** : Réception des webhooks Zabbix avec authentification **HMAC-SHA256**, filtrage automatique des macros de test non substituées (`{EVENT.NAME}`, `{HOST.NAME}`), qualification multi-sites et calcul d'idempotence `SHA-256`.
- 🌍 **Fédération Multi-Sites & Corrélation Topologique Anti-Tempête** :
  - Qualification automatique du site (`site_code`), de la zone réseau (`CORE`, `DMZ`, `EDGE`, `OT`, `CLOUD`), du proxy Zabbix local (`zabbix_proxy`) et de l'entité GLPI (`entity_id`).
  - **Règle 3 `SITE_TOPOLOGY_CORRELATION`** : Lorsqu'un routeur cœur, firewall, lien WAN ou proxy tombe sur un site distant, les alertes ICMP/Ping aval des serveurs de ce site sont corrélées sous l'incident maître du site (confiance `0.92`) pour éliminer les tempêtes de tickets.
- 🔄 **Haute Disponibilité (HA) & Continuité d'Activité (`RPO = 0`, `RTO < 15s`)** :
  - Pool PostgreSQL asynchrone avec `pool_pre_ping=True` et `pool_recycle=1800` compatible avec les bascules **Patroni / PgBouncer / HAProxy**.
  - **Redis Streams HA** avec protection mémoire `MAXLEN ~ 100000`, disjoncteur (*Circuit Breaker* `< 0.5s`) basculant sur tampon mémoire local sans perte d'alerte (`RPO = 0`), et **Dead-Letter Queue (`zabbix:events:dlq`)** isolant tout message corrompu.
  - Continuité en **mode dégradé déterministe** si le moteur LLM (Ollama) ou GLPI est temporairement injoignable.
- 📋 **Synchronisation GLPI 10 Multi-Entités & CMDB** : Recherche d'équipements, routage automatique vers l'entité GLPI du site concerné, création de tickets ITIL enrichis et publication de diagnostics en suivis privés assainis contre les injections XSS (`CWE-79`).
- 🧠 **Knowledge Center & RAG Hybride Production (P0 / P1 #4 / P2 #9)** :
  - **Recherche Hybride SQL Native & RRF** : Indexation vectorielle **pgvector HNSW** (`ef_search`) combinée au **Full-Text bilingue FR/EN GIN** (`search_tsv_multi` / `title_tsv_multi`) via **Reciprocal Rank Fusion**, isolation stricte multi-entités GLPI (`allowed_entities`) et blocage/audit des tentatives IDOR (`KB_IDOR_BLOCKED`).
  - **Chunking Sémantique v2 & Contextual Retrieval** (`packages/rag/src/chunker.py`) : Conversion structurée `html_to_structured_text` préservant titres, listes et blocs `<pre><code>` atomiques, recouvrement réel de **18%** (`108/600` car.), préfixe contextuel `[Source | OS | Service | Catégorie | Site | Section | Titre]` et métadonnées filtrables JSONB indexées GIN (`jsonb_path_ops`).
  - **Embeddings Multi-Providers & Garde Anti-Corruption DLQ** (`packages/rag/src/embeddings.py`) : Batching asynchrone supportant Ollama (`/api/embed`), TEI et APIs OpenAI-compatibles, disjoncteur, **Dead-Letter Queue PostgreSQL (`knowledge_embedding_dlq`)** et endpoints `/dlq/retry`, `/reindex-fallback`, `/reindex-contextual`.
  - **Qualité RAG Continue, Knowledge Gaps & GraphRAG Léger** (`packages/rag/src/quality.py`, `packages/rag/src/graph_rag.py`) : Calcul déterministe du score **Faithfulness** et de couverture des citations, détection/priorisation automatique des **Knowledge Gaps** avec création en 1 clic de brouillons `KnowledgeProposal`, et **GraphRAG opérationnel** reliant `Actif CMDB ↔ Service ↔ Incidents similaires ↔ Articles KB ↔ Runbooks` (filtrage 2 sauts).
- 🤖 **Orchestration LangGraph, HITL Persistant & Moteur LLM Hybride (P0 / P1 #5)** :
  - Chaîne complète avec boucle d'investigation lecture seule bornée (`investigation_agent_node`, max 2 itérations) et porte d'approbation humaine persistante (`human_approval_gate_node`, `PostgresAsyncCheckpointSaver`, `interrupt_before=["human_approval_gate"]`, endpoints `/api/v1/actions/approvals/*`).
  - Moteur LLM hybride (`packages/agents/src/llm_client.py`) avec timeouts, sorties structurées Pydantic, cache Redis, guardrails **OWASP LLM01** / masquage des secrets (`packages/agents/src/guardrails.py`), persistance des citations RAG (`recommendation_sources`), boucle Feedback → KB et télémétrie FinOps `/api/v1/ai/status`.
- 🧪 **Évaluation Continue Automatisée — Eval Harness (P2 #8)** :
  - **Golden Dataset v1.0.0** (`14` scénarios couvrant diagnostic, RAG `Recall@5`/`MRR`/`Faithfulness`, sûreté HITL et guardrails sécurité), métriques `pass@k` / `pass^k`, **Release Gate** bloquant CI/CD (`python -m packages.evals.src.cli`), persistance PostgreSQL (`ai_eval_runs`) et alerte Prometheus `AIOpsAIEvalRegression`.
- 🔐 **Système Complet IAM, MFA TOTP & Console d'Administration** : Authentification **Sign-In** (`/login`), **Sign-Up Viewer** (`/register`), **MFA TOTP RFC 6238** avec QR code & secrets chiffrés Fernet (`packages/security/src/mfa.py`), **Refresh Token Rotation** révocable (`UserSession`), profil utilisateur (`/profile`), console `/admin/users`, garde de navigation `AppShell`, et client centralisé `apiFetch()` anti-Open-Redirect (`CWE-601`).
- 🛡️ **Remédiation Contrôlée Niveau 3 (Human-in-the-Loop) & Audit Sécurité (`SECURITY.md`)** :
  - Catalogue de runbooks déclaratifs (PowerShell, SSH, Ansible) validés par schéma JSON avec extraction dynamique de service sécurisée (`^[A-Za-z0-9_.-]{1,64}$`).
  - Blocage strict OS/paramètres (`CWE-78`), neutralisation processus timeout (`CWE-775`), RBAC hiérarchique (`admin > operator > viewer`, `CWE-285/613`), isolation anti-IDOR multi-entités avec `AuditLog` (`INCIDENT_IDOR_BLOCKED`, `RUNBOOK_IDOR_BLOCKED`), en-tête `Content-Security-Policy` et journalisation d'audit infalsifiable.
- ⚡ **Optimisations Runtime & Performance** : Hachage mot de passe déporté hors event loop (`asyncio.to_thread`), pooling `httpx.AsyncClient` par boucle événementielle, cache santé LLM TTL 10s, sondes santé & enrichissement GLPI/Zabbix parallélisés (`asyncio.gather`), pipeline Redis `setex` batché et `cosine_similarity` en passe unique.
- 🎨 **Interface NOC Obsidian "Double-Bezel" (Next.js 15)** : Console haute densité ergonomique avec pages `/login`, `/register`, `/profile`, `/admin/users`, `/incidents`, `/knowledge` (recherche filtrée, DLQ, **Qualité RAG, Gaps & GraphRAG**), `/ai-operations` (FinOps LLM & Eval Harness), `/automation` (HITL & runbooks) et `/architecture-flow`.

---

## 🚀 Démarrage Rapide (Développement, Docker PROD & Kubernetes HA)

### Option A : Démarrage Natif sous Windows (Développement / Lab)

```powershell
cd C:\IA_ENV_LAB\AIOPS_ZABBIX_GLPI_LLM

# Lancer la plateforme complète (API Gateway :8005, Worker, Frontend :3005 et conteneurs)
.\start_windows.ps1
# (ou double-cliquer sur start_windows.bat)

# Pour arrêter proprement tous les processus :
.\stop_windows.ps1
```

### Option B : Déploiement Conteneurisé Standard (Docker Compose)

```bash
cp .env.example .env
docker compose up -d --build
```

### Option C : Déploiement en Production Durcie & Haute Disponibilité (`docker-compose.prod.yml`)

Active les conteneurs non-root (`USER aiops`, UID `10001`), `no-new-privileges:true`, Uvicorn multi-workers (`--workers 4`), réplicas d'API et de Workers, quotas CPU/RAM, persistance Redis AOF, réplication WAL PostgreSQL et rotation des logs :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### Option D : Déploiement Cluster Kubernetes Multi-Sites / Multi-AZ

Déploie le `Namespace`, `ConfigMap`, les `Deployment` avec `podAntiAffinity` inter-zones, le `PodDisruptionBudget` (`minAvailable: 2` pour zéro coupure), le `HorizontalPodAutoscaler` (`3 -> 12 pods`) et la `NetworkPolicy` Zero-Trust :

```bash
kubectl apply -f infrastructure/kubernetes/aiops-multi-site-ha.yaml
```

---

## 🌐 Annuaire des Services & Ports (12 Services Actifs)

### 1. Applications & Interfaces Web (Accessibles dans le Navigateur)

| Application Web | Port | URL d'Accès | Rôle & Identifiants |
| :--- | :---: | :--- | :--- |
| **Frontend Web Next.js 15** | `3005` | [http://localhost:3005](http://localhost:3005) | Console NOC Obsidian Double-Bezel |
| **API Gateway FastAPI** | `8005` | [http://localhost:8005](http://localhost:8005) | Swagger OpenAPI : `/docs` & Santé : `/health/live`, `/health/ready` |
| **Audit PROD Readiness** | `8005` | [http://localhost:8005/api/v1/system/production-readiness](http://localhost:8005/api/v1/system/production-readiness) | Score de conformité PROD, HA & Sécurité (`100/100`) |
| **Topologie Multi-Sites** | `8005` | [http://localhost:8005/api/v1/system/multi-site-topology](http://localhost:8005/api/v1/system/multi-site-topology) | État temps réel des 4 sites, proxies Zabbix & entités GLPI |
| **GLPI 10 ITSM & CMDB** | `8088` | [http://localhost:8088](http://localhost:8088) | Identifiants : `glpi` / `glpi` |
| **Zabbix 7.0 Web UI** | `8089` | [http://localhost:8089](http://localhost:8089) | Supervision Zabbix : `Admin` / `zabbix` |
| **Adminer (Web UI SQL)** | `8086` | [http://localhost:8086](http://localhost:8086) | Administration **PostgreSQL** & **MariaDB** |
| **Redis Commander** | `8087` | [http://localhost:8087](http://localhost:8087) | Inspection visuelle des clés et **Redis Streams** |
| **Grafana Dashboards** | `3006` | [http://localhost:3006](http://localhost:3006) | Tableaux de bord centralisés : `admin` / `admin_aiops_pass` |
| **Prometheus Metrics** | `9095` | [http://localhost:9095](http://localhost:9095) | Scraping `/metrics` & règles d'alerte `alerts.yml` |

### 2. Services Réseau TCP (Bases de Données, Caches & Trapper)

| Service | Port TCP | Chaîne de Connexion Client | Identifiants de Connexion |
| :--- | :---: | :--- | :--- |
| **PostgreSQL 16 + pgvector** | `5435` | `postgresql://localhost:5435/aiops_db` | `aiops_user` / `aiops_secure_password` |
| **MariaDB 10.11 (GLPI)** | `3307` | `mysql://localhost:3307/glpi_db` | `glpi_user` / `glpi_secure_password` |
| **Redis Streams** | `6380` | `redis://localhost:6380/0` | Mot de passe : `aiops_redis_password` |
| **Zabbix Server Trapper** | `10051` | `tcp://localhost:10051` | Port d'écoute agents & proxies Zabbix |

---

## 🌍 Architecture Multi-Sites, IA Hybride & Knowledge Center

```text
   [SITE PAR-DC1 (Core/DMZ)]   [SITE LYN-DC2 (PRA/DR)]   [SITE MAR-EDGE-01 (OT)]   [CLD-EU-WEST (K8s)]
       zbx-proxy-par-dc1          zbx-proxy-lyn-dc2        zbx-proxy-mar-edge-01    zbx-proxy-cld-eu-west
               \                          |                         |                        /
                +-------------------------+------------+------------+-----------------------+
                                                       |
                                      Webhook HTTPS signé HMAC-SHA256
                                                       v
                                    FASTAPI API GATEWAY (Stateless / HPA)
                         (Headers OWASP, Rate-Limit, RBAC, Qualification Site/Entité)
                                                       |
                                                       v
                              REDIS STREAMS HA (MAXLEN 100k + Circuit Breaker RPO=0)
                                    +---------> [Dead-Letter Queue :dlq]
                                    |
                                    v
                         INCIDENT WORKER & MOTEUR DE CORRÉLATION TOPOLOGIQUE
                  (Règle 1: Même Hôte | Règle 2: Recovery | Règle 3: Tempête Réseau Site)
                                    |
            +-----------------------+-----------------------+-------------------------------+
            |                                               |                               |
            v                                               v                               v
   GLPI 10 MULTI-ENTITÉS                      ORCHESTRATEUR LANGGRAPH              KNOWLEDGE CENTER & RAG v2
 (Entités #1, #2, #3, #4)             (Incident -> Correlation -> Knowledge       (pgvector HNSW + FTS Bilingue GIN + RRF
 (Tickets & Suivis Privés)             -> Investigation R/O [<=2] -> Diagnosis     + Contextual Chunking 18% + DLQ Emb.
                                       -> Validation -> HITL Checkpoint Gate)     + Faithfulness / Gaps / GraphRAG léger)
                                                            |                               ^
                                                            v                               |
                                            APPROBATION HUMAINE PERSISTANTE          EVAL HARNESS CONTINU
                                            (PostgresAsyncCheckpointSaver)        (14 Golden Cases • Release Gate)
                                                            |
                                                            v
                                         SANDBOX DE REMÉDIATION (CWE-78 / CWE-775)
                                               + Feedback Agent -> Propositions KB
```

---

## 🔌 Référence Rapide des APIs IAM, IA, HITL, Knowledge Center & Eval Harness

| Domaine | Endpoint | Méthode | Rôle RBAC | Fonction |
| :--- | :--- | :---: | :---: | :--- |
| **IAM & Auth** | `/api/v1/auth/login`, `/register`, `/refresh`, `/logout`, `/me`, `/change-password` | `POST`/`GET` | Public / Connecté | Authentification JWT, inscription Viewer, rotation Refresh Token & profil |
| **MFA TOTP** | `/api/v1/auth/mfa/setup`, `/enable`, `/disable`, `/verify-login` | `POST` | Connecté / Défi | Double authentification RFC 6238 (QR code + secrets chiffrés Fernet) |
| **Admin RBAC** | `/api/v1/users`, `/users/{id}/role`, `/entities`, `/status`, `/unlock` | `GET`/`PATCH` | `admin` | Gestion des utilisateurs, entités GLPI autorisées et déverrouillage |
| **Télémétrie IA** | `/api/v1/ai/status` | `GET` | Lecture | Statut LLM, cache Redis, tokens, latence et bascules déterministes |
| **HITL LangGraph** | `/api/v1/actions/approvals` | `GET` | `viewer+` | Liste des actions en attente d'approbation isolées par entité |
| **HITL LangGraph** | `/api/v1/actions/approvals/{id}/decide` | `POST` | `operator`/`admin` | Approuve/rejette et reprend le graphe depuis `PostgresAsyncCheckpointSaver` |
| **Eval Harness** | `/api/v1/evals/dataset` & `/summary` | `GET` | Public / Lecture | Expose le Golden Dataset (`14` cas) et l'historique des campagnes |
| **Eval Harness** | `/api/v1/evals/run` | `POST` | `operator+` | Lance une campagne `pass@k`/`pass^k` et persiste `AIEvalRun` |
| **Knowledge RAG** | `/api/v1/knowledge/search` | `POST` | `viewer+` | Recherche hybride HNSW+FTS RRF avec filtres `os`, `service`, `category`, `site_code` |
| **Knowledge RAG** | `/api/v1/knowledge/documents/{id}` | `GET` | `viewer+` | Détail document & chunks contextualisés (audit anti-IDOR `KB_IDOR_BLOCKED`) |
| **Knowledge Ops** | `/api/v1/knowledge/sync`, `/dlq/retry`, `/reindex-fallback`, `/reindex-contextual` | `POST` | `operator+` | Synchronisation GLPI, reprise DLQ embeddings & réindexation Contextual v2 |
| **Qualité & Gaps** | `/api/v1/knowledge/quality` & `/gaps` | `GET` | `viewer+` | KPIs Faithfulness, Citations, Recall@5, MRR & Knowledge Gaps priorisés |
| **Brouillon KB** | `/api/v1/knowledge/gaps/draft-proposal` | `POST` | `operator+` | Crée en 1 clic un brouillon `KnowledgeProposal` depuis un Knowledge Gap |
| **GraphRAG** | `/api/v1/knowledge/graph` | `GET` | `viewer+` | Graphe relationnel `Asset ↔ Service ↔ Incidents ↔ KB ↔ Runbooks` (`?q=`, `?asset=`) |

---

## 🔒 Sécurité Défensive & Audit Bug Bounty (OWASP Top 10:2025 / CWE / OWASP LLM)

Les contrôles critiques suivants sont appliqués, documentés dans [`SECURITY.md`](SECURITY.md) et couverts par des tests automatisés de non-régression :

| Réf. | CWE / OWASP | Protection Déployée | Fichier |
| :--- | :--- | :--- | :--- |
| **VULN-01** | **CWE-78** (Injection OS) | Rejet regex strict des métacaractères shell, validation service `^[A-Za-z0-9_.-]{1,64}$` & `ValueError -> HTTP 400` sur HITL override | `services/remediation_worker/src/runner.py`, `packages/agents/src/nodes/resolution_node.py`, `apps/api/src/routers/actions.py` |
| **VULN-02** | **CWE-306 / CWE-285** (RBAC) | Authentification JWT Bearer obligatoire, hiérarchie `admin > operator > viewer`, auth sur `/incidents/{id}/analyze` & `/lab/*` (+ blocage prod) | `apps/api/src/routers/actions.py`, `incidents.py`, `lab.py` |
| **VULN-03** | **CWE-798** (Secrets PROD) | Blocage `RuntimeError` au démarrage si secret par défaut ou `< 32` caractères en production | `packages/security/src/jwt.py` |
| **VULN-05** | **CWE-79** (Stored XSS) | Assainissement systématique `html.escape()` des suivis privés envoyés vers GLPI | `services/incident_worker/src/worker.py` |
| **VULN-06** | **CWE-942 / CWE-693** (CORS / CSP) | Liste blanche `ALLOWED_ORIGINS` et injection `Content-Security-Policy` (`default-src 'none'; frame-ancestors 'none'`) | `apps/api/src/main.py` |
| **VULN-10** | **CWE-755** (Audit Integrity) | Vérification d'existence de l'incident en base (`HTTP 404`) avant toute exécution de runbook | `apps/api/src/routers/actions.py` |
| **VULN-11** | **CWE-613** (Révocation) | Vérification en direct `user.is_active` rejetant immédiatement (`HTTP 403`) et Refresh Tokens révocables (`UserSession`) | `apps/api/src/dependencies/auth.py`, `apps/api/src/routers/auth.py` |
| **VULN-12** | **CWE-307** (Brute-Force) | Rate-Limiter `auth_limiter` (`HTTP 429` + `Retry-After`) sur login et échecs HMAC/Bearer webhook Zabbix | `apps/api/src/routers/auth.py`, `webhooks.py` |
| **VULN-13** | **CWE-770 / CWE-20** (Webhook) | Plafond strict `1 Mo` (`HTTP 413`), parsing sûr `Content-Length` (`HTTP 400`), tampons `deque` bornés (`RedisStreamsClient`) | `apps/api/src/routers/webhooks.py`, `packages/connectors/redis_streams.py` |
| **VULN-18** | **CWE-775** (Process Leak) | Terminaison forcée `process.kill()` + `await process.wait()` sur expiration de timeout | `services/remediation_worker/src/runner.py` |
| **SEC-IDOR** | **CWE-639** (Anti-IDOR) | Isolation stricte `allowed_entities` avec journalisation `AuditLog` (`INCIDENT_IDOR_BLOCKED`, `RUNBOOK_IDOR_BLOCKED`, `KB_IDOR_BLOCKED`) | `apps/api/src/routers/incidents.py`, `actions.py`, `knowledge.py` |
| **FE-SEC** | **CWE-601** (Frontend Security) | `sanitizeNextPath()` anti-Open-Redirect (`/login`) et migration complète vers `apiFetch()` authentifié | `apps/frontend/src/app/login/page.tsx`, `lib/api.ts` |
| **AI-SEC-01** | **OWASP LLM01 / LLM06** | Balisage XML (`<untrusted_incident_problem>`), redaction JWT/AWS/URL, blocage élargi des directives d'injection | `packages/agents/src/guardrails.py`, `nodes/diagnosis_node.py` |

---

## ⚙️ Configuration Zabbix 7.0 & Observabilité Prometheus / Grafana

### 1. Paramètres du Média Webhook Zabbix (`AIOps Webhook`)
Dans Zabbix (**Alerts > Media types > AIOps Webhook**), configurez les paramètres suivants :

| Name | Value | Description |
| :--- | :--- | :--- |
| **`URL`** | `http://api-gateway:8000/api/v1/webhooks/zabbix` *(ou `http://host.docker.internal:8005/api/v1/webhooks/zabbix`)* | Endpoint API Gateway |
| **`event_id`** | `{EVENT.ID}` | ID de l'événement |
| **`event_type`** | `{EVENT.VALUE}` | `1` (Problem) / `0` (Recovery) |
| **`host_id`** | `{HOST.ID}` | ID de l'équipement |
| **`host_name`** | `{HOST.NAME}` | Nom d'hôte CMDB (ex: `PAR-APP-01`, `LYN-CORE-RTR-01`) |
| **`trigger_id`** | `{TRIGGER.ID}` | ID du trigger |
| **`severity`** | `{TRIGGER.SEVERITY}` | Sévérité Zabbix |
| **`problem`** | `{EVENT.NAME}` | Description de l'alerte |
| **`metric`** | `{ITEM.KEY}` | Clé de métrique |
| **`value`** | `{ITEM.VALUE}` | Valeur mesurée |
| **`secret`** | `zabbix-webhook-shared-hmac-secret-key-32chars` | Clé secrète HMAC (`.env`) |

> **Note sur le bouton "Test" de Zabbix** : Lors d'un clic manuel sur le bouton *Test* dans Zabbix, Zabbix envoie les chaînes littérales `{EVENT.NAME}` et `{HOST.NAME}` faute d'événement réel actif. Le normalisateur AIOps détecte automatiquement ces macros non substituées et les convertit proprement en événement `[Test Webhook Zabbix] Test de connectivité` sur `SRV-TEST-01`.

### 2. Sources de Données Grafana (`http://localhost:3006`) & Métriques Prometheus (`/metrics`)
Les sources de données sont pré-provisionnées automatiquement dans [`infrastructure/monitoring/grafana/datasources/datasource.yml`](file:///c:/IA_ENV_LAB/AIOPS_ZABBIX_GLPI_LLM/infrastructure/monitoring/grafana/datasources/datasource.yml) :
- **Prometheus** : `http://prometheus:9090` (UID : `prometheus`)
- **Zabbix 7.0 JSON-RPC** : `http://zabbix-web:8080/api_jsonrpc.php` (Plugin `alexanderzobnin-zabbix-app`)
- **PostgreSQL AIOps** : `postgres:5432` (Base `aiops_db`)

Principales métriques IA / RAG / Eval exposées dans `packages/observability/src/metrics.py` :
- `aiops_rag_faithfulness_score`, `aiops_rag_citation_coverage_ratio`, `aiops_rag_knowledge_gaps_total`
- `aiops_rag_dlq_pending`, `aiops_rag_fallback_chunks`, `aiops_rag_embeddings_total`, `aiops_rag_search_latency_seconds`
- `aiops_eval_runs_total`, `aiops_eval_latest_score{dimension}`, `aiops_eval_regression_detected` (alerte `AIOpsAIEvalRegression`)
- `aiops_hitl_approvals_total`, `aiops_investigation_loops_total`, `aiops_llm_tokens_total`, `aiops_llm_fallback_total`

---

## 🧪 Validation, Eval Harness & Suite Complète de Tests (127/127 Tests Passants — 100%)

Exécutez l'ensemble des tests unitaires, IAM/MFA, de sécurité OWASP/CWE, d'intégration, des 10 scénarios ITIL, RAG/GraphRAG, Eval Harness, connectivité système et résilience Multi-Sites HA :

```powershell
$env:PYTHONNOUSERSITE = "1"
uv run pytest tests -v

# Exécuter le Release Gate CI/CD de l'Eval Harness (14 scénarios Golden v1.0.0)
uv run python -m packages.evals.src.cli --mode fast_deterministic --k 1

# Vérification statique TypeScript du Frontend Next.js
cd apps/frontend; npx tsc --noEmit
```

### Répartition des 127 Tests Automatisés (25 fichiers) :
- **Tests d'intégration API & LangGraph (`43 tests`)** :
  - `tests/integration/test_api_endpoints.py` *(9)* : Liveness, Webhook HMAC, Limite 1 Mo (`HTTP 413`), JSON malformé (`HTTP 400`), Catalogue Runbooks, Login JWT & `/me`, Rate-Limiting (`HTTP 429`), Incident inexistant (`HTTP 404`), Rejet RBAC Viewer (`HTTP 403`).
  - `tests/integration/test_iam_auth_mfa_users_api.py` *(4)* : Inscription self-service Viewer & politique mot de passe, Setup/Enable/Challenge/Verify/Disable MFA TOTP, Rotation Refresh Token & changement mot de passe, Administration RBAC `/users/*`.
  - `tests/integration/test_langgraph_workflow.py` *(1)* : Exécution bout-en-bout LangGraph incluant `feedback_agent` et proposition KB.
  - `tests/integration/test_p0_ai_knowledge_loop.py` *(4)* : Isolation RAG cross-entity (`403`), auth stricte PROD (`401`), `/api/v1/ai/status`, boucle Feedback → KB.
  - `tests/integration/test_p0_module2_knowledge_api.py` *(3)* : Détail document + audit IDOR `KB_IDOR_BLOCKED`, DLQ & réindexation RBAC, métriques `/knowledge/stats`.
  - `tests/integration/test_p1_contextual_rag_api.py` *(3)* : Filtres métadonnées RAG (`os`, `service`, `category`, `site_code`), `/reindex-contextual`, champs contextualisés.
  - `tests/integration/test_p1_hitl_approvals_api.py` *(5)* : RBAC approbation HITL (`viewer`/`operator`), reprise approuvée/rejetée du checkpoint LangGraph, isolation multi-entités.
  - `tests/integration/test_p2_evals_api.py` *(4)* : `/api/v1/evals/dataset` (`14` cas), rejet `viewer` (`403`), déclenchement & persistance opérateur, historique runs.
  - `tests/integration/test_p2_rag_quality_api.py` *(3)* : Endpoints `/knowledge/quality`, `/gaps`, `/graph` et création 1-clic `/gaps/draft-proposal` (`403`/`201` + `AuditLog`).
  - `tests/integration/test_security_audit_fixes_api.py` *(7)* : Anti-IDOR `/incidents/*/analyze`, `/incidents/*/feedback` & `/actions/execute`, auth/RBAC & garde prod `/lab/*`, `decide_approval` override `400`, webhook `Content-Length` invalide/négatif `400`, en-tête `Content-Security-Policy`.
- **Scénarios & Système (`25 tests`)** :
  - `tests/scenarios/test_all_10_incident_scenarios.py` *(10)* : Disque plein, CPU saturé, RAM+Swap, Service arrêté, Hôte injoignable, Corrélation multi-alertes, Incident inconnu sans hallucination, Tolérance panne GLPI, Mode dégradé sans LLM, `RECOVERY`.
  - `tests/system/test_full_aiops_connectivity.py` *(9)* : Audit réseau 12 services, PostgreSQL+pgvector, Redis Streams, Webhook Zabbix, API, GLPI, RAG Hybride, Runbooks, routes Frontend.
  - `tests/system/test_production_multisite_ha.py` *(6)* : `/production-readiness` (`100/100`), topologie 4 sites, qualification site/zone, `SITE_TOPOLOGY_CORRELATION`, bascule HA Redis `RPO=0` & DLQ, manifestes Docker/K8s.
- **Tests Unitaires & Sécurité (`59 tests`)** :
  - `tests/unit/test_security_rbac.py` *(7)* : Bcrypt/JWT, Rate-Limiter glissant & anti-fuite (`CWE-770`), RBAC, garde secret PROD (`CWE-798`), révocation compte (`CWE-613`).
  - `tests/unit/test_mfa_totp_security.py` *(5)* : TOTP RFC 6238, chiffrement Fernet secret MFA, codes de récupération, politique mot de passe, rejet des jetons challenge MFA sur `get_current_user`.
  - `tests/unit/test_security_agent_perf_audit.py` *(8)* : Redaction JWT/AWS/URL & marqueurs prompt injection élargis, masquage + cumul tokens `diagnosis_node`, normalisation LLM JSON `validation_node`, extraction service `resolution_node`, suivi `_use_memory_fallback` Checkpointer, deques bornées & `aclose()` Redis, hachage async `to_thread` & `cosine_similarity` passe unique.
  - `tests/unit/test_remediation_runner.py` *(5)* : Schéma runbook, rejet injection OS (`CWE-78`), simulation, `process.kill()` sur timeout (`CWE-775`).
  - `tests/unit/test_zabbix_normalization.py` *(5)* : Mapping sévérité, statut, idempotence SHA-256, assainissement macros Zabbix.
  - `tests/unit/test_rag_p0.py` *(4)*, `tests/unit/test_llm_guardrails_p0.py` *(3)* : RRF, filtrage entités, redaction secrets, anti-prompt injection, bascule déterministe.
  - `tests/unit/test_knowledge_rag_p0_module2.py` *(4)* : RRF bilingue SQL, `source_types`, embeddings multi-providers batchés, DLQ.
  - `tests/unit/test_semantic_chunker_p1.py` *(5)* : `html_to_structured_text`, blocs code/listes atomiques, overlap 18%, préfixes contextuels v2, filtres métadonnées.
  - `tests/unit/test_hitl_langgraph_p1.py` *(5)* : Checkpointer PostgreSQL LangGraph, boucle d'investigation R/O bornée (`<=2`), suspension/reprise HITL.
  - `tests/unit/test_eval_harness_p2.py` *(4)* : Golden Dataset v1.0.0, graders diagnostic/RAG/HITL/sécurité, `EvalHarnessRunner`, Release Gate.
  - `tests/unit/test_rag_quality_gaps_graphrag_p2.py` *(4)* : `normalize_incident_family`, `compute_faithfulness_score`, `detect_knowledge_gaps`, `build_operational_graph` (2 sauts).

---

## 📁 Arborescence du Projet

```text
AIOPS_ZABBIX_GLPI_LLM/
├── apps/
│   ├── api/                        # API Gateway FastAPI (actions, auth, evals, health, incidents, knowledge, lab, users, webhooks)
│   └── frontend/                   # Console Web Next.js 15 (login, register, profile, admin/users, incidents, knowledge, ai-operations, automation, architecture-flow)
├── packages/
│   ├── agents/                     # Graphe LangGraph (graph, state, checkpointer PG, guardrails LLM, llm_client, nodes/)
│   ├── connectors/                 # Clients Zabbix JSON-RPC, GLPI REST, Redis Streams HA (Circuit Breaker & DLQ)
│   ├── contracts/                  # Contrats Pydantic v2 (Events Multi-Sites, Incidents, AI/Citations, Runbooks)
│   ├── domain/                     # Modèles SQLAlchemy 2.0 & pgvector (Incidents, KB/DLQ, HITL Checkpoints, Eval Runs, Users/Sessions)
│   ├── evals/                      # Harness d'évaluation continue IA (dataset, graders, runner, persistence, cli)
│   ├── observability/              # Exportateur de métriques Prometheus temps réel (IA, RAG, HITL, Eval)
│   ├── rag/                        # RAG Production (chunker v2, embeddings multi-provider, retriever RRF, quality/gaps, graph_rag)
│   └── security/                   # HMAC-SHA256, JWT, MFA TOTP Fernet, Rate-Limiter anti-fuite, RBAC
├── services/
│   ├── incident_worker/            # Worker Redis Streams, Corrélation Topologique Multi-Sites & Isolation DLQ
│   ├── knowledge_worker/           # Synchronisation KB GLPI, chunking sémantique v2, DLQ retry & réindexation
│   └── remediation_worker/         # Sandbox d'exécution Niveau 3 durcie (Anti-CWE-78 & Timeout Kill CWE-775)
├── database/                       # Pool SQLAlchemy HA (pool_pre_ping=True), Migrations & Seeds
├── infrastructure/
│   ├── docker/                     # Dockerfiles durcis non-root (USER aiops) avec sondes HEALTHCHECK
│   ├── kubernetes/                 # Manifestes K8s Production Multi-Sites HA (HPA, PDB, AntiAffinity, NetworkPolicy)
│   └── monitoring/                 # Règles Prometheus alerts.yml (dont AIOpsAIEvalRegression) & Provisioning Grafana
├── tests/                          # 127 tests automatisés (Unitaires, IAM/MFA, Sécurité, Intégration, Scénarios, Système & HA)
├── SECURITY.md                     # Politique de sécurité, journal d'audit OWASP 2025/LLM & remédiations vérifiées
├── docker-compose.yml              # Stack conteneurisée complète (12 services)
├── docker-compose.prod.yml         # Surcharge Production Haute Disponibilité & Durcissement Sécurité
├── pyproject.toml                  # Configuration Python 3.12+, dépendances et pytest
├── start_windows.ps1 / .bat        # Lanceurs natifs Windows
└── stop_windows.ps1 / .bat         # Scripts d'arrêt propre
```

---

## 📄 Licence & Conformité
Plateforme conçue selon les standards **DevSecOps**, **OWASP Top 10:2025**, **OWASP LLM Top 10**, **Clean Architecture** et **ITIL v4**. Tous les accès, diagnostics IA, citations RAG, campagnes d'évaluation et exécutions de runbooks sont journalisés de manière immuable.
