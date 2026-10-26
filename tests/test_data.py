"""C1/C3 - Tests de la collecte (parsing) et des règles de nettoyage."""
from pathlib import Path

import pandas as pd

from src.data.clean import clean_episodes, clean_mesures
from src.data.collect import parse_episodes

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_parse_episodes_extrait_les_lignes_du_tableau():
    rows = parse_episodes((SAMPLES / "episodes.html").read_text(encoding="utf-8"))
    assert len(rows) == 4
    assert rows[0] == {"date": "12/01/2026", "zone": "Paris", "polluant": "PM10", "niveau": "Information"}


def test_clean_episodes_normalise_et_rejette_dates_invalides():
    df = clean_episodes(parse_episodes((SAMPLES / "episodes.html").read_text(encoding="utf-8")))
    assert len(df) == 3  # la ligne "date inconnue" est rejetée
    assert set(df["polluant"]) == {"PM10", "O3"}  # "PM 10" homogénéisé en "PM10"
    assert set(df["niveau"]) <= {"information", "alerte"}


def _serie(values_pm25):
    n = len(values_pm25)
    return [{
        "code_insee": "75056",
        "data": {"hourly": {
            "time": [f"2026-01-01T{h:02d}:00" for h in range(n)],
            "pm2_5": values_pm25,
            "pm10": [20.0] * n,
            "nitrogen_dioxide": [30.0] * n,
            "ozone": [40.0] * n,
        }},
    }]


def test_valeurs_aberrantes_neutralisees_puis_interpolees():
    df, stats = clean_mesures(_serie([10.0, 9999.0, 12.0]))
    assert stats["valeurs_aberrantes_neutralisees"] == 1
    assert df["pm25"].tolist() == [10.0, 11.0, 12.0]


def test_interpolation_limitee_a_3_heures():
    df, _ = clean_mesures(_serie([10.0, None, None, None, None, None, 16.0]))
    assert df["pm25"].isna().sum() == 2  # au-delà de 3 h consécutives on ne comble pas


def test_doublons_supprimes():
    raw = _serie([10.0, 11.0]) * 2
    df, _ = clean_mesures(raw)
    assert len(df) == 2
    assert pd.api.types.is_datetime64_any_dtype(df["horodatage"])


def test_fusion_de_collectes_qui_se_chevauchent():
    # Collecte du jour J (heures 0-5) puis du jour J+1 (heures 3-8) : 3 heures en commun.
    def serie(start, n):
        return {"code_insee": "75056", "data": {"hourly": {
            "time": [f"2026-01-01T{h:02d}:00" for h in range(start, start + n)],
            "pm2_5": [10.0] * n, "pm10": [20.0] * n, "nitrogen_dioxide": [30.0] * n, "ozone": [40.0] * n}}}
    df, stats = clean_mesures([serie(0, 6), serie(3, 6)])
    assert stats["lignes_brutes"] == 12
    assert stats["doublons_supprimes"] == 3
    assert len(df) == 9