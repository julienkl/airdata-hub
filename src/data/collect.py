"""C1 - Collecte automatisée multi-sources.

Usage :
    python -m src.data.collect --source all
    python -m src.data.collect --source communes --departement 75,92,93,94
    python -m src.data.collect --source air --days 7
    python -m src.data.collect --source episodes --annees 2025,2026

Sources (toutes réelles) :
    communes  -> API REST geo.api.gouv.fr (référentiel des communes, INSEE)          Licence Ouverte Etalab
    air       -> API REST Open-Meteo Air Quality (PM2.5, PM10, NO2, O3 horaires)    CC BY 4.0
    stations  -> fichier CSV Airparif « mes_idf_horaire_pm10 » (mesures aux stations)  ODbL, source : Airparif
                 URL à renseigner dans STATIONS_CSV_URL (lien « Télécharger CSV » du portail open data Airparif)
    episodes  -> scraping de la page publique Airparif « Historique des épisodes de pollution »
                 Le robots.txt du site est vérifié automatiquement avant chaque requête.

Chaque source écrit ses fichiers bruts horodatés dans data/raw/<source>/ et journalise dans logs/collect.log.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
LOG_DIR = ROOT / "logs"

GEO_API = "https://geo.api.gouv.fr/communes"
AIR_API = "https://air-quality-api.open-meteo.com/v1/air-quality"
AIR_VARS = "pm2_5,pm10,nitrogen_dioxide,ozone"
EPISODES_URL = os.getenv("EPISODES_URL", "https://www.airparif.fr/historique-des-episodes-de-pollution")
STATIONS_CSV_URL = os.getenv("STATIONS_CSV_URL", "")
SCRAPING_DELAY_S = 2.0  # politesse : pause entre deux pages scrapées

USER_AGENT = "AirDataHub/0.1 (projet pedagogique RNCP Developpeur IA)"

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "collect.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("collect")


class SourceNonConfiguree(RuntimeError):
    pass


class ScrapingInterdit(RuntimeError):
    pass


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save(source: str, payload, ext: str = "json", suffix: str = "") -> Path:
    out_dir = RAW_DIR / source
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{source}{suffix}_{_stamp()}.{ext}"
    if ext == "json":
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    elif isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")
    log.info("source=%s fichier=%s", source, path.relative_to(ROOT))
    return path


def http_get(url: str, params: dict | None = None, retries: int = 3, backoff: float = 2.0) -> requests.Response:
    """GET avec retries exponentiels : la gestion d'erreurs fait partie de la preuve C1."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=30, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            log.warning("échec %s (tentative %d/%d) : %s", url, attempt, retries, exc)
            if attempt == retries:
                raise
            time.sleep(backoff ** attempt)
    raise RuntimeError("inatteignable")


# ---------------------------------------------------------------- API : communes
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


# ---------------------------------------------------------------- API : qualité de l'air
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


# ---------------------------------------------------------------- Fichier : stations Airparif
def collect_stations(url_or_path: str | None) -> None:
    """Télécharge le fichier CSV Airparif des mesures aux stations (ou copie un fichier local déjà téléchargé)."""
    src = url_or_path or STATIONS_CSV_URL
    if not src:
        raise SourceNonConfiguree(
            "STATIONS_CSV_URL non défini : renseigner dans .env le lien CSV du jeu « mes idf horaire pm10 » "
            "du portail open data Airparif (voir README)"
        )
    if src.startswith(("http://", "https://")):
        content = http_get(src).content
        log.info("fichier stations téléchargé : %d octets depuis %s", len(content), urlparse(src).netloc)
    else:
        content = Path(src).read_bytes()
        log.info("fichier stations lu localement : %s", src)
    if not content.strip():
        raise ValueError("fichier stations vide")
    _save("stations", content, ext="csv")


# ---------------------------------------------------------------- Scraping : épisodes Airparif
def robots_autorise(url: str) -> bool:
    """Vérifie dans le robots.txt du site que l'URL peut être consultée par un robot."""
    racine = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    rp = RobotFileParser()
    try:
        resp = requests.get(urljoin(racine, "/robots.txt"), timeout=15, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        log.error("robots.txt injoignable (%s) : par prudence, pas de scraping", exc)
        return False
    if resp.status_code == 404:
        return True  # pas de robots.txt : aucune restriction déclarée
    if resp.status_code >= 400:
        log.error("robots.txt renvoie %s : par prudence, pas de scraping", resp.status_code)
        return False
    rp.parse(resp.text.splitlines())
    return rp.can_fetch(USER_AGENT, url)


_DATE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
_POLLUANT = re.compile(r"\b(PM\s?10|PM\s?2[.,]?5|NO2|O3|SO2)\b", re.IGNORECASE)


def _coche(td) -> bool:
    """Une case de critère est « cochée » si elle contient une icône ou du texte."""
    return bool(td.get_text(strip=True)) or td.find(["img", "svg", "i", "span"]) is not None


def parse_episodes(html: str, base_url: str = EPISODES_URL) -> list[dict]:
    """Extrait les lignes du tableau « Historique des épisodes de pollution » d'Airparif.

    Colonnes attendues : Level | Polluant | Date | critère population (>10 % d'un département) |
    critère surface (>100 km² en Île-de-France) | Détails.
    L'extraction s'appuie sur le contenu (formats de date et de polluant) plutôt que sur des classes CSS,
    pour résister aux changements de mise en forme du site.
    """
    soup = BeautifulSoup(html, "html.parser")
    episodes = []
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue  # lignes d'en-tête
        texte = " ".join(td.get_text(" ", strip=True) for td in tds)
        date, polluant = _DATE.search(texte), _POLLUANT.search(texte)
        if not (date and polluant):
            continue
        lien = tr.find("a", href=True)
        episodes.append({
            "niveau": tds[0].get_text(" ", strip=True),
            "polluant": polluant.group(1),
            "date": date.group(1),
            "critere_population": _coche(tds[3]) if len(tds) > 3 else None,
            "critere_surface": _coche(tds[4]) if len(tds) > 4 else None,
            "lien": urljoin(base_url, lien["href"]) if lien else None,
        })
    return episodes


def collect_episodes(annees: list[int]) -> None:
    if not robots_autorise(EPISODES_URL):
        raise ScrapingInterdit(f"le robots.txt n'autorise pas {EPISODES_URL}")
    log.info("robots.txt vérifié : scraping autorisé pour %s", EPISODES_URL)
    tous = []
    for i, annee in enumerate(annees):
        if i:
            time.sleep(SCRAPING_DELAY_S)
        resp = http_get(EPISODES_URL, params={"year": annee})
        _save("episodes", resp.text, ext="html", suffix=f"_{annee}")  # page brute conservée (traçabilité)
        lignes = parse_episodes(resp.text)
        for ligne in lignes:
            ligne["annee_page"] = annee
        log.info("épisodes extraits pour %d : %d", annee, len(lignes))
        tous.extend(lignes)
    if not tous:
        log.warning("aucun épisode extrait : vérifier que la structure de la page n'a pas changé")
    _save("episodes", tous)


# ---------------------------------------------------------------- point d'entrée
def main(argv: list[str] | None = None) -> int:
    annee = datetime.now().year
    parser = argparse.ArgumentParser(description="Collecte AirData Hub")
    parser.add_argument("--source", choices=["all", "communes", "air", "stations", "episodes"], default="all")
    parser.add_argument("--departement", default=os.getenv("DEPARTEMENT", "75,92,93,94"),
                        help="un ou plusieurs codes séparés par des virgules")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=20, help="nombre de communes (les plus peuplées) pour les mesures d'air")
    parser.add_argument("--stations-csv", default=None, help="URL ou chemin local du CSV stations (sinon STATIONS_CSV_URL)")
    parser.add_argument("--annees", default=f"{annee - 1},{annee}", help="années d'épisodes à scraper, ex. 2025,2026")
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
        run("episodes", collect_episodes, [int(a) for a in args.annees.split(",") if a.strip()])

    log.info("=== fin collecte (sources en échec : %s) ===", ", ".join(failed) or "aucune")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
