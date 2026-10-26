"""C4/C5 - Tests de la base, de la purge RGPD et de l'API (authentification, routes, validation)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.db.import_data import create_user
from src.db.models import Abonne, Commune, Episode, Mesure, SessionLocal, init_db
from src.db.purge_rgpd import purge


@pytest.fixture(scope="module", autouse=True)
def seed():
    init_db()
    create_user("tester", "s3cret!")
    with SessionLocal() as s:
        s.merge(Commune(code_insee="75056", nom="Paris", code_postal="75001", population=2100000, lat=48.85, lon=2.35))
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        s.add_all(Mesure(code_insee="75056", horodatage=t0 + timedelta(hours=h), pm25=10 + h, no2=30.0) for h in range(5))
        s.add(Episode(date=t0.date(), zone="Paris", polluant="PM10", niveau="alerte"))
        s.commit()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def token(client):
    r = client.post("/auth/token", data={"username": "tester", "password": "s3cret!"})
    assert r.status_code == 200
    return r.json()["access_token"]


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_route_protegee_sans_jeton_401(client):
    assert client.get("/communes").status_code == 401


def test_mauvais_mot_de_passe_401(client):
    assert client.post("/auth/token", data={"username": "tester", "password": "faux"}).status_code == 401


def test_jeton_falsifie_401(client):
    assert client.get("/communes", headers=auth("abc.def.ghi")).status_code == 401


def test_communes(client, token):
    r = client.get("/communes", headers=auth(token))
    assert r.status_code == 200
    assert r.json()[0]["nom"] == "Paris"


def test_mesures_pagination(client, token):
    r = client.get("/mesures", params={"commune": "75056", "limit": 2}, headers=auth(token))
    body = r.json()
    assert r.status_code == 200
    assert body["total"] == 5 and len(body["items"]) == 2


def test_mesures_validation_code_insee(client, token):
    assert client.get("/mesures", params={"commune": "75"}, headers=auth(token)).status_code == 422


def test_stats_moyennes(client, token):
    r = client.get("/stats/moyennes", headers=auth(token))
    assert r.json()[0]["pm25_moy"] == 12.0


def test_episodes_filtre(client, token):
    assert len(client.get("/episodes", params={"polluant": "pm10"}, headers=auth(token)).json()) == 1


def test_openapi_documente(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/communes", "/mesures", "/auth/token"} <= set(paths)


def test_purge_rgpd():
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        s.add_all([
            Abonne(email="ok@example.org", code_insee="75056", consentement=True, date_consentement=now, derniere_activite=now),
            Abonne(email="nocons@example.org", code_insee="75056", consentement=False, derniere_activite=now),
            Abonne(email="old@example.org", code_insee="75056", consentement=True, derniere_activite=now - timedelta(days=800)),
        ])
        s.commit()
    assert purge(dry_run=True) == 2
    assert purge() == 2
    with SessionLocal() as s:
        assert [a.email for a in s.query(Abonne).all()] == ["ok@example.org"]
