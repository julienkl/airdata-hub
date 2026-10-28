"""Bonus - Tests du client de l'interface : authentification, pagination, messages d'erreur.
Les appels HTTP sont simulés ; un test de bout en bout passe aussi par la vraie API (TestClient)."""
from unittest.mock import MagicMock

import pytest
import requests

from app.client import AirDataClient, ApiError


def _rep(status=200, json=None):
    return MagicMock(status_code=status, json=lambda: json)


def test_login_stocke_le_jeton_et_l_envoie_ensuite():
    s = MagicMock()
    s.request.side_effect = [_rep(json={"access_token": "abc"}), _rep(json=[])]
    c = AirDataClient("http://api", session=s)
    assert c.login("u", "p") == "abc"
    c.communes()
    assert s.request.call_args.kwargs["headers"] == {"Authorization": "Bearer abc"}


def test_pagination_des_mesures():
    s = MagicMock()
    s.request.side_effect = [_rep(json={"total": 1500, "limit": 1000, "offset": 0, "items": [{"i": 1}] * 1000}),
                             _rep(json={"total": 1500, "limit": 1000, "offset": 1000, "items": [{"i": 2}] * 500})]
    items = AirDataClient(token="t", session=s).mesures("75056", "2026-01-01T00:00:00")
    assert len(items) == 1500
    assert s.request.call_args.kwargs["params"]["offset"] == 1000
    assert s.request.call_args.kwargs["params"]["from"] == "2026-01-01T00:00:00"


@pytest.mark.parametrize("status,msg", [(401, "reconnectez"), (403, "droits"), (404, "introuvable"),
                                        (422, "Paramètres"), (500, "code 500")])
def test_erreurs_http_traduites(status, msg):
    s = MagicMock()
    s.request.return_value = _rep(status=status)
    with pytest.raises(ApiError, match=msg):
        AirDataClient(token="t", session=s).moyennes()


@pytest.mark.parametrize("exc,msg", [(requests.Timeout(), "trop de temps"), (requests.ConnectionError(), "joindre")])
def test_erreurs_reseau(exc, msg):
    s = MagicMock()
    s.request.side_effect = exc
    with pytest.raises(ApiError, match=msg):
        AirDataClient(session=s).episodes()


def test_de_bout_en_bout_avec_la_vraie_api():
    """Le client parle à l'API réelle (base de test) via le TestClient de FastAPI."""
    from fastapi.testclient import TestClient

    from api.main import app
    from src.db.import_data import create_user
    from src.db.models import init_db

    init_db()
    create_user("ui-tester", "mdp-ui-123")
    with TestClient(app) as tc:
        c = AirDataClient("http://testserver", session=tc)
        with pytest.raises(ApiError, match="reconnectez"):
            c.login("ui-tester", "mauvais")
        c.login("ui-tester", "mdp-ui-123")
        assert isinstance(c.communes(), list)
        assert isinstance(c.moyennes(5), list)
