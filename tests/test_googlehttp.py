"""Tests fuer projekt.googlehttp (ohne Netz: Fake-Transport, Loopback nur lokal)."""

import json
import threading
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest

from projekt import googlehttp
from projekt.gdrive import GOOGLE_DOC, WORD
from projekt.googleauth import client_pfad, lade_token, speichere_token, token_pfad
from projekt.googlehttp import (
    GoogleQuelle,
    anmelden,
    hole_vorlage,
    liste_vorlagen_google,
    zugriffstoken,
)

CLIENT = {
    "client_id": "cid",
    "client_secret": "geheim",
    "auth_uri": "https://accounts.example/auth",
    "token_uri": "https://tokens.example/token",
}
CLIENT_JSON = json.dumps({"installed": {"client_id": "cid", "client_secret": "geheim"}})
LISTE = {
    "files": [
        {"id": "1", "name": "Mietvertrag", "mimeType": GOOGLE_DOC, "ownedByMe": False},
        {"id": "2", "name": "Rechnung", "mimeType": WORD, "ownedByMe": True},
    ]
}
DOCX = b"PK\x03\x04docx"


class Fake:
    """Zeichnet Aufrufe auf und antwortet nach Teilstueck der Adresse."""

    def __init__(self, antworten=None):
        self.aufrufe = []
        self.antworten = antworten or {}

    def __call__(self, url, kopf, daten):
        self.aufrufe.append((url, dict(kopf), daten))
        for teil, antwort in self.antworten.items():
            if teil in url:
                return antwort(url) if callable(antwort) else antwort
        return 404, b"{}"


def token_antwort(zugriff="neu", **extra):
    return 200, json.dumps({"access_token": zugriff, "expires_in": 3600, **extra}).encode()


def browser(code="C1", state=None):
    """Nachgestellter Browser: ruft den Redirect der Anmelde-Adresse lokal auf."""

    gesehen = {}

    def oeffne(url):
        q = parse_qs(urlsplit(url).query)
        gesehen.update(url=url, q=q)
        ziel = q["redirect_uri"][0]
        abfrage = f"code={code}&state={state or q['state'][0]}"
        threading.Thread(
            target=lambda: urllib.request.urlopen(f"{ziel}?{abfrage}", timeout=10).read(),
            daemon=True,
        ).start()

    oeffne.gesehen = gesehen
    return oeffne


def test_senden_verlangt_https():
    with pytest.raises(ValueError, match="https"):
        googlehttp.senden("http://www.googleapis.com/x")


def test_anmelden_tauscht_code_gegen_token():
    transport = Fake({"tokens.example": token_antwort("a1", refresh_token="r1")})
    oeffne = browser()
    token = anmelden(CLIENT, transport=transport, oeffne=oeffne, jetzt=lambda: 100.0, wartezeit=10)
    assert token == {"access_token": "a1", "refresh_token": "r1", "ablauf": 3700.0}
    q = oeffne.gesehen["q"]
    assert q["redirect_uri"][0].startswith("http://127.0.0.1:")
    assert q["code_challenge_method"] == ["S256"]
    url, kopf, daten = transport.aufrufe[0]
    assert url == "https://tokens.example/token"
    assert kopf["Content-Type"] == "application/x-www-form-urlencoded"
    form = parse_qs(daten.decode())
    assert form["code"] == ["C1"] and form["redirect_uri"] == q["redirect_uri"]
    assert form["grant_type"] == ["authorization_code"]


def test_anmelden_lehnt_falschen_state_ab():
    transport = Fake({"tokens.example": token_antwort(refresh_token="r")})
    with pytest.raises(ValueError, match="state"):
        anmelden(CLIENT, transport=transport, oeffne=browser(state="fremd"), wartezeit=10)
    assert transport.aufrufe == []


def test_anmelden_ohne_antwort_endet_im_zeitlimit():
    with pytest.raises(ValueError, match="rechtzeitig"):
        anmelden(CLIENT, transport=Fake(), oeffne=lambda url: None, wartezeit=0.3)


def test_zugriffstoken_nutzt_gueltiges_und_erneuert_abgelaufenes(tmp_path):
    datei = token_pfad(tmp_path)
    transport = Fake({"tokens.example": token_antwort("frisch")})
    with pytest.raises(ValueError, match="nicht verbunden"):
        zugriffstoken(CLIENT, datei, transport=transport, jetzt=lambda: 0)
    speichere_token(datei, {"access_token": "alt", "refresh_token": "r", "ablauf": 5000})
    assert zugriffstoken(CLIENT, datei, transport=transport, jetzt=lambda: 100) == "alt"
    assert transport.aufrufe == []
    assert zugriffstoken(CLIENT, datei, transport=transport, jetzt=lambda: 4990) == "frisch"
    gespeichert = lade_token(datei)
    assert gespeichert["access_token"] == "frisch" and gespeichert["refresh_token"] == "r"
    assert parse_qs(transport.aufrufe[0][2].decode())["grant_type"] == ["refresh_token"]


def test_liste_vorlagen_google_blaettert_und_filtert():
    seiten = {
        "": {"files": LISTE["files"][:1], "nextPageToken": "p2"},
        "p2": {"files": LISTE["files"][1:]},
    }

    def antwort(url):
        token = parse_qs(urlsplit(url).query).get("pageToken", [""])[0]
        return 200, json.dumps(seiten[token]).encode()

    transport = Fake({"drive/v3/files": antwort})
    dateien = liste_vorlagen_google("zt", transport=transport)
    assert [d["id"] for d in dateien] == ["1"]
    assert len(transport.aufrufe) == 2
    assert all(k["Authorization"] == "Bearer zt" for _, k, _ in transport.aufrufe)
    andere = liste_vorlagen_google("zt", stichworte=("rechnung",), transport=transport)
    assert [d["id"] for d in andere] == ["2"]


def test_liste_vorlagen_google_meldet_fehler():
    fehler = json.dumps({"error": {"message": "Invalid Credentials"}}).encode()
    with pytest.raises(ValueError, match="Invalid Credentials"):
        liste_vorlagen_google("x", transport=Fake({"drive": (401, fehler)}))
    with pytest.raises(ValueError, match="500"):
        liste_vorlagen_google("x", transport=Fake({"drive": (500, b"{}")}))


def test_hole_vorlage_export_und_pruefung():
    transport = Fake({"export": (200, DOCX), "alt=media": (200, DOCX)})
    assert hole_vorlage("zt", {"id": "1", "mime": GOOGLE_DOC}, transport=transport) == DOCX
    assert "/files/1/export" in transport.aufrufe[0][0]
    assert hole_vorlage("zt", {"id": "2", "mime": WORD}, transport=transport) == DOCX
    assert "alt=media" in transport.aufrufe[1][0]
    datei = {"id": "1", "name": "V", "mime": GOOGLE_DOC}
    with pytest.raises(ValueError, match="Status 403"):
        hole_vorlage("zt", datei, transport=Fake({"export": (403, b"")}))
    with pytest.raises(ValueError, match="docx"):
        hole_vorlage("zt", datei, transport=Fake({"export": (200, b"<html>")}))


def quelle(tmp_path, transport=None, oeffne=lambda url: None, **kw):
    return GoogleQuelle(
        tmp_path, transport=transport or Fake(), oeffne=oeffne, im_hintergrund=False, **kw
    )


def test_quelle_ohne_client_datei_zeigt_klaren_hinweis(tmp_path):
    dateien, hinweise = quelle(tmp_path).vorlagen()
    assert dateien == []
    assert "google-client.json" in hinweise[0] and str(tmp_path) in hinweise[0]
    assert "fehlt" in quelle(tmp_path).status()
    assert "fehlt" in quelle(tmp_path).verbinden()


def test_quelle_startet_die_anmeldung_nie_von_selbst(tmp_path):
    client_pfad(tmp_path).parent.mkdir(parents=True)
    client_pfad(tmp_path).write_text(CLIENT_JSON, encoding="utf-8")
    geoeffnet = []
    q = quelle(tmp_path, Fake(), geoeffnet.append)
    for _ in range(2):
        dateien, hinweise = q.vorlagen()
        assert dateien == [] and "Nicht mit Google verbunden" in hinweise[0]
    assert geoeffnet == [] and not lade_token(token_pfad(tmp_path))


def test_quelle_anmeldung_per_knopf_und_danach_liste(tmp_path):
    client_pfad(tmp_path).parent.mkdir(parents=True)
    client_pfad(tmp_path).write_text(CLIENT_JSON, encoding="utf-8")
    transport = Fake(
        {
            "oauth2.googleapis.com": token_antwort("a1", refresh_token="r1"),
            "drive/v3/files": (200, json.dumps(LISTE).encode()),
        }
    )
    q = quelle(tmp_path, transport, browser())
    assert "gestartet" in q.verbinden()
    assert lade_token(token_pfad(tmp_path))["refresh_token"] == "r1"
    assert "verbunden" in q.status()
    dateien, hinweise = q.vorlagen()
    assert [d["id"] for d in dateien] == ["1"] and hinweise == []


def test_quelle_zeitueberschreitung_ist_eine_verstaendliche_meldung(tmp_path):
    client_pfad(tmp_path).parent.mkdir(parents=True)
    client_pfad(tmp_path).write_text(CLIENT_JSON, encoding="utf-8")
    q = quelle(tmp_path, wartezeit=0.2)
    assert q.verbinden() == "Anmeldung abgebrochen - erneut versuchen"
    dateien, hinweise = q.vorlagen()
    assert "Anmeldung abgebrochen - erneut versuchen" in hinweise[0]
    assert "nicht rechtzeitig" not in hinweise[0]


def test_quelle_cache_und_hole(tmp_path):
    speichere_token(
        token_pfad(tmp_path), {"access_token": "a", "refresh_token": "r", "ablauf": 9e9}
    )
    client_pfad(tmp_path).write_text(CLIENT_JSON, encoding="utf-8")
    transport = Fake(
        {
            "drive/v3/files/1/export": (200, DOCX),
            "drive/v3/files?": (200, json.dumps(LISTE).encode()),
        }
    )
    q = quelle(tmp_path, transport)
    assert len(q.vorlagen()[0]) == 1 and len(q.vorlagen()[0]) == 1
    assert sum("files?" in u for u, _, _ in transport.aufrufe) == 1
    assert q.hole("1") == DOCX
    with pytest.raises(ValueError):
        q.hole("2")


def test_quelle_fehler_werden_zu_hinweisen(tmp_path):
    speichere_token(
        token_pfad(tmp_path), {"access_token": "a", "refresh_token": "r", "ablauf": 9e9}
    )
    client_pfad(tmp_path).write_text(CLIENT_JSON, encoding="utf-8")
    fehler = json.dumps({"error": {"message": "Kaputt"}}).encode()
    dateien, hinweise = quelle(tmp_path, Fake({"drive": (500, fehler)})).vorlagen()
    assert dateien == [] and "Kaputt" in hinweise[0]
    dateien, hinweise = quelle(tmp_path, Fake({"drive": (200, b'{"files": []}')})).vorlagen()
    assert dateien == [] and "Keine passende Vorlage" in hinweise[0]
