# Security Policy & Audit Report — AIOps Zabbix-GLPI-LLM

## 1. Security Audit Log

| Audit Date | Scope | Frameworks | Status |
| :--- | :--- | :--- | :--- |
| **2026-11-23** | Full-Stack Codebase (`apps/api`, `apps/frontend`, `packages/*`, `services/*`) | OWASP Top 10:2025, OWASP LLM Top 10, CWE/SANS, 12-Layer Agent Stack | **Remediated** |

---

## 2. Executive Summary

Un audit complet couvrant la sécurité applicative, les vulnérabilités API/Frontend (anti-IDOR, RBAC, injection, redirections ouvertes, en-têtes HTTP), la sécurité des agents LLM (fuite de secrets dans les prompts, prompt injection, exécution bornée d'outils), la résilience des connecteurs/checkpointers et l'optimisation runtime a été réalisé le **2026-11-23**.

Toutes les vulnérabilités critiques et avertissements identifiés ont été corrigés directement dans le code source et couverts par des tests unitaires et d'intégration dédiés.

---

## 3. Audit Findings & Remediations

### Critical / High Findings (Fixed)

| ID | Category / CWE | Component | Issue & Remediation |
| :--- | :--- | :--- | :--- |
| **SEC-01** | **A01:2025 Broken Access Control / IDOR** (`CWE-639`) | `apps/api/src/routers/incidents.py`, `apps/api/src/routers/actions.py` | **Fix**: Application du contrôle d'isolation multi-entités GLPI (`allowed_entities`) sur `GET /api/v1/incidents`, `GET /api/v1/incidents/{id}`, `POST /api/v1/incidents/{id}/analyze`, `POST /api/v1/incidents/{id}/feedback` et `POST /api/v1/actions/execute`. Enregistrement systématique d'un `AuditLog` (`INCIDENT_IDOR_BLOCKED`, `RUNBOOK_IDOR_BLOCKED`) lors de toute tentative cross-tenant. |
| **SEC-02** | **A01:2025 Missing Auth & Prod Lab Exposure** (`CWE-306`) | `apps/api/src/routers/incidents.py`, `apps/api/src/routers/lab.py` | **Fix**: Authentification JWT + RBAC (`operator` / `admin`) + rate-limiter (`default_limiter`) imposés sur `POST /api/v1/incidents/{id}/analyze` et `POST /api/v1/lab/scenarios/{scenario_id}/inject`. Ajout de `_assert_lab_allowed()` bloquant l'ensemble des endpoints `/api/v1/lab/*` en `HTTP 403` lorsque `ENVIRONMENT=production` (sauf `LAB_MODE_ENABLED=true`). |
| **SEC-03** | **A05:2025 Open Redirect** (`CWE-601`) | `apps/frontend/src/app/login/page.tsx` | **Fix**: Ajout de `sanitizeNextPath()` rejetant les chemins relatifs de schéma (`//evil.com`), backslashes (`/\evil.com`), schémas explicites (`://`) et caractères de contrôle (`\r`, `\n`, `\0`) avant toute redirection post-login ou post-MFA. |
| **SEC-04** | **A01 / A07 Unauthenticated Client Requests** | `apps/frontend/src/app/page.tsx`, `incidents/page.tsx`, `architecture-flow/page.tsx` | **Fix**: Remplacement des appels `fetch("http://localhost:8005/...")` directs par `apiFetch(...)` (`apps/frontend/src/lib/api.ts`), injectant automatiquement le jeton `Bearer`, gérant le refresh transparent sur `401`, et utilisant `NEXT_PUBLIC_API_URL`. |
| **SEC-05** | **LLM01 Prompt Injection & LLM06 Secret Leakage** (`CWE-200`, `CWE-74`) | `packages/agents/src/guardrails.py`, `packages/agents/src/nodes/diagnosis_node.py` | **Fix**: Extension de `redact_sensitive_data()` (masquage des JWT, clés AWS `AKIA...`, mots de passe dans les URLs `scheme://user:pass@host`) appliquée à `host_name` et `problem` avant envoi au LLM. Encapsulation de `problem` dans `<untrusted_incident_problem>` via `wrap_untrusted_xml()`. Extension de `sanitize_untrusted_text()` contre les marqueurs `forget instructions`, `override system`, `new instructions:`, `jailbreak`, `<|eot_id|>`, `[INST]`. |
| **SEC-06** | **A03 Parameter / Command Injection Guard** (`CWE-78`, `CWE-20`) | `packages/agents/src/nodes/resolution_node.py`, `apps/api/src/routers/actions.py` | **Fix**: Extraction dynamique sécurisée du service cible (`_extract_target_service`) validée par expression régulière stricte `^[A-Za-z0-9_.-]{1,64}$`. Gestion propre des `ValueError` levées par `remediation_runner.execute` lors d'un `parameters_override` invalide sur `POST /api/v1/actions/approvals/{approval_id}/decide` (`HTTP 400` au lieu de `500`). |

### Warning / Hardening Findings (Fixed)

| ID | Category / CWE | Component | Issue & Remediation |
| :--- | :--- | :--- | :--- |
| **SEC-07** | **A05:2025 Missing CSP Header** (`CWE-693`) | `apps/api/src/main.py` | **Fix**: Injection de l'en-tête HTTP `Content-Security-Policy` dans `production_security_and_tracing_middleware` (`default-src 'none'; frame-ancestors 'none'` pour l'API JSON, politique dédiée pour `/docs`, `/redoc`, `/openapi.json`). |
| **SEC-08** | **A04 / A09 Webhook Input & Auth Brute-Force** (`CWE-20`, `CWE-307`) | `apps/api/src/routers/webhooks.py` | **Fix**: Validation sûre de l'en-tête `Content-Length` non numérique ou négatif (`HTTP 400` au lieu de `500`). Ajout d'un rate-limiter IP dédié (`auth_limiter`, clé `webhook_auth_fail:{ip}`, `HTTP 429`) sur échec HMAC/Bearer. |
| **SEC-09** | **Agent Reliability & Bounded State** | `packages/agents/src/{checkpointer,diagnosis_node,validation_node}.py`, `packages/connectors/redis_streams.py` | **Fix**: Suivi exact de `_use_memory_fallback` dans `PostgresAsyncCheckpointSaver`, normalisation défensive des sorties JSON LLM malformées (`diagnosis_node`, `validation_node`), cumul exact des jetons/coûts entre itérations d'investigation, fermeture propre du client Redis (`await client.aclose()`) en cas d'échec `ping()`, bornage mémoire via `deque(maxlen=10000 / 2000)` dans `RedisStreamsClient`. |
| **SEC-10** | **Runtime & Event-Loop Performance** | `jwt.py`, `auth.py`, `users.py`, `llm_client.py`, `embeddings.py`, `retriever.py`, `glpi/client.py`, `zabbix/client.py`, `context_enrichment.py`, `health.py` | **Fix**: Déportation du hachage/vérification de mots de passe dans un thread worker (`asyncio.to_thread`), pooling `httpx.AsyncClient` par boucle événementielle, mise en cache TTL 10s du probe LLM, parallélisation `asyncio.gather` des sondes santé et de l'enrichissement GLPI+Zabbix, pipeline Redis pour embeddings et `cosine_similarity` en passe unique. |

### Passed Baseline Security Controls

- **IAM & Authentification Multi-Facteurs** : Hachage robuste des mots de passe, rotation de Refresh Tokens révocables (`UserSession`), MFA TOTP RFC 6238 avec provisioning QR, verrouillage de compte sur tentatives échouées.
- **Anti-CSRF & CORS** : `CORS` restreint aux origines autorisées configurables, validation des jetons JWT signés HMAC-SHA256 (`HS256`) avec secret fail-closed en production.
- **Ingestion Webhook Zabbix** : Signature HMAC-SHA256 ou Bearer Token requis hors mode lab, limite de taille payload (`MAX_WEBHOOK_BODY_BYTES`).
- **Remédiation & Exécution HITL** : Liste blanche stricte des runbooks approuvés en base (`Runbook.is_enabled`), pas d'exécution shell libre sans validation de paramètres et contrôle RBAC + approbation humaine LangGraph persistante.
- **RAG Sécurisé** : Filtrage strict SQL multi-entités `entity_id`, redaction PII/secrets avant indexation et génération, séparation données non fiables par balises XML.

---

## 4. Verification Summary (2026-11-23)

- **Backend Test Suite** (`uv run pytest tests -v`) : **127/127 passed (100%)** (unitaires, sécurité OWASP/LLM, IAM/MFA, intégration API, scénarios & HA multi-sites).
- **Eval Harness Release Gate** (`uv run python -m packages.evals.src.cli --mode fast_deterministic --k 1`) : **14/14 PASSED**, `overall=1.00`, `pass@k=1.00`, `pass^k=1.00`, `sec=1.00`, `hitl=1.00`, `RELEASE GATE: PASSED`.
- **Frontend TypeScript Check** (`npx tsc --noEmit`) : exit `0`.
- **Live Probes** : `GET http://localhost:8005/health/live` -> `HTTP 200` avec `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `POST /api/v1/incidents/{id}/analyze` et `/api/v1/lab/scenarios/2_cpu_high/inject` non authentifiés -> `HTTP 401`, `GET http://localhost:3005/` -> `HTTP 200`.

---

## 5. Reporting a Vulnerability

Pour signaler une vulnérabilité de sécurité sur ce dépôt :

1. **Ne créez pas d'issue publique GitHub** contenant des détails exploitables ou des preuves de concept actives.
2. Documentez la vulnérabilité en privé (composant concerné, vecteur d'attaque, impact estimé et correctif recommandé) et transmettez-la à l'équipe sécurité / maintainers du projet.
3. Assurez-vous qu'aucun secret réel (`.env`, clés JWT, jetons Zabbix/GLPI/OpenAI) n'est exposé dans les logs, captures d'écran ou commits Git.
