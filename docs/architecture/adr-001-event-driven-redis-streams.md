# ADR-001 : Architecture Événementielle avec Redis Streams

## Status
Accepted

## Context
- **Problème** : Les webhooks émis par Zabbix Server doivent être acquittés immédiatement (< 50 ms) pour éviter les retries intempestifs du serveur de supervision. Parallèlement, les tâches d'enrichissement CMDB GLPI, de recherche RAG et d'orchestration multi-agents LangGraph prennent plusieurs secondes.
- **Contraintes** : Haute fiabilité, aucune perte d'alerte en cas de surcharge, capacité de reprise après incident (dead-letter queue).

## Options Considered
| Option | Pros | Cons | Complexité |
|--------|------|------|------------|
| Traitement HTTP synchrone direct | Simple, sans composant tiers | Bloquant, timeout Zabbix fréquent, perte d'alertes | Faible |
| Celery + RabbitMQ | Mature, écosystème Python riche | 2 briques supplémentaires, configuration lourde | Élevée |
| Redis Streams (Consumer Groups) | Léger, très rapide, persistance intégrée, ACK explicite | Nécessite un worker consommateur asynchrone | Moyenne |

## Decision
Nous choisissons **Redis Streams** avec des groupes de consommateurs dédiés (`orchestrator-group`, `remediation-group`, `kb-sync-group`).

## Rationale
Redis Streams permet à la FastAPI Gateway d'écrire l'événement validé avec `XADD` et de répondre `202 Accepted` en moins de 30 ms. Les workers consomment avec `XREADGROUP` et confirment le traitement via `XACK`.

## Consequences
- **Positif** : Latence d'ingestion ultra-faible, découplage total, tolérance aux pannes.
- **Négatif** : Nécessite la surveillance de la taille du stream (backlog).
- **Mitigation** : Métriques Prometheus exposant `redis_stream_lag` et alertes en cas de rétention excessive.

## Revisit Trigger
- Volume d'événements dépassant 10 000 alertes/seconde nécessitant le passage à Apache Kafka.
