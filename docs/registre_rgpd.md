# C4 — Registre des traitements de données personnelles

> À compléter avec ton nom et les dates. Ce registre suit la structure recommandée par la CNIL pour un registre de traitement.

## Traitement n°1 — Gestion des abonnés aux alertes qualité de l'air

| Rubrique | Contenu |
|---|---|
| Responsable du traitement | *[Ton nom], projet AirData Hub* |
| Finalité | Envoyer des alertes de pollution pour la commune choisie par l'abonné |
| Base légale | Consentement (article 6.1.a du RGPD), recueilli par case à cocher non pré-cochée |
| Personnes concernées | Abonnés volontaires |
| Données collectées | Adresse email, commune suivie, date du consentement, date de dernière activité |
| Données exclues (minimisation) | Nom, adresse postale, géolocalisation précise, âge, données de santé |
| Destinataires | Le responsable du projet uniquement ; l'API publique n'expose **aucune** route sur la table `abonne` |
| Durée de conservation | 24 mois après la dernière activité ; suppression immédiate si consentement retiré |
| Mise en œuvre de la conservation | `python -m src.db.purge_rgpd`, planifié quotidiennement, testé dans `tests/test_api.py::test_purge_rgpd` |
| Transferts hors UE | Aucun (PostgreSQL hébergé localement / Docker) |
| Sécurité | Accès base par mot de passe en `.env` non versionné, API protégée par JWT, comptes API à mot de passe haché |
| Droits des personnes | Accès, rectification, effacement, retrait du consentement : par email au responsable, traitement sous 1 mois |

## Traitement n°2 — Comptes techniques de l'API

| Rubrique | Contenu |
|---|---|
| Finalité | Contrôler l'accès à l'API de données |
| Base légale | Intérêt légitime (sécurité du service) |
| Données | Identifiant, empreinte du mot de passe, rôle |
| Conservation | Durée du projet |

## Données non personnelles

Les mesures de qualité de l'air, communes et épisodes de pollution sont des données ouvertes et agrégées, sans lien avec une personne physique.
