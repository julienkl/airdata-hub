"""C4 - Traitement RGPD : purge des données personnelles en fin de durée de conservation.

Règles (voir docs/registre_rgpd.md) :
- abonné sans consentement            -> suppression immédiate
- abonné inactif depuis > 24 mois     -> suppression

Usage : python -m src.db.purge_rgpd [--dry-run]
À planifier (cron / GitHub Actions schedule) une fois par jour.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from src.db.models import Abonne, SessionLocal, init_db

RETENTION_DAYS = 730
log = logging.getLogger("purge_rgpd")


def purge(dry_run: bool = False, now: datetime | None = None) -> int:
    init_db()
    now = now or datetime.now(timezone.utc)
    limit = now - timedelta(days=RETENTION_DAYS)
    with SessionLocal() as s:
        q = s.query(Abonne).filter(or_(Abonne.consentement.is_(False), Abonne.derniere_activite < limit))
        n = q.count()
        if not dry_run:
            q.delete(synchronize_session=False)
            s.commit()
    log.info("abonnés purgés : %d (dry_run=%s)", n, dry_run)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    purge(p.parse_args().dry_run)
