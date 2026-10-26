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
| R9 | Coordonnées des stations converties de Lambert-93 (EPSG:2154) en WGS84 (latitude/longitude) | Homogénéiser avec les coordonnées GPS des communes ; une valeur > 1000 indique des mètres en Lambert-93 | `test_conversion_lambert93_vers_wgs84`, `test_clean_stations_deduit_le_referentiel` |

## Tableau avant/après (à remplir avec ta vraie collecte pour la slide)

| Indicateur | Avant | Après |
|---|---|---|
| Lignes | 3528 | 3360 |
| Doublons (collectes qui se chevauchent) | 168 | 0 |
| Valeurs aberrantes (hors bornes physiques) | 0 | 0 |
| Valeurs manquantes PM25 | 0 | 0 |
| Valeurs manquantes PM10 | 0 | 0 |
| Valeurs manquantes NO2 | 0 | 0 |
| Valeurs manquantes O3 | 0 | 0 |
| Valeurs interpolées (trous ≤ 3 h) | — | 0 |
| Lignes sans aucun polluant supprimées | — | 0 |

**Limite connue :** le fichier Airparif des stations couvre 2017-09-18 → 2024-06-24 (plus mis à jour). Il sert de référentiel des stations ; les mesures récentes proviennent d'Open-Meteo.