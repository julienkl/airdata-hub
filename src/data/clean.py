"""C3 - Nettoyage, homogénéisation et agrégation des données brutes.

Usage :
    python -m src.data.clean

- Mesures de qualité de l'air : fusion de TOUTES les collectes présentes dans data/raw/air/
  (chaque collecte couvre les N derniers jours, les collectes successives se chevauchent),
  puis dédoublonnage, contrôle des bornes, interpolation limitée.
- Communes, épisodes, stations : fichier le plus récent de chaque source.

Sorties :
    data/processed/*.csv                 données propres
    data/processed/quality_report.json   indicateurs avant/après (machine)
    data/processed/quality_report.md     tableau avant/après prêt pour le rapport et la slide C3
Les règles sont documentées dans docs/regles_nettoyage.md.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
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


def all_files(source: str, pattern: str = "*.json") -> list[Path]:
    return sorted((RAW / source).glob(pattern))


def clean_communes(raw: list[dict]) -> tuple[pd.DataFrame, dict]:
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
    avant = len(df)
    sans_population = int(df["population"].isna().sum())
    df = df.drop_duplicates("code_insee")
    df["population"] = df["population"].fillna(0).astype(int)
    return df, {"lignes_brutes": avant, "doublons_supprimes": avant - len(df),
                "population_manquante_remplacee_par_0": sans_population, "lignes_finales": len(df)}


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
    cols = [c for c in BOUNDS if c in df]

    stats: dict = {
        "lignes_brutes": int(len(df)),
        "communes": int(df["code_insee"].nunique()),
        "manquants_avant": {p: int(df[p].isna().sum()) for p in cols},
    }

    # R6 : horodatage homogène en UTC
    df["horodatage"] = pd.to_datetime(df["horodatage"], utc=True)

    # R2 : dédoublonnage (collectes qui se chevauchent). On garde la valeur la plus récente collectée.
    avant = len(df)
    df = df.drop_duplicates(["code_insee", "horodatage"], keep="last")
    stats["doublons_supprimes"] = avant - len(df)

    # R3 : valeurs hors bornes physiques -> manquantes
    aberrantes = 0
    for col, (lo, hi) in BOUNDS.items():
        if col not in df:
            continue
        mask = (df[col] < lo) | (df[col] > hi)
        aberrantes += int(mask.sum())
        df.loc[mask, col] = pd.NA
    stats["valeurs_aberrantes_neutralisees"] = aberrantes

    # R4 : interpolation linéaire limitée à 3 h consécutives par commune
    df = df.sort_values(["code_insee", "horodatage"])
    manquants_avant_interp = int(df[cols].isna().sum().sum())
    for col in cols:
        df[col] = df.groupby("code_insee")[col].transform(lambda s: s.interpolate(limit=3, limit_area="inside"))
    stats["valeurs_interpolees"] = manquants_avant_interp - int(df[cols].isna().sum().sum())

    # R5 : suppression des lignes sans aucun polluant
    avant = len(df)
    df = df.dropna(subset=cols, how="all")
    stats["lignes_vides_supprimees"] = avant - len(df)

    stats.update({
        "manquants_apres": {p: int(df[p].isna().sum()) for p in cols},
        "lignes_finales": int(len(df)),
        "periode": [str(df["horodatage"].min()), str(df["horodatage"].max())] if len(df) else None,
    })
    return df, stats


def clean_episodes(raw: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=["date", "zone", "polluant", "niveau"])
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce").dt.date
    df["polluant"] = df["polluant"].str.upper().str.replace(".", "", regex=False).str.replace(" ", "", regex=False)
    df["niveau"] = df["niveau"].str.lower().str.strip()
    return df.dropna(subset=["date"]).drop_duplicates()


def clean_stations(path: Path) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [c.strip().lower() for c in df.columns]
    avant = len(df)
    df = df.drop_duplicates()
    return df, {"lignes_brutes": avant, "doublons_supprimes": avant - len(df), "lignes_finales": len(df)}


def to_markdown(report: dict) -> str:
    """Tableau avant/après lisible, à coller dans le rapport et la slide C3."""
    lines = [f"# Rapport qualité — généré le {report['genere_le']}", ""]
    m = report.get("mesures")
    if m:
        lines += [
            f"## Mesures de qualité de l'air ({report['fichiers_air_fusionnes']} collectes fusionnées, "
            f"{m['communes']} communes)", "",
            "| Indicateur | Avant | Après |", "|---|---|---|",
            f"| Lignes | {m['lignes_brutes']} | {m['lignes_finales']} |",
            f"| Doublons (collectes qui se chevauchent) | {m['doublons_supprimes']} | 0 |",
            f"| Valeurs aberrantes (hors bornes physiques) | {m['valeurs_aberrantes_neutralisees']} | 0 |",
        ]
        for p in m["manquants_avant"]:
            lines.append(f"| Valeurs manquantes {p.upper()} | {m['manquants_avant'][p]} | {m['manquants_apres'][p]} |")
        lines += [f"| Valeurs interpolées (trous ≤ 3 h) | — | {m['valeurs_interpolees']} |",
                  f"| Lignes sans aucun polluant supprimées | — | {m['lignes_vides_supprimees']} |", ""]
        if m.get("periode"):
            lines += [f"Période couverte : {m['periode'][0]} → {m['periode'][1]}", ""]
    for name in ("communes", "stations"):
        s = report.get(name)
        if s:
            lines += [f"## {name.capitalize()}", "", "| Indicateur | Valeur |", "|---|---|"]
            lines += [f"| {k.replace('_', ' ')} | {v} |" for k, v in s.items()] + [""]
    if "episodes" in report:
        lines += ["## Épisodes de pollution", "", f"Lignes retenues : {report['episodes']['lignes']}", ""]
    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"genere_le": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

    if p := latest("communes"):
        communes, stats = clean_communes(json.loads(p.read_text(encoding="utf-8")))
        communes.to_csv(OUT / "communes.csv", index=False)
        report["communes"] = stats

    air_files = all_files("air")
    if air_files:
        raw = [serie for f in air_files for serie in json.loads(f.read_text(encoding="utf-8"))]
        mesures, stats = clean_mesures(raw)
        mesures.to_csv(OUT / "mesures.csv", index=False)
        report["fichiers_air_fusionnes"] = len(air_files)
        report["mesures"] = stats

    if p := latest("episodes"):
        episodes = clean_episodes(json.loads(p.read_text(encoding="utf-8")))
        episodes.to_csv(OUT / "episodes.csv", index=False)
        report["episodes"] = {"lignes": len(episodes)}

    if p := latest("stations", "*.csv"):
        stations, stats = clean_stations(p)
        stations.to_csv(OUT / "stations.csv", index=False)
        report["stations"] = stats

    (OUT / "quality_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "quality_report.md").write_text(to_markdown(report), encoding="utf-8")
    log.info("rapport qualité écrit : data/processed/quality_report.md")
    print(to_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())