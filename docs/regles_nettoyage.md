# C3 — Règles de nettoyage et d'agrégation

Implémentées dans `src/data/clean.py`, vérifiées par `tests/test_data.py`. Le rapport chiffré avant/après est écrit dans `data/processed/quality_report.json` à chaque exécution.

| # | Règle | Justification | Test |
|---|---|---|---|
| R1 | Dédoublonnage communes sur `code_insee` | Le code INSEE est l'identifiant officiel | — |
| R2 | Dédoublonnage mesures sur `(code_insee, horodatage)` | Une collecte relancée renvoie les mêmes heures | `test_doublons_supprimes` |
| R3 | Valeurs hors bornes physiques mises à manquant (PM2.5 : 0–500, PM10 : 0–600, NO2 : 0–400, O3 : 0–400 µg/m³) | Erreurs de capteur ; une valeur négative n'a pas de sens | `test_valeurs_aberrantes_neutralisees_puis_interpolees` |
| R4 | Interpolation linéaire des manquants, limitée à 3 h consécutives par commune | Au-delà, l'interpolation inventerait une tendance | `test_interpolation_limitee_a_3_heures` |
| R5 | Suppression des lignes sans aucun polluant | Ligne inexploitable | — |
| R6 | Horodatage converti en UTC | Homogénéiser API et fichiers | `test_doublons_supprimes` |
| R7 | Polluants des épisodes normalisés (`PM 10` → `PM10`) | Jointure possible avec les mesures | `test_clean_episodes_normalise_et_rejette_dates_invalides` |
| R8 | Dates d'épisodes non interprétables rejetées | Pas de date = épisode inexploitable | idem |

## Tableau avant/après (à remplir avec ta vraie collecte pour la slide)

| Indicateur | Avant | Après |
|---|---|---|
| Lignes de mesures | | |
| Valeurs manquantes PM2.5 | | |
| Valeurs aberrantes neutralisées | | |
| Doublons supprimés | | |
