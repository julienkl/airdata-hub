# AirData Hub

Plateforme de collecte, nettoyage et mise à disposition de données de qualité de l'air par commune.
Projet de validation du **Bloc 1 (C1 à C5)** du titre RNCP Développeur en Intelligence Artificielle (Simplon).

```
sources (2 API, CSV, scraping) → data/raw → nettoyage → data/processed → PostgreSQL → API REST (JWT)
```

## Démarrage rapide

```bash
python -m venv .venv && source .venv/bin/activate     # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # remplir les secrets

# 1. Collecte (C1)
python -m src.data.collect --source all          # départements 75,92,93,94 et années N-1,N par défaut

# 2. Nettoyage (C3)
python -m src.data.clean

# 3. Base + import (C4)
docker compose up -d db
# Import dans PostgreSQL depuis le conteneur (fonctionne aussi sur PC Windows ARM)
docker compose run --rm api python -m src.db.import_data
docker compose run --rm api python -m src.db.import_data --create-user admin --password '<mdp>' --role admin
# Variante depuis ta machine (hors Windows ARM) :
# export DATABASE_URL=postgresql+psycopg://airdata:<mdp>@localhost:5432/airdata && python -m src.db.import_data

# 4. API (C5)
uvicorn api.main:app --reload       # puis http://localhost:8000/docs → Authorize

# 5. Interface de consultation (bonus) : consomme l'API, jamais la base
pip install -r app/requirements.txt
python -m streamlit run app/streamlit_app.py   # port 8501, se connecter avec un compte API

# Requêtes SQL (C2)
docker compose exec db psql -U airdata -d airdata -f /sql/queries.sql

# RGPD
python -m src.db.purge_rgpd --dry-run
```

Sans `DATABASE_URL`, le projet utilise un fichier SQLite local (pratique pour développer).

Tout en Docker : `docker compose up --build` (l'API attend que la base soit prête).

## Tests

```bash
pytest -v --cov=src --cov=api
```

## Structure

```
src/data/collect.py      C1  collecte 4 sources réelles (2 API, CSV, scraping), retries, logs, robots.txt
sql/queries.sql          C2  requêtes documentées + optimisation
src/data/clean.py        C3  règles de nettoyage, rapport qualité
src/db/                  C4  modèle, import, purge RGPD
api/main.py              C5  API REST + JWT + OpenAPI
app/                     bonus interface Streamlit (classement, évolution, carte, épisodes) via l'API
docs/                        MCD, registre RGPD, règles, matrice de preuves
tests/                       tests données, base, API
.github/workflows/ci.yml     CI
reports/captures/            captures pour la soutenance
```

## Sources de données

| Source | Type | Producteur | Licence |
|---|---|---|---|
| Communes (`geo.api.gouv.fr`) | API REST | Etalab / INSEE | Licence Ouverte 2.0 |
| Qualité de l'air horaire (`air-quality-api.open-meteo.com`) | API REST | Open-Meteo (modèle CAMS) | CC BY 4.0 |
| Mesures aux stations « mes idf horaire pm10 » | Fichier CSV (`STATIONS_CSV_URL`) | Airparif | ODbL — citer Airparif |
| Historique des épisodes de pollution (`airparif.fr`) | Scraping HTML | Airparif | page publique, `robots.txt` vérifié à chaque collecte |

Le scraping respecte le `robots.txt` (vérification automatique, arrêt si interdit), s'identifie par un User-Agent
explicite, espace ses requêtes de 2 s et conserve chaque page brute dans `data/raw/episodes/` pour la traçabilité.
Les fichiers de `tests/fixtures/` sont des **jeux de test** reproduisant la structure des sources ; ils ne sont
jamais utilisés par la collecte.

## À faire pour finaliser

- [ ] Renseigner `STATIONS_CSV_URL` dans `.env` (lien CSV du portail open data Airparif)
- [ ] Relancer la collecte régulièrement pour enrichir l'historique
- [ ] Remplir le tableau avant/après dans `docs/regles_nettoyage.md` avec ta vraie collecte
- [ ] Faire les captures listées dans `docs/matrice_preuves.md`
