# Guide Utilisateur Technicien : AI IT Operations

Ce guide est destiné aux techniciens NOC / SOC et opérateurs de support ITIL utilisant la plateforme AI IT Operations au quotidien.

---

## 1. Cycle de Traitement d'un Incident

### Étape 1 : Notification & Prise en Charge
Lorsqu'une alerte Zabbix survient :
1. Un ticket GLPI est automatiquement créé (ex: `#15248`) avec les informations d'équipement issues de la CMDB.
2. L'incident apparaît immédiatement dans la console **Incidents AIOps**.
3. Les alertes concomitantes (ex: CPU + RAM + Latence) sont automatiquement regroupées dans le même incident.

### Étape 2 : Consultation du Diagnostic IA
En ouvrant l'incident :
- **Observations vérifiées** : Liste des métriques factuelles (ex: CPU mesuré à 96.4%, 18 min de durée).
- **Hypothèses de cause racine** : Classées par probabilité (`probable`, `unconfirmed`, `confirmed`).
- **Contrôles recommandés** : Vérifications suggérées avant toute action.
- **Sources documentaires** : Liens directs vers les articles KB GLPI ou tickets similaires résolus.

---

## 2. Validation et Exécution d'une Action Contrôlée (Niveau 3)

1. Examiner la proposition d'action (ex: *Redémarrage du service Spooler* ou *Purge des logs archivés*).
2. Cliquer sur **Approuver & Exécuter le Runbook**.
3. La plateforme exécute l'action en sandbox sécurisée avec privilèges minimaux.
4. Le résultat d'exécution (`stdout`, code retour, durée) s'affiche en direct et est consigné dans le suivi privé du ticket GLPI.

---

## 3. Clôture de l'Incident et Retour d'Expérience

- Lorsque Zabbix détecte le retour à la normale, un événement `RECOVERY` est reçu.
- Le statut passe à `RECOVERY_OBSERVED`.
- Le technicien valide la résolution dans GLPI.
- Le **Knowledge Feedback Agent** propose automatiquement la mise à jour ou la création d'un article KB basé sur les actions qui ont fonctionné.
