"""Client de l'API AirData Hub utilisé par l'interface Streamlit (bonus).

Toute la logique d'appel (authentification, pagination, messages d'erreur) est ici, et non dans l'interface :
elle est ainsi testable sans navigateur (tests/test_app_client.py).
"""
from __future__ import annotations

import os

import requests

API_URL = os.getenv("AIRDATA_API_URL", "http://localhost:8000")
MESSAGES = {
    401: "Session expirée ou identifiants incorrects : reconnectez-vous.",
    403: "Votre compte n'a pas les droits pour cette action.",
    404: "Donnée introuvable.",
    422: "Paramètres refusés par l'API (format de date, code INSEE…).",
}


class ApiError(Exception):
    """Erreur présentable à l'utilisateur (message en français, sans détail technique)."""


class AirDataClient:
    def __init__(self, base_url: str = API_URL, token: str | None = None, session: requests.Session | None = None,
                 timeout: float = 10):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = session or requests.Session()
        self.timeout = timeout

    def _call(self, method: str, path: str, **kwargs):
        if self.token:
            kwargs.setdefault("headers", {})["Authorization"] = f"Bearer {self.token}"
        try:
            r = self.session.request(method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
        except requests.Timeout:
            raise ApiError("L'API met trop de temps à répondre. Réessayez dans un instant.")
        except requests.ConnectionError:
            raise ApiError(f"Impossible de joindre l'API ({self.base_url}). Est-elle démarrée ?")
        if r.status_code >= 400:
            raise ApiError(MESSAGES.get(r.status_code, f"Erreur de l'API (code {r.status_code})."))
        return r.json()

    def login(self, username: str, password: str) -> str:
        data = self._call("POST", "/auth/token", data={"username": username, "password": password})
        self.token = data["access_token"]
        return self.token

    def communes(self, q: str | None = None) -> list[dict]:
        return self._call("GET", "/communes", params={"q": q} if q else None)

    def moyennes(self, top: int = 10) -> list[dict]:
        return self._call("GET", "/stats/moyennes", params={"top": top})

    def episodes(self, polluant: str | None = None) -> list[dict]:
        return self._call("GET", "/episodes", params={"polluant": polluant} if polluant else None)

    def mesures(self, commune: str, date_from: str | None = None, date_to: str | None = None,
                max_items: int = 5000) -> list[dict]:
        """Récupère toutes les mesures d'une commune en suivant la pagination de l'API (1 000 par page)."""
        params = {"commune": commune, "limit": 1000, "offset": 0}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        items: list[dict] = []
        while len(items) < max_items:
            page = self._call("GET", "/mesures", params=dict(params))
            items.extend(page["items"])
            params["offset"] += page["limit"]
            if params["offset"] >= page["total"] or not page["items"]:
                break
        return items[:max_items]
