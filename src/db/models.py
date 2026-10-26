"""C4 - Modèle physique de données (MPD) en SQLAlchemy.

Le MCD/MPD correspondant est décrit dans docs/mcd.md.
La table `abonne` contient des données personnelles : voir docs/registre_rgpd.md.
"""
from __future__ import annotations

import os
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./airdata.db")


class Base(DeclarativeBase):
    pass


class Commune(Base):
    __tablename__ = "commune"
    code_insee: Mapped[str] = mapped_column(String(5), primary_key=True)
    nom: Mapped[str] = mapped_column(String(120), index=True)
    code_postal: Mapped[str | None] = mapped_column(String(5))
    population: Mapped[int] = mapped_column(Integer, default=0)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    mesures: Mapped[list["Mesure"]] = relationship(back_populates="commune")


class Mesure(Base):
    __tablename__ = "mesure"
    __table_args__ = (UniqueConstraint("code_insee", "horodatage", name="uq_mesure_commune_heure"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_insee: Mapped[str] = mapped_column(ForeignKey("commune.code_insee"), index=True)
    horodatage: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    pm25: Mapped[float | None] = mapped_column(Float)
    pm10: Mapped[float | None] = mapped_column(Float)
    no2: Mapped[float | None] = mapped_column(Float)
    o3: Mapped[float | None] = mapped_column(Float)
    commune: Mapped[Commune] = relationship(back_populates="mesures")


class Episode(Base):
    __tablename__ = "episode"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    zone: Mapped[str] = mapped_column(String(120))
    polluant: Mapped[str] = mapped_column(String(10))
    niveau: Mapped[str] = mapped_column(String(30))


class Abonne(Base):
    """Données personnelles : email + commune suivie. Base légale : consentement."""

    __tablename__ = "abonne"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    code_insee: Mapped[str] = mapped_column(ForeignKey("commune.code_insee"))
    consentement: Mapped[bool] = mapped_column(Boolean, default=False)
    date_consentement: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    derniere_activite: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiUser(Base):
    """Comptes techniques autorisés à appeler l'API (mot de passe haché, jamais en clair)."""

    __tablename__ = "api_user"
    username: Mapped[str] = mapped_column(String(50), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="reader")


engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
