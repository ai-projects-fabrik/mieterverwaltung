"""Akzeptanztest (spec-first) fuer projekt.googleauth (Ziel `mv-googleauth`)."""

import base64
import hashlib
import importlib.util
import json
from urllib.parse import parse_qs, urlsplit

import pytest

if importlib.util.find_spec("projekt.googleauth") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.googleauth import (  # noqa: E402
    SCOPE,
    anmelde_url,
    code_aus_redirect,
    lade_client,
    lade_token,
    neues_pkce,
    speichere_token,
    token_anfrage_code,
    token_anfrage_refresh,
    token_aus_antwort,
    token_gueltig,
    token_pfad,
)

CLIENT_JSON = json.dumps(
    {"installed": {"client_id": "cid.apps.example", "client_secret": "geheim", "project_id": "p"}}
)
REDIRECT = "http://127.0.0.1:50123/"


def client():
    return lade_client(CLIENT_JSON)


def test_scope_ist_nur_lesen():
    assert SCOPE == "https://www.googleapis.com/auth/drive.readonly"


def test_client_aus_google_datei():
    assert client() == {
        "client_id": "cid.apps.example",
        "client_secret": "geheim",
        "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    eigene = json.dumps(
        {
            "installed": {
                "client_id": "a",
                "client_secret": "b",
                "auth_uri": "https://auth.example/x",
                "token_uri": "https://tok.example/y",
            }
        }
    )
    assert lade_client(eigene)["token_uri"] == "https://tok.example/y"


@pytest.mark.parametrize(
    ("text", "teil"),
    [
        ("{nicht json", "JSON"),
        ("[]", "installed"),
        (json.dumps({"web": {"client_id": "a", "client_secret": "b"}}), "installed"),
        (json.dumps({"installed": {"client_secret": "b"}}), "client_id"),
        (json.dumps({"installed": {"client_id": "a", "client_secret": " "}}), "client_secret"),
        (
            json.dumps(
                {"installed": {"client_id": "a", "client_secret": "b", "token_uri": "http://x"}}
            ),
            "token_uri",
        ),
    ],
)
def test_client_fehler_nennen_das_feld(text, teil):
    with pytest.raises(ValueError, match=teil):
        lade_client(text)


def test_pkce_s256():
    verifier, challenge = neues_pkce(bytes(range(32)))
    assert verifier == base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode()
    erwartet = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    assert challenge == erwartet.rstrip(b"=").decode()
    assert "=" not in verifier + challenge
    assert 43 <= len(verifier) <= 128
    with pytest.raises(ValueError, match="zufall"):
        neues_pkce(b"kurz")


def test_anmelde_url():
    url = anmelde_url(client(), REDIRECT, "st", "ch")
    teile = urlsplit(url)
    assert f"{teile.scheme}://{teile.netloc}{teile.path}" == client()["auth_uri"]
    q = {k: v[0] for k, v in parse_qs(teile.query).items()}
    assert q == {
        "client_id": "cid.apps.example",
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "state": "st",
        "code_challenge": "ch",
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    assert "localhost" in anmelde_url(client(), "http://localhost:8080/", "s", "c")
    for schlecht in ("https://example.org/", "http://127.0.0.1.evil.org/", ""):
        with pytest.raises(ValueError, match="redirect_uri"):
            anmelde_url(client(), schlecht, "s", "c")
    with pytest.raises(ValueError, match="state"):
        anmelde_url(client(), REDIRECT, "", "c")


def test_code_aus_redirect():
    assert code_aus_redirect("code=4%2Fabc&state=st&scope=x", "st") == "4/abc"
    assert code_aus_redirect("?state=st&code=k", "st") == "k"
    with pytest.raises(ValueError, match="abgelehnt"):
        code_aus_redirect("error=access_denied&state=st", "st")
    with pytest.raises(ValueError, match="state"):
        code_aus_redirect("code=k&state=anderer", "st")
    with pytest.raises(ValueError, match="state"):
        code_aus_redirect("code=k", "st")
    with pytest.raises(ValueError, match="code"):
        code_aus_redirect("state=st", "st")


def test_token_anfragen_sind_formulare():
    url, koerper = token_anfrage_code(client(), "c/1", "ver", REDIRECT)
    assert url == "https://oauth2.googleapis.com/token"
    assert {k: v[0] for k, v in parse_qs(koerper.decode()).items()} == {
        "client_id": "cid.apps.example",
        "client_secret": "geheim",
        "code": "c/1",
        "code_verifier": "ver",
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
    }
    url, koerper = token_anfrage_refresh(client(), "r1")
    assert url == "https://oauth2.googleapis.com/token"
    assert {k: v[0] for k, v in parse_qs(koerper.decode()).items()} == {
        "client_id": "cid.apps.example",
        "client_secret": "geheim",
        "refresh_token": "r1",
        "grant_type": "refresh_token",
    }
    with pytest.raises(ValueError, match="code"):
        token_anfrage_code(client(), "", "v", REDIRECT)
    with pytest.raises(ValueError, match="refresh_token"):
        token_anfrage_refresh(client(), " ")


def test_token_aus_antwort():
    antwort = json.dumps({"access_token": "a1", "refresh_token": "r1", "expires_in": 3599})
    assert token_aus_antwort(antwort.encode(), 1000.0) == {
        "access_token": "a1",
        "refresh_token": "r1",
        "ablauf": 4599.0,
    }
    ohne = json.dumps({"access_token": "a2", "expires_in": 100}).encode()
    assert token_aus_antwort(ohne, 10, {"refresh_token": "r0"}) == {
        "access_token": "a2",
        "refresh_token": "r0",
        "ablauf": 110,
    }
    assert token_aus_antwort(ohne, 0, {"refresh_token": "r0"})["ablauf"] == 100
    with pytest.raises(ValueError, match="refresh_token"):
        token_aus_antwort(ohne, 10)
    fehler = json.dumps({"error": "invalid_grant", "error_description": "Token abgelaufen"})
    with pytest.raises(ValueError, match="invalid_grant"):
        token_aus_antwort(fehler.encode(), 0)
    with pytest.raises(ValueError, match="JSON"):
        token_aus_antwort(b"<html>", 0)
    with pytest.raises(ValueError, match="access_token"):
        token_aus_antwort(b'{"refresh_token": "r"}', 0)
    with pytest.raises(ValueError, match="expires_in"):
        token_aus_antwort(b'{"access_token": "a", "refresh_token": "r", "expires_in": -5}', 0)


def test_token_gueltig_mit_puffer():
    token = {"access_token": "a", "refresh_token": "r", "ablauf": 1000}
    assert token_gueltig(token, 900)
    assert not token_gueltig(token, 940)
    assert token_gueltig(token, 940, puffer=10)
    assert not token_gueltig({"refresh_token": "r", "ablauf": 1000}, 0)
    assert not token_gueltig(None, 0)
    assert not token_gueltig({"access_token": "", "ablauf": 1000}, 0)


def test_token_datei(tmp_path):
    pfad = token_pfad(tmp_path)
    assert pfad == tmp_path / ".mieterverwaltung" / "google_token.json"
    assert lade_token(pfad) == {}
    token = {"access_token": "a", "refresh_token": "r", "ablauf": 5.5}
    speichere_token(pfad, token)
    assert lade_token(pfad) == token
    assert [p.name for p in pfad.parent.iterdir()] == ["google_token.json"]
    speichere_token(pfad, {**token, "access_token": "b"})
    assert lade_token(pfad)["access_token"] == "b"
    with pytest.raises(ValueError, match="refresh_token"):
        speichere_token(pfad, {"access_token": "x"})
    assert lade_token(pfad)["access_token"] == "b"


def test_kaputte_token_datei_ergibt_leer(tmp_path):
    pfad = tmp_path / "t.json"
    for inhalt in ("{kaputt", "[1]", '{"access_token": "a"}'):
        pfad.write_text(inhalt, encoding="utf-8")
        assert lade_token(pfad) == {}
