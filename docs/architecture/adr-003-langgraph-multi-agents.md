# ADR-003 : Orchestration Multi-Agents LangGraph avec Checkpoints

## Status
Accepted

## Context
- **Problème** : L'analyse d'incident nécessite d'enchaîner l'inspection des symptômes, la corrélation d'événements, la recherche de connaissances, la formulation d'hypothèses, la sélection d'actions et la validation humaine (Human-in-the-Loop).
- **Contraintes** : Déterminisme du flux opérationnel, gestion des interruptions/reprises, prévention des hallucinations.

## Options Considered
| Option | Pros | Cons | Complexité |
|--------|------|------|------------|
| Multi-agent autonome (CrewAI / AutoGen) | Émergent, créatif | Difficilement contrôlable, risque d'actions imprévisibles | Élevée |
| Graphe d'états LangGraph | Machine à états typée, points d'arrêts (breakpoints) explicites pour validation humaine | Nécessite une définition rigoureuse des états et transitions | Moyenne |

## Decision
Nous choisissons **LangGraph** avec 7 agents spécialisés typés avec Pydantic v2 et points d'arrêt d'approbation humaine.
