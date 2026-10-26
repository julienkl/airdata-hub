"""C4 - Import des données nettoyées dans la base.

Usage :
    python -m src.db.import_data            # importe data/processed/*.csv
    python -m src.db.import_data --create-user admin --password '***'
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.models import ApiUser, Commune, Episode, Mesure, SessionLocal, engine, init_db
from src.security import hash_password

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
log = logging.getLogger("import")


def _upsert(session, model, rows: list[dict], keys: list[str]) -> None:
    if not rows:
        return
    insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    stmt = insert(model).values(rows).on_conflict_do_nothing(index_elements=keys)
    session.execute(stmt)


def import_all() -> dict:
    init_db()
    counts = {}
    with SessionLocal() as s:
        if (f := PROCESSED / "communes.csv").exists():
            df = pd.read_csv(f, dtype={"code_insee": str, "code_postal": str})
            rows = df.where(pd.notna(df), None).to_dict("records")
            _upsert(s, Commune, rows, ["code_insee"])
            counts["commune"] = len(rows)
        if (f := PROCESSED / "mesures.csv").exists():
            df = pd.read_csv(f, dtype={"code_insee": str}, parse_dates=["horodatage"])
            df = df[["code_insee", "horodatage", "pm25", "pm10", "no2", "o3"]]
            rows = df.astype(object).where(pd.notna(df), None).to_dict("records")
            for i in range(0, len(rows), 5000):
                _upsert(s, Mesure, rows[i : i + 5000], ["code_insee", "horodatage"])
            counts["mesure"] = len(rows)
        if (f := PROCESSED / "episodes.csv").exists():
            df = pd.read_csv(f, parse_dates=["date"])
            df["date"] = df["date"].dt.date
            s.query(Episode).delete()
            s.add_all(Episode(**r) for r in df.to_dict("records"))
            counts["episode"] = len(df)
        s.commit()
    log.info("import terminé : %s", counts)
    return counts


def create_user(username: str, password: str, role: str = "reader") -> None:
    init_db()
    with SessionLocal() as s:
        s.merge(ApiUser(username=username, password_hash=hash_password(password), role=role))
        s.commit()
    log.info("utilisateur API créé : %s (%s)", username, role)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--create-user")
    p.add_argument("--password")
    p.add_argument("--role", default="reader", choices=["reader", "admin"])
    a = p.parse_args()
    if a.create_user:
        create_user(a.create_user, a.password, a.role)
    else:
        import_all()
