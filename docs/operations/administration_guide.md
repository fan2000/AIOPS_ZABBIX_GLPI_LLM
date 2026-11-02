# Guide d'Administration : AI IT Operations

Ce guide s'adresse aux ingénieurs DevSecOps et administrateurs de la plateforme AIOps.

---

## 1. Configuration des Intégrations

### 1.1 Configuration du Webhook Zabbix Server
Dans l'interface web Zabbix :
1. Aller dans **Administration > Media types**.
2. Créer un nouveau Media Type nommé `AI IT Operations Webhook` de type **Webhook**.
3. Renseigner les paramètres :
   - `URL` : `https://<ip_ou_domaine_aiops>:8005/api/v1/webhooks/zabbix`
   - `HTTPHeader` : `Authorization: Bearer <ZABBIX_WEBHOOK_SECRET>`
4. Script Webhook Javascript :
```javascript
try {
    var req = new HttpRequest();
    req.addHeader('Content-Type: application/json');
    req.addHeader('Authorization: Bearer ' + Zabbix.params.webhook_secret);
    var payload = {
        event_id: Zabbix.params.event_id,
        event_type: Zabbix.params.event_type,
        host_id: Zabbix.params.host_id,
        host_name: Zabbix.params.host_name,
        trigger_id: Zabbix.params.trigger_id,
        severity: Zabbix.params.severity,
        problem: Zabbix.params.problem,
        metric: Zabbix.params.metric,
        value: parseFloat(Zabbix.params.value),
        timestamp: new Date().toISOString()
    };
    var resp = req.post(Zabbix.params.api_url, JSON.stringify(payload));
    return resp;
} catch (error) {
    Zabbix.log(3, 'Erreur envoi webhook AIOps: ' + error);
    throw error;
}
```

---

## 2. Configuration GLPI REST API

1. Dans GLPI, aller dans **Configuration > Générale > API**.
2. Activer l'API REST.
3. Générer un `App-Token`.
4. Pour l'utilisateur de service AIOps (`glpi`), générer un `User-Token` dans son profil utilisateur.
5. Reporter ces clés dans le fichier `.env` (`GLPI_APP_TOKEN` et `GLPI_USER_TOKEN`).

---

## 3. Gestion du Modèle LLM et Embeddings

- **Modèle local** : Par défaut, Ollama écoute sur `http://localhost:11434`.
  - Pour télécharger le modèle recommandé :
    ```bash
    ollama pull nomic-embed-text
    ollama pull gemma4:latest
    ```
- **Mode Dégradé** : Si Ollama est arrêté, la plateforme bascule automatiquement en mode heuristique sans interruption de service.
