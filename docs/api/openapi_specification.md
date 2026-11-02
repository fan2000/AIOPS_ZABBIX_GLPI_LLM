# Spécification OpenAPI / Contrats REST : AI IT Operations

La documentation interactive Swagger UI est accessible à l'adresse : `http://localhost:8005/docs`.

---

## 1. Endpoints Webhooks

### `POST /api/v1/webhooks/zabbix`
- **Description** : Réception HTTPS des alertes Zabbix.
- **En-têtes** :
  - `X-Zabbix-Signature` (HMAC-SHA256) ou `Authorization: Bearer <SECRET>`
- **Corps (JSON)** :
```json
{
  "event_id": "45821",
  "event_type": "PROBLEM",
  "host_id": "10452",
  "host_name": "SRV-APP-01",
  "trigger_id": "9821",
  "severity": "HIGH",
  "problem": "CPU utilization above 90%",
  "metric": "system.cpu.util",
  "value": 96.4,
  "timestamp": "2026-11-02T12:30:00Z"
}
```
- **Réponse HTTP 202 Accepted** :
```json
{
  "status": "accepted",
  "message_id": "1730557800000-0",
  "event_id": "45821",
  "event_type": "PROBLEM",
  "idempotency_key": "c57d..."
}
```

---

## 2. Endpoints Incidents

### `GET /api/v1/incidents`
- **Filtres** : `status`, `severity`, `limit`
- **Réponse** : Liste paginée des incidents consolidés avec identifiants GLPI et Zabbix.

### `GET /api/v1/incidents/{id}`
- **Réponse** : Détail complet de l'incident, événements corrélés et dernier rapport de diagnostic IA.

### `POST /api/v1/incidents/{id}/analyze`
- **Description** : Déclenche manuellement une nouvelle analyse multi-agents LangGraph.

---

## 3. Endpoints Remédiation

### `GET /api/v1/actions/runbooks`
- **Réponse** : Catalogue des runbooks autorisés avec schémas de paramètres JSON.

### `POST /api/v1/actions/execute`
- **Corps (JSON)** :
```json
{
  "runbook_id": "rb-win-service-restart",
  "incident_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "parameters": {
    "service_name": "Spooler"
  },
  "approved_by_user_id": "technician-42"
}
```
- **Réponse HTTP 200** :
```json
{
  "execution_id": "7ca...",
  "status": "success",
  "exit_code": 0,
  "stdout": "Restart-Service: Service 'Spooler' successfully restarted.",
  "duration_seconds": 1.42,
  "verified_by_zabbix": true
}
```
