# Guide d'Installation et Déploiement : AI IT Operations

Ce document décrit la procédure complète de déploiement et de démarrage de la plateforme **AI IT Operations**.

---

## 1. Prérequis Système

- **Système d'exploitation** : Linux (Ubuntu 22.04+, Debian 12+, RHEL 9+) ou Windows avec Docker Desktop & WSL2.
- **Ressources minimales** :
  - CPU : 4 cœurs (8 cœurs recommandés avec LLM local).
  - RAM : 8 Go (16 Go recommandés avec Ollama et `gemma4:latest` ou `qwen2.5:7b`).
  - Disque : 20 Go d'espace libre.
- **Logiciels requis** :
  - Docker v24+ et Docker Compose v2.20+.
  - Python 3.11+ (ou `uv`).
  - Node.js 20+ (si build frontend hors conteneur).
  - Ollama (si inférence locale).

---

## 2. Ports Réseau Utilisés

Les ports hôtes ont été spécifiquement choisis pour ne pas entrer en conflit avec les installations existantes :

| Service | Port Hôte | Port Conteneur | Description |
|---|---|---|---|
| **PostgreSQL + pgvector** | `5435` | `5432` | Stockage relationnel et embeddings |
| **Redis Streams** | `6380` | `6379` | Bus de messages asynchrone |
| **FastAPI Gateway** | `8005` | `8000` | Point d'entrée HTTPS et webhooks |
| **Frontend Next.js** | `3005` | `3000` | Interface utilisateur web |
| **Prometheus** | `9095` | `9090` | Collecteur de métriques |
| **Grafana** | `3006` | `3000` | Tableaux de bord de supervision |

---

## 3. Déploiement en 3 Commandes avec Docker Compose

```bash
# 1. Cloner ou se positionner dans le répertoire du projet
cd c:\IA_ENV_LAB\AIOPS_ZABBIX_GLPI_LLM

# 2. Configurer les variables d'environnement
cp .env.example .env

# 3. Lancer l'ensemble des conteneurs
docker compose up -d --build
```

---

## 4. Vérification du Démarrage

- **API Documentation (Swagger UI)** : `http://localhost:8005/docs`
- **Frontend Web** : `http://localhost:3005`
- **Grafana** : `http://localhost:3006` (Identifiants : `admin` / `admin_aiops_pass`)
- **Prometheus** : `http://localhost:9095`
- **Probe de santé** :
  ```bash
  curl http://localhost:8005/health/ready
  ```
