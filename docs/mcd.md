# C4 — Modèle de données

## Choix du SGBD

| Critère | PostgreSQL (retenu) | SQLite | MongoDB |
|---|---|---|---|
| Données relationnelles (commune → mesures) | Oui, clés étrangères | Oui | Pas naturel |
| Séries temporelles, fonctions de fenêtre | Oui | Limité | Agrégations possibles |
| Multi-utilisateurs, droits, rôles | Oui | Non | Oui |
| Déploiement Docker | Image officielle | Fichier local | Image officielle |

PostgreSQL est retenu pour les jointures, les fonctions de fenêtre (requête Q3) et la gestion des rôles. SQLite sert uniquement aux tests automatisés.

## MCD

```mermaid
erDiagram
    COMMUNE ||--o{ MESURE : "est mesurée"
    COMMUNE ||--o{ ABONNE : "est suivie par"
    COMMUNE {
        string code_insee PK
        string nom
        string code_postal
        int population
        float lat
        float lon
    }
    MESURE {
        int id PK
        string code_insee FK
        datetime horodatage
        float pm25
        float pm10
        float no2
        float o3
    }
    EPISODE {
        int id PK
        date date
        string zone
        string polluant
        string niveau
    }
    ABONNE {
        int id PK
        string email "donnée personnelle"
        string code_insee FK
        bool consentement
        datetime date_consentement
        datetime derniere_activite
    }
    API_USER {
        string username PK
        string password_hash
        string role
    }
```

## MPD — contraintes notables

- `mesure` : contrainte d'unicité `(code_insee, horodatage)` → l'import est idempotent (relancer la collecte ne crée pas de doublons).
- Index sur `mesure.code_insee` et `mesure.horodatage`, plus l'index composite créé dans `sql/queries.sql` (Q6).
- `abonne.email` unique ; aucun mot de passe stocké pour les abonnés.
- `api_user.password_hash` : PBKDF2-SHA256 salé, 200 000 itérations (`src/security.py`).

Le MPD est défini en code dans `src/db/models.py` (source de vérité unique).

## Procédure d'installation

```bash
cp .env.example .env              # puis remplir les mots de passe
docker compose up -d db
python -m src.data.collect --source all
python -m src.data.clean
DATABASE_URL=postgresql+psycopg2://airdata:<mdp>@localhost:5432/airdata python -m src.db.import_data
```
