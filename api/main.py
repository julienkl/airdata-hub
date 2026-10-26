"""C5 - API REST de mise à disposition des données (FastAPI).

Lancer : uvicorn api.main:app --reload
Documentation OpenAPI : http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt import PyJWTError
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import ApiUser, Commune, Episode, Mesure, SessionLocal, init_db
from src.security import create_token, decode_token, verify_password

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="AirData Hub API",
    version="0.1.0",
    description="Données de qualité de l'air par commune. Authentification JWT (bouton **Authorize**).",
)
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token")


# ---------- dépendances ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


def current_user(token: Annotated[str, Depends(oauth2)]) -> dict:
    try:
        return decode_token(token)
    except PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré", {"WWW-Authenticate": "Bearer"})


User = Annotated[dict, Depends(current_user)]


# ---------- schémas ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CommuneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code_insee: str
    nom: str
    code_postal: str | None
    population: int
    lat: float | None
    lon: float | None


class MesureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code_insee: str
    horodatage: datetime
    pm25: float | None
    pm10: float | None
    no2: float | None
    o3: float | None


class MoyenneOut(BaseModel):
    code_insee: str
    nom: str
    pm25_moy: float | None
    no2_moy: float | None
    nb_mesures: int


class EpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date: date
    zone: str
    polluant: str
    niveau: str


class Page(BaseModel):
    total: int
    limit: int
    offset: int


class MesuresPage(Page):
    items: list[MesureOut]


# ---------- routes ----------
@app.get("/health", tags=["système"])
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/token", response_model=Token, tags=["auth"])
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB) -> Token:
    user = db.get(ApiUser, form.username)
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants incorrects")
    return Token(access_token=create_token(user.username, user.role))


@app.get("/communes", response_model=list[CommuneOut], tags=["données"])
def list_communes(db: DB, _: User, q: str | None = Query(None, description="filtre sur le nom")) -> list[Commune]:
    stmt = select(Commune).order_by(Commune.population.desc())
    if q:
        stmt = stmt.where(Commune.nom.ilike(f"%{q}%"))
    return list(db.scalars(stmt))


@app.get("/communes/{code_insee}", response_model=CommuneOut, tags=["données"])
def get_commune(code_insee: str, db: DB, _: User) -> Commune:
    c = db.get(Commune, code_insee)
    if not c:
        raise HTTPException(404, "Commune inconnue")
    return c


@app.get("/mesures", response_model=MesuresPage, tags=["données"])
def list_mesures(
    db: DB,
    _: User,
    commune: str = Query(..., description="code INSEE", min_length=5, max_length=5),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> MesuresPage:
    stmt = select(Mesure).where(Mesure.code_insee == commune)
    if date_from:
        stmt = stmt.where(Mesure.horodatage >= date_from)
    if date_to:
        stmt = stmt.where(Mesure.horodatage <= date_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Mesure.horodatage).limit(limit).offset(offset)).all()
    return MesuresPage(total=total or 0, limit=limit, offset=offset, items=items)


@app.get("/stats/moyennes", response_model=list[MoyenneOut], tags=["indicateurs"])
def moyennes(db: DB, _: User, top: int = Query(10, ge=1, le=100)) -> list[MoyenneOut]:
    stmt = (
        select(
            Commune.code_insee,
            Commune.nom,
            func.avg(Mesure.pm25),
            func.avg(Mesure.no2),
            func.count(Mesure.id),
        )
        .join(Mesure, Mesure.code_insee == Commune.code_insee)
        .group_by(Commune.code_insee, Commune.nom)
        .order_by(func.avg(Mesure.pm25).desc())
        .limit(top)
    )
    return [
        MoyenneOut(code_insee=c, nom=n, pm25_moy=round(p, 2) if p else None, no2_moy=round(x, 2) if x else None, nb_mesures=k)
        for c, n, p, x, k in db.execute(stmt)
    ]


@app.get("/episodes", response_model=list[EpisodeOut], tags=["données"])
def list_episodes(db: DB, _: User, polluant: str | None = None) -> list[Episode]:
    stmt = select(Episode).order_by(Episode.date.desc())
    if polluant:
        stmt = stmt.where(Episode.polluant == polluant.upper())
    return list(db.scalars(stmt))
