"""C3 - Nettoyage, homogénéisation et agrégation des données brutes.

Usage :
    python -m src.data.clean

Lit le fichier le plus récent de chaque source dans data/raw/, applique les règles
documentées dans docs/regles_nettoyage.md et écrit data/processed/*.csv
+ data/processed/quality_report.json (avant/après, preuve C3).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
log = logging.getLogger("clean")

POLLUTANTS = {"pm2_5": "pm25", "pm10": "pm10", "nitrogen_dioxide": "no2", "ozone": "o3"}
# Bornes physiquement plausibles (µg/m³) : au-delà, on considère la valeur aberrante.
BOUNDS = {"pm25": (0, 500), "pm10": (0, 600), "no2": (0, 400), "o3": (0, 400)}


def latest(source: str, pattern: str = "*.json") -> Path | None:
    files = sorted((RAW / source).glob(pattern))
    return files[-1] if files else None


def clean_communes(raw: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "code_insee": [c["code"] for c in raw],
            "nom": [c["nom"].strip() for c in raw],
            "code_postal": [(c.get("codesPostaux") or [None])[0] for c in raw],
            "population": [c.get("population") for c in raw],
            "lon": [c.get("centre", {}).get("coordinates", [None, None])[0] for c in raw],
            "lat": [c.get("centre", {}).get("coordinates", [None, None])[1] for c in raw],
        }
    )
    df = df.drop_duplicates("code_insee")
    df["population"] = df["population"].fillna(0).astype(int)
    return df


def clean_mesures(raw: list[dict]) -> tuple[pd.DataFrame, dict]:
    frames = []
    for serie in raw:
        hourly = serie["data"].get("hourly", {})
        df = pd.DataFrame(hourly)
        if df.empty:
            continue
        df["code_insee"] = serie["code_insee"]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["time", "code_insee", *POLLUTANTS])
    df = df.rename(columns={"time": "horodatage", **POLLUTANTS})

    stats = {"lignes_brutes": int(len(df)), "manquants_avant": {p: int(df[p].isna().sum()) for p in BOUNDS if p in df}}

    df["horodatage"] = pd.to_datetime(df["horodatage"], utc=True)
    df = df.drop_duplicates(["code_insee", "horodatage"])

    aberrantes = 0
    for col, (lo, hi) in BOUNDS.items():
        if col not in df:
            continue
        mask = (df[col] < lo) | (df[col] > hi)
        aberrantes += int(mask.sum())
        df.loc[mask, col] = pd.NA

    # Règle : interpolation linéaire limitée à 3 h consécutives par commune, sinon la valeur reste manquante.
    df = df.sort_values(["code_insee", "horodatage"])
    for col in BOUNDS:
        if col in df:
            df[col] = df.groupby("code_insee")[col].transform(lambda s: s.interpolate(limit=3))

    # Règle : on supprime les lignes où tous les polluants sont manquants.
    df = df.dropna(subset=[c for c in BOUNDS if c in df], how="all")

    stats.update(
        {
            "valeurs_aberrantes_neutralisees": aberrantes,
            "manquants_apres": {p: int(df[p].isna().sum()) for p in BOUNDS if p in df},
            "lignes_finales": int(len(df)),
        }
    )
    return df, stats


def clean_episodes(raw: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=["date", "zone", "polluant", "niveau"])
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce").dt.date
    df["polluant"] = df["polluant"].str.upper().str.replace(".", "", regex=False).str.replace(" ", "", regex=False)
    df["niveau"] = df["niveau"].str.lower().str.strip()
    return df.dropna(subset=["date"]).drop_duplicates()


def clean_stations(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [c.strip().lower() for c in df.columns]
    return df.drop_duplicates()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {}

    if p := latest("communes"):
        communes = clean_communes(json.loads(p.read_text(encoding="utf-8")))
        communes.to_csv(OUT / "communes.csv", index=False)
        report["communes"] = {"lignes": len(communes)}
    if p := latest("air"):
        mesures, stats = clean_mesures(json.loads(p.read_text(encoding="utf-8")))
        mesures.to_csv(OUT / "mesures.csv", index=False)
        report["mesures"] = stats
    if p := latest("episodes"):
        episodes = clean_episodes(json.loads(p.read_text(encoding="utf-8")))
        episodes.to_csv(OUT / "episodes.csv", index=False)
        report["episodes"] = {"lignes": len(episodes)}
    if p := latest("stations", "*.csv"):
        stations = clean_stations(p)
        stations.to_csv(OUT / "stations.csv", index=False)
        report["stations"] = {"lignes": len(stations)}

    (OUT / "quality_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("rapport qualité : %s", json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
