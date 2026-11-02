# ADR-002 : Stockage Unifié PostgreSQL 16 + pgvector

## Status
Accepted

## Context
- **Problème** : La plateforme manipule des données relationnelles strictes (tickets, événements, exécutions de runbooks, logs d'audit) et des représentations vectorielles d'articles de connaissances et de procédures (RAG).
- **Contraintes** : Cohérence transactionnelle, gestion des droits par entité GLPI, simplicité d'exploitation.

## Options Considered
| Option | Pros | Cons | Complexité |
|--------|------|------|------------|
| PostgreSQL + Qdrant/Pinecone | Base vectorielle dédiée spécialisée | Double maintenance, risque de désynchronisation des droits | Élevée |
| PostgreSQL 16 + pgvector | ACID natif, requêtes hybrides jointes en SQL, une seule sauvegarde | Nécessite un dimensionnement mémoire adapté | Faible |

## Decision
Nous adoptons **PostgreSQL 16 avec l'extension pgvector** et indexation HNSW (`cosine distance`).

## Rationale
pgvector permet de filtrer les résultats vectoriels directement dans la clause `WHERE` avec les permissions d'entités GLPI (`WHERE entity_id IN (...)`), évitant toute fuite documentaire inter-clients sans recourir à un composant tiers.
