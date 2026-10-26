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
python -m src.data.collect --source all --departement 75 --days 7

# 2. Nettoyage (C3)
python -m src.data.clean

# 3. Base + import (C4)
docker compose up -d db
export DATABASE_URL=postgresql+psycopg2://airdata:<mdp>@localhost:5432/airdata
python -m src.db.import_data
python -m src.db.import_data --create-user admin --password '<mdp>' --role admin

# 4. API (C5)
uvicorn api.main:app --reload       # puis http://localhost:8000/docs → Authorize

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
src/data/collect.py      C1  collecte multi-sources, retries, logs
sql/queries.sql          C2  requêtes documentées + optimisation
src/data/clean.py        C3  règles de nettoyage, rapport qualité
src/db/                  C4  modèle, import, purge RGPD
api/main.py              C5  API REST + JWT + OpenAPI
docs/                        MCD, registre RGPD, règles, matrice de preuves
tests/                       tests données, base, API
.github/workflows/ci.yml     CI
reports/captures/            captures pour la soutenance
```

## Sources de données

| Source | Type | Licence |
|---|---|---|
| geo.api.gouv.fr | API REST | Licence Ouverte Etalab |
| Open-Meteo Air Quality | API REST | CC BY 4.0 (citer Open-Meteo / CAMS) |
| Stations de mesure | Fichier CSV (`data/samples/stations.csv` exemple, à remplacer par le fichier data.gouv) | Licence Ouverte |
| Épisodes de pollution | Scraping HTML (`EPISODES_URL`), page exemple fournie | Vérifier CGU et robots.txt |

## À faire pour finaliser

- [ ] Remplacer `data/samples/stations.csv` par le vrai fichier data.gouv et adapter `clean_stations`
- [ ] Choisir la page d'épisodes à scraper, vérifier robots.txt, adapter `parse_episodes`
- [ ] Remplir le tableau avant/après dans `docs/regles_nettoyage.md` avec ta vraie collecte
- [ ] Faire les captures listées dans `docs/matrice_preuves.md`
