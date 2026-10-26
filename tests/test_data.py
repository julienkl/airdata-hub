"""C1/C3 - Tests de la collecte (parsing) et des règles de nettoyage."""
from pathlib import Path

import pandas as pd

from src.data.clean import clean_episodes, clean_mesures, clean_stations, lambert93_vers_wgs84
from src.data.collect import parse_episodes, robots_autorise

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _episodes_html() -> str:
    return (FIXTURES / "airparif_episodes_extrait.html").read_text(encoding="utf-8")


def test_parse_episodes_structure_airparif():
    rows = parse_episodes(_episodes_html(), base_url="https://www.airparif.fr/historique-des-episodes-de-pollution")
    assert len(rows) == 4  # les 3 lignes d'en-tête sont ignorées
    assert rows[0] == {"niveau": "Informations", "polluant": "PM10", "date": "06/03/2026",
                       "critere_population": True, "critere_surface": True,
                       "lien": "https://www.airparif.fr/episode/123"}
    assert rows[1]["critere_surface"] is False and rows[2]["critere_population"] is False


def test_clean_episodes_normalise_et_decrit_la_zone():
    raw = parse_episodes(_episodes_html()) + [{"niveau": "Informations", "polluant": "PM 10", "date": "pas une date",
                                               "critere_population": True, "critere_surface": False}]
    df, stats = clean_episodes(raw)
    assert len(df) == 4 and stats["dates_invalides_rejetees"] == 1
    assert set(df["niveau"]) == {"information", "alerte"}
    assert df.loc[0, "zone"] == "Île-de-France (population > 10 % d'un département et surface > 100 km²)"


def test_clean_stations_deduit_le_referentiel():
    # Jeu de test au format réel du fichier Airparif « mes idf horaire pm10 » (coordonnées x/y en Lambert-93).
    df, stats = clean_stations(FIXTURES / "airparif_stations_extrait.csv")
    assert stats["lignes_brutes_mesures"] == 4 and len(df) == 3  # 4 mesures, 3 stations distinctes
    assert {"code_station", "nom_station", "typologie", "insee_com", "lat", "lon"} <= set(df.columns)
    assert "valeur" not in df.columns  # le référentiel ne garde pas les mesures
    assert stats["coordonnees_converties_lambert93_vers_wgs84"] == 3
    assert stats["periode_des_mesures"] == "2017-09-18 → 2017-09-19"


def test_conversion_lambert93_vers_wgs84():
    lat, lon = lambert93_vers_wgs84(652469, 6862035)  # point de contrôle : centre de Paris
    assert abs(lat - 48.8566) < 0.001 and abs(lon - 2.3522) < 0.001


def test_robots_txt_interdit(monkeypatch):
    class R:
        status_code = 200
        text = "User-agent: *\nDisallow: /historique-des-episodes-de-pollution\n"
    monkeypatch.setattr("src.data.collect.requests.get", lambda *a, **k: R())
    assert robots_autorise("https://www.airparif.fr/historique-des-episodes-de-pollution") is False


def test_robots_txt_autorise(monkeypatch):
    class R:
        status_code = 200
        text = "User-agent: *\nDisallow: /admin/\n"
    monkeypatch.setattr("src.data.collect.requests.get", lambda *a, **k: R())
    assert robots_autorise("https://www.airparif.fr/historique-des-episodes-de-pollution") is True


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
