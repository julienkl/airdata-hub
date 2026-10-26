# Matrice compétences → preuves (Bloc 1)

| Comp. | Preuve technique | Où dans le dépôt | Capture à faire pour la slide | Statut |
|---|---|---|---|---|
| **C1** Extraction multi-sources | 4 sources (2 API REST, 1 fichier CSV, 1 scraping), retries, logs, sortie horodatée | `src/data/collect.py`, `logs/collect.log`, `data/raw/` | Terminal `python -m src.data.collect --source all` + arborescence `data/raw/` + extrait du log | ☐ |
| **C2** Requêtes SQL | 6 requêtes commentées (jointures, fenêtre glissante, `FILTER`, index + `EXPLAIN ANALYZE`) | `sql/queries.sql` | Résultat de Q1 et Q3 + les deux plans de Q6 (avant/après index) | ☐ |
| **C3** Agrégation / nettoyage | 8 règles documentées, rapport qualité, tests | `src/data/clean.py`, `docs/regles_nettoyage.md`, `data/processed/quality_report.json`, `tests/test_data.py` | Tableau avant/après + `pytest tests/test_data.py -v` | ☐ |
| **C4** Base de données RGPD | MCD/MPD, choix SGBD, import idempotent, registre, purge automatisée | `docs/mcd.md`, `src/db/models.py`, `src/db/import_data.py`, `docs/registre_rgpd.md`, `src/db/purge_rgpd.py` | Diagramme MCD + `docker compose up` + `purge_rgpd --dry-run` | ☐ |
| **C5** API REST de données | FastAPI, JWT, validation, pagination, OpenAPI, tests | `api/main.py`, `src/security.py`, `tests/test_api.py` | Swagger `/docs` + appel sans jeton (401) puis avec jeton (200) + `pytest -v` | ☐ |
| (bonus) CI | Tests et build Docker à chaque push | `.github/workflows/ci.yml` | Onglet Actions avec un run vert | ☐ |

Règle : aucune ligne ne reste « on l'a fait » sans fichier et capture associés.
