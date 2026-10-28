"""Interface de consultation AirData Hub (bonus) : consomme l'API REST, jamais la base directement.

Lancer (API démarrée sur le port 8000) :
    pip install -r app/requirements.txt
    python -m streamlit run app/streamlit_app.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.client import AirDataClient, ApiError  # noqa: E402

# Valeurs guides journalières de l'OMS (lignes directrices 2021), en µg/m³.
OMS_24H = {"pm25": 15, "pm10": 45, "no2": 25}
LIBELLES = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO2", "o3": "O3"}

st.set_page_config(page_title="AirData Hub", page_icon="🌫️", layout="wide")
st.title("AirData Hub — qualité de l'air en Île-de-France")
st.caption("Données Open-Meteo (CAMS), Airparif et geo.api.gouv.fr, servies par l'API AirData Hub.")


# ---------- connexion ----------
with st.sidebar:
    st.header("Connexion")
    if "token" not in st.session_state:
        with st.form("login"):
            user = st.text_input("Identifiant")
            pwd = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Se connecter"):
                try:
                    st.session_state.token = AirDataClient().login(user, pwd)
                    st.rerun()
                except ApiError as exc:
                    st.error(str(exc))
        st.info("L'API exige un jeton JWT : l'interface n'a pas d'accès direct à la base.")
        st.stop()
    st.success("Connecté")
    if st.button("Se déconnecter"):
        del st.session_state.token
        st.rerun()

api = AirDataClient(token=st.session_state.token)


def appel(fonction, *args, **kwargs):
    """Affiche l'erreur à l'utilisateur ; si le jeton a expiré, renvoie vers la connexion."""
    try:
        return fonction(*args, **kwargs)
    except ApiError as exc:
        st.error(f"⚠️ {exc}")
        if "reconnectez" in str(exc):
            st.session_state.pop("token", None)
        st.stop()


communes = pd.DataFrame(appel(api.communes))
if communes.empty:
    st.warning("Aucune commune en base : lancez la collecte puis l'import (voir README).")
    st.stop()

onglet_classement, onglet_commune, onglet_carte, onglet_episodes = st.tabs(
    ["🏆 Classement", "📈 Évolution par commune", "🗺️ Carte", "🚨 Épisodes de pollution"])

# ---------- classement ----------
with onglet_classement:
    top = st.slider("Nombre de communes", 5, 50, 10)
    moy = pd.DataFrame(appel(api.moyennes, top))
    if moy.empty:
        st.info("Pas encore de mesures en base.")
    else:
        st.subheader("Communes les plus exposées aux particules fines (PM2.5 moyen)")
        st.bar_chart(moy, x="nom", y="pm25_moy", x_label="Commune", y_label="PM2.5 moyen (µg/m³)",
                     horizontal=True, sort="-pm25_moy")
        st.dataframe(moy.rename(columns={"nom": "Commune", "pm25_moy": "PM2.5 moyen (µg/m³)",
                                         "no2_moy": "NO2 moyen (µg/m³)", "nb_mesures": "Nb de mesures",
                                         "code_insee": "Code INSEE"}),
                     hide_index=True, width="stretch")

# ---------- évolution ----------
with onglet_commune:
    col1, col2 = st.columns([2, 1])
    noms = dict(zip(communes["nom"] + " (" + communes["code_insee"] + ")", communes["code_insee"]))
    choix = col1.selectbox("Commune", list(noms))
    periode = col2.date_input("Période", (date.today() - timedelta(days=30), date.today()))
    if isinstance(periode, tuple) and len(periode) == 2:
        debut, fin = periode
        mes = pd.DataFrame(appel(api.mesures, noms[choix], f"{debut}T00:00:00", f"{fin}T23:59:59"))
        if mes.empty:
            st.info("Aucune mesure sur cette période pour cette commune.")
        else:
            mes["horodatage"] = pd.to_datetime(mes["horodatage"], utc=True)
            jour = mes.set_index("horodatage")[list(LIBELLES)].resample("D").mean().round(1)
            polluants = st.multiselect("Polluants", list(LIBELLES), default=["pm25", "no2"],
                                       format_func=LIBELLES.get)
            if polluants:
                st.line_chart(jour[polluants].rename(columns=LIBELLES), y_label="Moyenne journalière (µg/m³)")
            # Information donnée en texte et pas seulement par la couleur (accessibilité).
            cols = st.columns(len(OMS_24H))
            for c, (pol, seuil) in zip(cols, OMS_24H.items()):
                n = int((jour[pol] > seuil).sum())
                c.metric(f"Jours au-dessus du seuil OMS {LIBELLES[pol]} ({seuil} µg/m³)", f"{n} / {len(jour)}")
            st.caption(f"{len(mes)} mesures horaires. Seuils : valeurs guides journalières de l'OMS (2021).")

# ---------- carte ----------
with onglet_carte:
    geo = communes.dropna(subset=["lat", "lon"])
    st.map(geo, latitude="lat", longitude="lon")
    st.caption(f"{len(geo)} communes géolocalisées sur {len(communes)}.")

# ---------- épisodes ----------
with onglet_episodes:
    polluant = st.selectbox("Polluant", ["Tous", "PM10", "PM2.5", "NO2", "O3"])
    epi = pd.DataFrame(appel(api.episodes, None if polluant == "Tous" else polluant))
    if epi.empty:
        st.info("Aucun épisode enregistré pour ce filtre.")
    else:
        st.metric("Épisodes enregistrés", len(epi))
        st.dataframe(epi.rename(columns={"date": "Date", "zone": "Zone", "polluant": "Polluant", "niveau": "Niveau"}),
                     hide_index=True, width="stretch")
