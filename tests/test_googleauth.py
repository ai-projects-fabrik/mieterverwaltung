"""Tests fuer projekt.googleauth mit synthetischen Zugangsdaten und Dateien."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import projekt.googleauth as googleauth_modul
from projekt.googleauth import (
    SCOPE,
    anmelde_url,
    client_pfad,
    code_aus_redirect,
    lade_client,
    lade_client_datei,
    lade_token,
    neues_pkce,
    speichere_token,
    token_anfrage_code,
    token_anfrage_refresh,
    token_aus_antwort,
    token_gueltig,
    token_pfad,
)

REDIRECT = "http://127.0.0.1:50123/"


def client_text(**installiert):
    daten = {
        "client_id": "cid.apps.example",
        "client_secret": "geheim",
        **installiert,
    }
    return json.dumps({"installed": daten})


def client():
    return lade_client(client_text())


def test_lade_client_trimmt_werte_und_nutzt_google_standardadressen():
    text = client_text(client_id="  cid  ", client_secret="  geheim  ")
    assert lade_client(text) == {
        "client_id": "cid",
        "client_secret": "geheim",
        "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def test_lade_client_uebernimmt_eigene_https_adressen():
    text = client_text(auth_uri="https://auth.example/x", token_uri="https://token.example/y")
    ergebnis = lade_client(text)
    assert ergebnis["auth_uri"] == "https://auth.example/x"
    assert ergebnis["token_uri"] == "https://token.example/y"


@pytest.mark.parametrize(
    ("text", "teil"),
    [
        (None, "Client-Datei"),
        ("[]", "installed"),
        ("{}", "installed"),
        ('{"installed": []}', "installed"),
        (client_text(client_id=""), "client_id"),
        (client_text(client_id=5), "client_id"),
        (client_text(client_secret="   "), "client_secret"),
        (client_text(auth_uri="http://auth.example"), "auth_uri"),
        (client_text(token_uri="ftp://token.example"), "token_uri"),
        (client_text(token_uri=None), "token_uri"),
    ],
)
def test_lade_client_meldet_feld_oder_bereich(text, teil):
    with pytest.raises(ValueError, match=teil):
        lade_client(text)


def test_neues_pkce_akzeptiert_genau_32_und_mehr_bytes():
    for zufall in (bytes(range(32)), bytes(range(64))):
        verifier, challenge = neues_pkce(zufall)
        assert "=" not in verifier + challenge
        assert 43 <= len(verifier) <= 128
        assert challenge


@pytest.mark.parametrize("zufall", [None, "x" * 32, bytearray(range(32)), b"x" * 31])
def test_neues_pkce_lehnt_falsche_oder_zu_kurze_zufallswerte_ab(zufall):
    with pytest.raises(ValueError, match="zufall"):
        neues_pkce(zufall)


def test_anmelde_url_behaelt_vorhandene_parameter():
    daten = lade_client(client_text(auth_uri="https://auth.example/anmelden?mandant=mv"))
    url = anmelde_url(daten, REDIRECT, "state", "challenge")
    teile = urlsplit(url)
    assert teile.path == "/anmelden"
    werte = parse_qs(teile.query)
    assert werte["mandant"] == ["mv"]
    assert werte["scope"] == [SCOPE]
    assert werte["state"] == ["state"]
    assert werte["code_challenge"] == ["challenge"]


@pytest.mark.parametrize(
    ("daten", "teil"),
    [
        (None, "client"),
        ([], "client"),
        ({"client_id": "a", "client_secret": "b"}, "auth_uri"),
        ({"client_secret": "b", "auth_uri": "https://a.example"}, "client_id"),
    ],
)
def test_anmelde_url_braucht_vollstaendige_client_daten(daten, teil):
    with pytest.raises(ValueError, match=teil):
        anmelde_url(daten, REDIRECT, "s", "c")


@pytest.mark.parametrize(
    "redirect",
    ["", "https://localhost:8080/", "http://127.0.0.1.evil.org/", "http://example.org:80/"],
)
def test_anmelde_url_akzeptiert_nur_loopback_redirects(redirect):
    with pytest.raises(ValueError, match="redirect_uri"):
        anmelde_url(client(), redirect, "s", "c")


@pytest.mark.parametrize(("state", "challenge"), [("", "c"), ("s", "  ")])
def test_anmelde_url_braucht_state_und_challenge(state, challenge):
    with pytest.raises(ValueError):
        anmelde_url(client(), REDIRECT, state, challenge)


def test_code_aus_redirect_meldet_fehler_mit_beschreibung():
    with pytest.raises(ValueError, match="abgelehnt.*Zugriff verweigert"):
        code_aus_redirect("error=access_denied&error_description=Zugriff+verweigert&state=s", "s")
    with pytest.raises(ValueError, match="abgelehnt.*unbekannt"):
        code_aus_redirect("error=&state=s", "s")


@pytest.mark.parametrize(
    ("abfrage", "state", "teil"),
    [
        ("code=&state=s", "s", "code"),
        ("code=k", "s", "state"),
        ("code=k&state=anders", "s", "state"),
        ("", "s", "state"),
        ("code=k&state=s", "", "state"),
        (None, "s", "Redirect-Abfrage"),
    ],
)
def test_code_aus_redirect_meldet_fehlende_oder_falsche_werte(abfrage, state, teil):
    with pytest.raises(ValueError, match=teil):
        code_aus_redirect(abfrage, state)


def test_token_anfrage_code_prueft_alle_werte():
    with pytest.raises(ValueError, match="code_verifier"):
        token_anfrage_code(client(), "code", "", REDIRECT)
    with pytest.raises(ValueError, match="redirect_uri"):
        token_anfrage_code(client(), "code", "verifier", "https://example.org/")
    with pytest.raises(ValueError, match="client_id"):
        token_anfrage_code(
            {"client_secret": "b", "token_uri": "https://t.example"}, "c", "v", REDIRECT
        )


def test_token_anfrage_refresh_prueft_client_und_token():
    with pytest.raises(ValueError, match="token_uri"):
        token_anfrage_refresh(
            {"client_id": "a", "client_secret": "b", "token_uri": "http://t.example"}, "r"
        )
    with pytest.raises(ValueError, match="refresh_token"):
        token_anfrage_refresh(client(), "\t")


def test_token_aus_antwort_nutzt_standardablauf_und_entfernt_fremde_felder():
    antwort = json.dumps(
        {"access_token": "a", "refresh_token": "r", "expires_in": 3600, "scope": SCOPE}
    ).encode()
    assert token_aus_antwort(antwort, 5) == {
        "access_token": "a",
        "refresh_token": "r",
        "ablauf": 3605,
    }
    ohne_ablauf = json.dumps({"access_token": "a", "refresh_token": "r"}).encode()
    assert token_aus_antwort(ohne_ablauf, 0)["ablauf"] == 3600


@pytest.mark.parametrize(
    ("antwort", "jetzt", "alt", "teil"),
    [
        (None, 0, None, "bytes"),
        (b"[]", 0, None, "Objekt"),
        (b"\xff", 0, None, "JSON"),
        (b'{"refresh_token": "r"}', 0, None, "access_token"),
        (b'{"access_token": "a", "refresh_token": "r", "expires_in": 0}', 0, None, "expires_in"),
        (
            b'{"access_token": "a", "refresh_token": "r", "expires_in": true}',
            0,
            None,
            "expires_in",
        ),
        (
            b'{"access_token": "a", "refresh_token": "r", "expires_in": "60"}',
            0,
            None,
            "expires_in",
        ),
        (b'{"access_token": "a", "expires_in": 60}', 0, [], "refresh_token"),
        (b'{"access_token": "a", "expires_in": 60}', 0, {"refresh_token": " "}, "refresh_token"),
        (b'{"access_token": "a", "refresh_token": null}', 0, None, "refresh_token"),
        (b'{"access_token": "a", "refresh_token": "r"}', "0", None, "jetzt"),
        (b'{"access_token": "a", "refresh_token": "r"}', True, None, "jetzt"),
    ],
)
def test_token_aus_antwort_meldet_ungueltige_werte(antwort, jetzt, alt, teil):
    with pytest.raises(ValueError, match=teil):
        token_aus_antwort(antwort, jetzt, alt)


def test_token_aus_antwort_meldet_google_fehler():
    antwort = json.dumps(
        {"error": "invalid_client", "error_description": "Client unbekannt"}
    ).encode()
    with pytest.raises(ValueError, match="invalid_client.*Client unbekannt"):
        token_aus_antwort(antwort, 0)
    with pytest.raises(ValueError, match="unbekannt"):
        token_aus_antwort(b'{"error": []}', 0)


def test_token_gueltig_prueft_grenze_und_typen():
    token = {"access_token": "a", "refresh_token": "r", "ablauf": 1000}
    assert token_gueltig(token, 939.999)
    assert not token_gueltig(token, 940)
    assert token_gueltig(token, 940, puffer=0)
    assert token_gueltig(token, 1000, puffer=-1)
    for falsch in (
        [],
        {"refresh_token": "r", "ablauf": 1000},
        {"access_token": True, "ablauf": 1000},
        {"access_token": "a", "ablauf": True},
        {"access_token": "a", "ablauf": "1000"},
    ):
        assert not token_gueltig(falsch, 0)
    assert not token_gueltig(token, "0")
    assert not token_gueltig(token, True)
    assert not token_gueltig(token, 0, puffer=True)


def test_pfade_liegen_unter_dem_benutzerordner(tmp_path):
    assert client_pfad(tmp_path) == tmp_path / ".mieterverwaltung" / "google-client.json"
    assert token_pfad(tmp_path) == tmp_path / ".mieterverwaltung" / "google-token.json"
    assert client_pfad() == Path.home() / ".mieterverwaltung" / "google-client.json"
    assert token_pfad() == Path.home() / ".mieterverwaltung" / "google-token.json"
    with pytest.raises(ValueError, match="home"):
        client_pfad(5)
    with pytest.raises(ValueError, match="home"):
        token_pfad(5)


def test_lade_client_datei_liest_gueltige_datei(tmp_path):
    pfad = tmp_path / "google-client.json"
    pfad.write_text(client_text(), encoding="utf-8")
    assert lade_client_datei(pfad) == client()


def test_lade_client_datei_meldet_fehlende_kaputte_und_nicht_lesbare_datei(tmp_path):
    fehlt = tmp_path / "fehlt" / "google-client.json"
    with pytest.raises(ValueError, match="google-client.json.*fehlt"):
        lade_client_datei(fehlt)

    kaputt = tmp_path / "kaputt.json"
    kaputt.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="google-client.json"):
        lade_client_datei(kaputt)

    ordner = tmp_path / "ordner.json"
    ordner.mkdir()
    with pytest.raises(ValueError, match="google-client.json"):
        lade_client_datei(ordner)


def test_lade_token_akzeptiert_nur_objekt_mit_refresh_token(tmp_path):
    pfad = tmp_path / "token.json"
    for inhalt in (b"[]", b'{"access_token": "a"}', b'{"refresh_token": " "}', b"{kaputt", b"\xff"):
        pfad.write_bytes(inhalt)
        assert lade_token(pfad) == {}
    pfad.write_text('{"refresh_token": "r"}', encoding="utf-8")
    assert lade_token(pfad) == {"refresh_token": "r"}
    assert lade_token(tmp_path / "fehlt.json") == {}


def test_speichere_token_legt_ordner_an_und_schreibt_exakt(tmp_path):
    pfad = tmp_path / "neu" / "google-token.json"
    token = {"access_token": "a", "refresh_token": "r", "ablauf": 5.5}
    speichere_token(pfad, token)
    assert lade_token(pfad) == token
    assert [p.name for p in pfad.parent.iterdir()] == ["google-token.json"]
    assert json.loads(pfad.read_text(encoding="utf-8")) == token


def test_speichere_token_prueft_refresh_vor_dem_anlegen(tmp_path):
    pfad = tmp_path / "neu" / "google-token.json"
    for token in (None, [], {}, {"refresh_token": ""}, {"refresh_token": 5}):
        with pytest.raises(ValueError, match="refresh_token"):
            speichere_token(pfad, token)
    assert not pfad.parent.exists()


def test_speichere_token_laesst_bei_schreibfehler_die_alte_datei_stehen(tmp_path, monkeypatch):
    pfad = tmp_path / "google-token.json"
    speichere_token(pfad, {"access_token": "alt", "refresh_token": "r", "ablauf": 1})
    vorher = pfad.read_bytes()

    def fehlschlag(*_args, **_kwargs):
        raise OSError("Testschreibfehler")

    monkeypatch.setattr(googleauth_modul.os, "replace", fehlschlag)
    with pytest.raises(ValueError, match="Token-Datei"):
        speichere_token(pfad, {"access_token": "neu", "refresh_token": "r", "ablauf": 2})
    assert pfad.read_bytes() == vorher
    assert [p.name for p in tmp_path.iterdir()] == ["google-token.json"]


@pytest.mark.parametrize(
    "token",
    [
        {"refresh_token": "r", "wert": object()},
        {"refresh_token": "r", "wert": "\ud800"},
    ],
)
def test_speichere_token_meldet_nicht_schreibbaren_inhalt_ohne_reste(tmp_path, token):
    pfad = tmp_path / "neu" / "google-token.json"
    with pytest.raises(ValueError, match="Token"):
        speichere_token(pfad, token)
    assert not pfad.parent.exists()
