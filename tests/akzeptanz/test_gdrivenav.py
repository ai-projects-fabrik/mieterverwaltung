"""Akzeptanztest (spec-first) fuer projekt.gdrivenav (Ziel `mv-gdrivenav`)."""

import importlib.util
import json
from urllib.parse import parse_qs, urlsplit

import pytest

if importlib.util.find_spec("projekt.gdrivenav") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.gdrive import GOOGLE_DOC, WORD  # noqa: E402
from projekt.gdrivenav import (  # noqa: E402
    GETEILT,
    ORDNER,
    WURZEL,
    auswerte_datei,
    auswerte_konto,
    auswerte_ordner,
    datei_anfrage,
    konto_anfrage,
    ordner_anfrage,
    suche_in,
)


def eintrag(kennung, name, mime=GOOGLE_DOC, eigene=True):
    return {"id": kennung, "name": name, "mimeType": mime, "ownedByMe": eigene}


def abfrage(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_konstanten():
    assert (WURZEL, GETEILT) == ("root", "geteilt")
    assert ORDNER == "application/vnd.google-apps.folder"


def test_konto():
    url = konto_anfrage()
    assert url.startswith("https://www.googleapis.com/drive/v3/about?")
    assert abfrage(url) == {"fields": "user(displayName,emailAddress)"}
    antwort = json.dumps({"user": {"displayName": "Swiss Seller", "emailAddress": "a@b.ch"}})
    assert auswerte_konto(antwort.encode()) == "a@b.ch"
    assert auswerte_konto(b'{"user": {"displayName": " Nur Name "}}') == "Nur Name"
    for schlecht in (b"{}", b'{"user": {}}', b'{"user": {"emailAddress": " "}}'):
        with pytest.raises(ValueError, match="Konto"):
            auswerte_konto(schlecht)
    with pytest.raises(ValueError, match="Invalid"):
        auswerte_konto(json.dumps({"error": {"message": "Invalid Credentials"}}).encode())


def test_datei():
    url = datei_anfrage("abc-DEF_1")
    assert urlsplit(url).path == "/drive/v3/files/abc-DEF_1"
    assert abfrage(url) == {"fields": "id,name,mimeType,ownedByMe", "supportsAllDrives": "true"}
    for schlecht in ("", "a/b", "a b", "a?x=1", 5):
        with pytest.raises(ValueError, match="id"):
            datei_anfrage(schlecht)
    antwort = json.dumps(eintrag("7", "Mein Vertrag", WORD, eigene=False)).encode()
    assert auswerte_datei(antwort) == {
        "id": "7",
        "name": "Mein Vertrag",
        "mime": WORD,
        "eigene": False,
    }
    with pytest.raises(ValueError, match="Google Docs"):
        auswerte_datei(json.dumps(eintrag("7", "Bild", "image/png")).encode())
    with pytest.raises(ValueError, match="Datei"):
        auswerte_datei(b'{"name": "ohne id"}')


def test_ordner_anfrage():
    q = abfrage(ordner_anfrage())["q"]
    assert q == (
        "'root' in parents and trashed=false and "
        f"(mimeType='{ORDNER}' or mimeType='{GOOGLE_DOC}' or mimeType='{WORD}')"
    )
    assert "'F1' in parents" in abfrage(ordner_anfrage("F1"))["q"]
    geteilt = abfrage(ordner_anfrage(GETEILT))["q"]
    assert geteilt.startswith("sharedWithMe=true and trashed=false and (mimeType=")
    rest = abfrage(ordner_anfrage("F1"))
    assert rest["fields"] == "nextPageToken,files(id,name,mimeType,ownedByMe)"
    assert rest["orderBy"] == "folder,name" and rest["pageSize"] == "200"
    assert rest["supportsAllDrives"] == rest["includeItemsFromAllDrives"] == "true"
    assert "pageToken" not in rest
    assert abfrage(ordner_anfrage("F1", "a/b c"))["pageToken"] == "a/b c"
    for schlecht in ("", "x' or name contains '", "a b", 7):
        with pytest.raises(ValueError, match="ordner_id"):
            ordner_anfrage(schlecht)


def test_auswerte_ordner_trennt_ordner_und_dateien():
    antwort = json.dumps(
        {
            "nextPageToken": "weiter",
            "files": [
                eintrag("f2", "zeta", ORDNER),
                eintrag("d2", "Vertrag B", WORD, eigene=False),
                eintrag("f1", "Alpha", ORDNER),
                eintrag("d1", "august Protokoll"),
                eintrag("x", "Bild", "image/png"),
                {"id": "y", "name": 5, "mimeType": WORD},
                "kaputt",
            ],
        }
    ).encode()
    ordner, dateien, weiter = auswerte_ordner(antwort)
    assert ordner == [{"id": "f1", "name": "Alpha"}, {"id": "f2", "name": "zeta"}]
    assert dateien == [
        {"id": "d1", "name": "august Protokoll", "mime": GOOGLE_DOC, "eigene": True},
        {"id": "d2", "name": "Vertrag B", "mime": WORD, "eigene": False},
    ]
    assert weiter == "weiter"
    assert auswerte_ordner(b"{}") == ([], [], "")
    with pytest.raises(ValueError, match="JSON"):
        auswerte_ordner(b"<html>")


def test_suche_in():
    dateien = [{"id": "1", "name": "Feltenbummler Vertrag"}, {"id": "2", "name": "Rechnung"}]
    assert suche_in(dateien, "VERTRAG") == dateien[:1]
    assert suche_in(dateien, "  ") == dateien
    assert suche_in(dateien, "xyz") == []
    assert suche_in([], "a") == []
    with pytest.raises(ValueError, match="eintraege"):
        suche_in("x", "a")
    with pytest.raises(ValueError, match="text"):
        suche_in(dateien, None)
