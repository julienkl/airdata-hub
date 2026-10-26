"""C1 - Collecte automatisée multi-sources.

Usage :
    python -m src.data.collect --source all
    python -m src.data.collect --source communes --departement 75
    python -m src.data.collect --source air --days 7

Sources :
    communes  -> API REST geo.api.gouv.fr (référentiel communes INSEE)
    air       -> API REST Open-Meteo Air Quality (mesures horaires PM2.5, PM10, NO2, O3)
    stations  -> fichier CSV (data.gouv.fr ou fichier local fourni dans data/samples/)
    episodes  -> scraping d'une page HTML publique d'épisodes de pollution

Chaque source écrit un fichier horodaté dans data/raw/<source>/ et journalise dans logs/collect.log.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
SAMPLES_DIR = ROOT / "data" / "samples"
LOG_DIR = ROOT / "logs"

GEO_API = "https://geo.api.gouv.fr/communes"
AIR_API = "https://air-quality-api.open-meteo.com/v1/air-quality"
AIR_VARS = "pm2_5,pm10,nitrogen_dioxide,ozone"
# À adapter : page publique listant les épisodes de pollution (vérifier robots.txt et CGU).
EPISODES_URL = os.getenv("EPISODES_URL", "")

USER_AGENT = "AirDataHub/0.1 (projet pedagogique RNCP; contact: voir README)"

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "collect.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("collect")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save(source: str, payload, ext: str = "json") -> Path:
    out_dir = RAW_DIR / source
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{source}_{_stamp()}.{ext}"
    if ext == "json":
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        path.write_text(payload, encoding="utf-8")
    log.info("source=%s fichier=%s", source, path.relative_to(ROOT))
    return path


def http_get(url: str, params: dict | None = None, retries: int = 3, backoff: float = 2.0) -> requests.Response:
    """GET avec retries exponentiels : la gestion d'erreurs fait partie de la preuve C1."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=20, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            log.warning("échec %s (tentative %d/%d) : %s", url, attempt, retries, exc)
            if attempt == retries:
                raise
            time.sleep(backoff ** attempt)
    raise RuntimeError("inatteignable")


def collect_communes(departements: str) -> list[dict]:
    """Collecte les communes d'un ou plusieurs départements (codes séparés par des virgules)."""
    communes: list[dict] = []
    for dep in [d.strip() for d in departements.split(",") if d.strip()]:
        resp = http_get(
            GEO_API,
            params={"codeDepartement": dep, "fields": "nom,code,codesPostaux,population,centre", "format": "json"},
        )
        communes.extend(resp.json())
    log.info("communes collectées : %d (départements %s)", len(communes), departements)
    _save("communes", communes)
    return communes


def collect_air(communes: list[dict], days: int, limit: int) -> None:
    # On limite aux N communes les plus peuplées pour rester raisonnable sur l'API gratuite.
    top = sorted([c for c in communes if c.get("centre")], key=lambda c: c.get("population", 0), reverse=True)[:limit]
    results = []
    for c in top:
        lon, lat = c["centre"]["coordinates"]
        try:
            resp = http_get(
                AIR_API,
                params={"latitude": lat, "longitude": lon, "hourly": AIR_VARS, "past_days": days, "forecast_days": 0},
            )
            results.append({"code_insee": c["code"], "nom": c["nom"], "data": resp.json()})
        except requests.RequestException:
            log.error("commune ignorée après échecs : %s", c["code"])
    log.info("séries qualité de l'air collectées : %d/%d", len(results), len(top))
    _save("air", results)


def collect_stations(csv_path: str | None) -> None:
    src = Path(csv_path) if csv_path else SAMPLES_DIR / "stations.csv"
    if not src.exists():
        log.error("fichier stations introuvable : %s", src)
        return
    out_dir = RAW_DIR / "stations"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"stations_{_stamp()}.csv"
    shutil.copy(src, dest)
    log.info("source=stations fichier=%s", dest.relative_to(ROOT))


def parse_episodes(html: str) -> list[dict]:
    """Extraction des épisodes depuis un tableau HTML (date | zone | polluant | niveau).

    Adapter les sélecteurs à la page réellement scrapée ; la fonction est isolée pour être testée.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("table tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) >= 4:
            rows.append({"date": cells[0], "zone": cells[1], "polluant": cells[2], "niveau": cells[3]})
    return rows


def collect_episodes() -> None:
    if EPISODES_URL:
        html = http_get(EPISODES_URL).text
    else:
        log.warning("EPISODES_URL non défini : utilisation de la page exemple data/samples/episodes.html")
        html = (SAMPLES_DIR / "episodes.html").read_text(encoding="utf-8")
    episodes = parse_episodes(html)
    log.info("épisodes extraits : %d", len(episodes))
    _save("episodes", episodes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collecte AirData Hub")
    parser.add_argument("--source", choices=["all", "communes", "air", "stations", "episodes"], default="all")
    parser.add_argument("--departement", default=os.getenv("DEPARTEMENT", "75,92,93,94"), help="un ou plusieurs codes séparés par des virgules")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=20, help="nombre de communes (les plus peuplées) pour les mesures d air")
    parser.add_argument("--stations-csv", default=None)
    args = parser.parse_args(argv)

    log.info("=== début collecte source=%s ===", args.source)
    failed: list[str] = []

    def run(name: str, fn, *fn_args):
        """Chaque source est isolée : l'échec de l'une n'empêche pas les autres."""
        try:
            return fn(*fn_args)
        except Exception as exc:  # journalisé, puis code retour != 0 exploitable en CI / cron
            log.error("source %s en échec : %s", name, exc)
            failed.append(name)
            return None

    if args.source in ("all", "communes", "air"):
        communes = run("communes", collect_communes, args.departement)
        if communes and args.source in ("all", "air"):
            run("air", collect_air, communes, args.days, args.limit)
    if args.source in ("all", "stations"):
        run("stations", collect_stations, args.stations_csv)
    if args.source in ("all", "episodes"):
        run("episodes", collect_episodes)

    log.info("=== fin collecte (sources en échec : %s) ===", ", ".join(failed) or "aucune")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
