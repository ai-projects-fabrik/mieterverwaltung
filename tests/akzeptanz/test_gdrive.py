"""Akzeptanztest (spec-first) fuer projekt.gdrive (Ziel `mv-gdrive`)."""

import importlib.util
import json
from urllib.parse import parse_qs, urlsplit

import pytest

if importlib.util.find_spec("projekt.gdrive") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.gdrive import (  # noqa: E402
    GOOGLE_DOC,
    STICHWORTE,
    WORD,
    abruf_anfrage,
    auswerte_liste,
    liste_anfrage,
    passt,
)


def datei(kennung, name, mime=GOOGLE_DOC, eigene=True):
    return {"id": kennung, "name": name, "mimeType": mime, "ownedByMe": eigene}


def test_konstanten():
    assert GOOGLE_DOC == "application/vnd.google-apps.document"
    assert WORD == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert STICHWORTE == ("vertrag", "protokoll")


def test_passt_ohne_gross_und_kleinschreibung_als_teilwort():
    assert passt("Feltenbummler Vertrag 2026")
    assert passt("August26-Uebergabeprotokoll")
    assert passt("KAUFVERTRAG")
    assert not passt("Rechnung Strom")
    assert passt("Rechnung Strom", ("strom",))
    assert not passt("Vertrag", ("protokoll",))
    assert passt("Irgendwas", ())
    assert passt("Irgendwas", (" ",))
    with pytest.raises(ValueError, match="name"):
        passt(5)


def test_liste_anfrage():
    teile = urlsplit(liste_anfrage())
    assert (
        f"{teile.scheme}://{teile.netloc}{teile.path}"
        == "https://www.googleapis.com/drive/v3/files"
    )
    q = {k: v[0] for k, v in parse_qs(teile.query).items()}
    assert q["q"] == (f"trashed=false and (mimeType='{GOOGLE_DOC}' or mimeType='{WORD}')")
    assert q["fields"] == "nextPageToken,files(id,name,mimeType,ownedByMe)"
    assert q["supportsAllDrives"] == "true"
    assert q["includeItemsFromAllDrives"] == "true"
    assert q["pageSize"] == "1000"
    assert "pageToken" not in q
    seite = {k: v[0] for k, v in parse_qs(urlsplit(liste_anfrage("a/b c")).query).items()}
    assert seite["pageToken"] == "a/b c"
    assert "name contains" not in liste_anfrage()


def test_auswerte_liste_filtert_und_sortiert():
    antwort = json.dumps(
        {
            "nextPageToken": "weiter",
            "files": [
                datei("3", "August26-Uebergabeprotokoll", GOOGLE_DOC, eigene=False),
                datei("1", "feltenbummler Vertrag", WORD, eigene=False),
                datei("2", "Rechnung Strom", WORD),
                datei("4", "Alter Vertrag", "application/pdf"),
                datei("5", "Aelterer Vertrag"),
                {"id": "6", "name": 7, "mimeType": WORD},
                {"name": "Vertrag ohne id", "mimeType": WORD},
                "kaputt",
            ],
        }
    ).encode()
    treffer, weiter = auswerte_liste(antwort)
    assert weiter == "weiter"
    assert treffer == [
        {"id": "5", "name": "Aelterer Vertrag", "mime": GOOGLE_DOC, "eigene": True},
        {"id": "3", "name": "August26-Uebergabeprotokoll", "mime": GOOGLE_DOC, "eigene": False},
        {"id": "1", "name": "feltenbummler Vertrag", "mime": WORD, "eigene": False},
    ]
    alle, _ = auswerte_liste(antwort.replace(b"weiter", b"x"), ("strom",))
    assert [d["id"] for d in alle] == ["2"]
    assert auswerte_liste(b'{"files": []}') == ([], "")
    assert auswerte_liste(b"{}") == ([], "")


def test_auswerte_liste_fehler():
    with pytest.raises(ValueError, match="JSON"):
        auswerte_liste(b"<html>")
    with pytest.raises(ValueError, match="Objekt"):
        auswerte_liste(b"[]")
    fehler = json.dumps({"error": {"code": 401, "message": "Invalid Credentials"}}).encode()
    with pytest.raises(ValueError, match="Invalid Credentials"):
        auswerte_liste(fehler)


def test_abruf_anfrage():
    assert abruf_anfrage({"id": "abc", "mime": WORD}) == (
        "https://www.googleapis.com/drive/v3/files/abc?alt=media&supportsAllDrives=true"
    )
    export = abruf_anfrage({"id": "a/b", "mime": GOOGLE_DOC})
    teile = urlsplit(export)
    assert teile.path == "/drive/v3/files/a%2Fb/export"
    assert parse_qs(teile.query) == {"mimeType": [WORD]}
    with pytest.raises(ValueError, match="id"):
        abruf_anfrage({"mime": WORD})
    with pytest.raises(ValueError, match="id"):
        abruf_anfrage("x")
    with pytest.raises(ValueError, match="mime"):
        abruf_anfrage({"id": "a", "mime": "application/pdf"})
