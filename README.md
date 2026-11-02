# AI IT Operations Platform

**Plateforme AIOps intelligente et modulaire connectant Zabbix, GLPI, LangGraph et pgvector.**

---

## 🌟 Présentation
AI IT Operations est une plateforme industrielle d'assistance aux opérations informatiques (NOC / SOC / Service Desk) permettant de :
- Recevoir et acquitter les alertes Zabbix en moins de 30 ms.
- Dédupliquer et corréler de façon déterministe les alertes en incidents majeurs.
- Créer et enrichir les tickets GLPI (avec recherche automatique dans la CMDB).
- Exécuter une recherche RAG hybride (vectorielle pgvector + textuelle) dans les connaissances GLPI.
- Orchestrer 7 agents spécialisés via LangGraph (Incident, Corrélation, RAG, Diagnostic, Résolution, Validation, Feedback).
- Proposer des runbooks contrôlés (Ansible / PowerShell / SSH) exécutables uniquement sous validation humaine (Niveau 3).
- Vérifier la résolution effective de l'incident via les métriques Zabbix.

---

## 🏗️ Architecture Technique
- **Backend** : FastAPI, Python 3.12, SQLAlchemy 2.0 Async, Pydantic v2.
- **Messagerie** : Redis Streams (Consumer Groups).
- **IA & RAG** : LangGraph, Ollama (`gemma4`, `qwen2.5`, `mistral`), pgvector.
- **Frontend** : Next.js 15, React 19, TypeScript, Tailwind CSS, Lucide.
- **Observabilité** : Prometheus, Grafana, OpenTelemetry.

---

## 🚀 Démarrage Rapide

### Avec Docker Compose
```bash
cp .env.example .env
docker compose up -d --build
```

### URLs d'Accès
- **Tableau de Bord Web** : `http://localhost:3005`
- **Documentation API (OpenAPI)** : `http://localhost:8005/docs`
- **Grafana** : `http://localhost:3006` (admin / admin_aiops_pass)
- **Prometheus** : `http://localhost:9095`

---

## 🧪 Tests Automatisés
```bash
uv run pytest tests/
```
