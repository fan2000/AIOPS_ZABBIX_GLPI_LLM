# ADR-004 : Moteur de Remédiation Contrôlée et Sandbox d'Exécution

## Status
Accepted

## Context
- **Problème** : Permettre à la plateforme d'appliquer des remédiations (ex: relance de service, purge de disques) sans jamais autoriser le LLM à forger ou exécuter du code shell arbitraire non contrôlé.
- **Contraintes** : Sécurité DevSecOps stricte, conformité aux privilèges minimaux, traçabilité d'audit inaltérable.

## Options Considered
| Option | Pros | Cons | Complexité |
|--------|------|------|------------|
| LLM générant du Bash/PowerShell libre | Très flexible | Vulnérabilité critique, risque de destruction ou d'injection | Inacceptable |
| Catalogue de runbooks paramétrés avec validation de schéma | Sécurité absolue, paramètres typés, liste blanche | Moins flexible qu'un shell ouvert | Faible |

## Decision
Nous imposons un **catalogue strict de runbooks** avec schémas JSON Schema validés, exécution en subprocess sandboxé sans shell arbitraire, validation humaine obligatoire (Niveau 3) et double vérification post-exécution via les métriques Zabbix.
