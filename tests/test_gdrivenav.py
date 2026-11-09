"""Tests fuer projekt.gdrivenav mit synthetischen Drive-Antworten ohne Netzwerk."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from projekt.gdrive import GOOGLE_DOC, WORD
from projekt.gdrivenav import (
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


def test_konstanten_und_kontoanfrage_sind_fest():
    assert (WURZEL, GETEILT) == ("root", "geteilt")
    assert ORDNER == "application/vnd.google-apps.folder"
    assert konto_anfrage() == (
        "https://www.googleapis.com/drive/v3/about?fields=user(displayName,emailAddress)"
    )


def test_konto_bevorzugt_mail_dann_namen_und_meldet_api_fehler():
    beide = {"user": {"emailAddress": " a@b.ch ", "displayName": "Name"}}
    assert auswerte_konto(json.dumps(beide).encode()) == "a@b.ch"
    assert auswerte_konto(b'{"user": {"displayName": "  Name  "}}') == "Name"
    assert auswerte_konto(b'{"user": {"emailAddress": 5, "displayName": "Name"}}') == "Name"

    for antwort in (b"{}", b'{"user": []}', b'{"user": {"emailAddress": " "}}'):
        with pytest.raises(ValueError, match="Konto"):
            auswerte_konto(antwort)
    with pytest.raises(ValueError, match="Invalid Credentials"):
        auswerte_konto(b'{"error": {"message": "Invalid Credentials"}}')


def test_konto_prueft_json_und_antworttyp():
    with pytest.raises(ValueError, match="antwort"):
        auswerte_konto("{}")
    with pytest.raises(ValueError, match="JSON"):
        auswerte_konto(b"<html>")
    with pytest.raises(ValueError, match="JSON-Objekt"):
        auswerte_konto(b"[]")


@pytest.mark.parametrize("kennung", ["a", "a" * 200, "ABC_def-123"])
def test_datei_anfrage_akzeptiert_drive_ids(kennung):
    url = datei_anfrage(kennung)
    assert urlsplit(url).path == f"/drive/v3/files/{kennung}"
    assert abfrage(url) == {
        "fields": "id,name,mimeType,ownedByMe",
        "supportsAllDrives": "true",
    }


@pytest.mark.parametrize(
    "kennung",
    ["", "a" * 201, "a/b", "a b", "a+b", "ä", "x' or name contains '", None, 7],
)
def test_datei_anfrage_lehnt_ungueltige_ids_ab(kennung):
    with pytest.raises(ValueError, match="id"):
        datei_anfrage(kennung)


def test_auswerte_datei_liefert_nur_docs_und_word():
    assert auswerte_datei(json.dumps(eintrag("7", "Vertrag", WORD, False)).encode()) == {
        "id": "7",
        "name": "Vertrag",
        "mime": WORD,
        "eigene": False,
    }
    assert (
        auswerte_datei(json.dumps(eintrag("8", "Protokoll", eigene=False)).encode())["eigene"]
        is False
    )
    assert (
        auswerte_datei(json.dumps({**eintrag("9", "Vertrag"), "ownedByMe": "true"}).encode())[
            "eigene"
        ]
        is False
    )

    with pytest.raises(ValueError, match="Google Docs"):
        auswerte_datei(json.dumps(eintrag("7", "Bild", "image/png")).encode())
    with pytest.raises(ValueError, match="Datei"):
        auswerte_datei(b'{"name": "ohne id"}')
    with pytest.raises(ValueError, match="Datei"):
        auswerte_datei(json.dumps(eintrag("a/b", "Vertrag")).encode())
    with pytest.raises(ValueError, match="Datei"):
        auswerte_datei(json.dumps(eintrag("a" * 201, "Vertrag")).encode())
    with pytest.raises(ValueError, match="Datei"):
        auswerte_datei(json.dumps(eintrag("7", "  ")).encode())


def test_ordner_anfrage_unterscheidet_wurzel_geteilt_und_seite():
    wurzel = abfrage(ordner_anfrage())
    assert wurzel["q"] == (
        f"'root' in parents and trashed=false and (mimeType='{ORDNER}' or "
        f"mimeType='{GOOGLE_DOC}' or mimeType='{WORD}')"
    )
    assert wurzel["fields"] == "nextPageToken,files(id,name,mimeType,ownedByMe)"
    assert wurzel["pageSize"] == "200" and wurzel["orderBy"] == "folder,name"
    assert wurzel["supportsAllDrives"] == wurzel["includeItemsFromAllDrives"] == "true"
    assert "pageToken" not in wurzel

    geteilt = abfrage(ordner_anfrage(GETEILT))
    assert geteilt["q"].startswith("sharedWithMe=true and trashed=false and (mimeType=")
    assert abfrage(ordner_anfrage("F1", "a/b c"))["pageToken"] == "a/b c"
    assert abfrage(ordner_anfrage("F1", "Grüße & mehr"))["pageToken"] == "Grüße & mehr"


@pytest.mark.parametrize(
    "ordner_id",
    ["", "a" * 201, "a/b", "a b", "x' or name contains '", None, 7],
)
def test_ordner_anfrage_lehnt_ungueltige_ids_ab(ordner_id):
    with pytest.raises(ValueError, match="ordner_id"):
        ordner_anfrage(ordner_id)


@pytest.mark.parametrize("seitentoken", [None, 1, b"abc"])
def test_ordner_anfrage_verlangt_texttoken(seitentoken):
    with pytest.raises(ValueError, match="seitentoken"):
        ordner_anfrage("F1", seitentoken)


def test_auswerte_ordner_sortiert_und_uebergeht_unbrauchbare_eintraege():
    antwort = json.dumps(
        {
            "nextPageToken": "weiter",
            "files": [
                eintrag("f2", "zeta", ORDNER),
                eintrag("f1", "Alpha", ORDNER),
                eintrag("f3", "alpha", ORDNER),
                eintrag("d2", "VERTRAG", WORD, False),
                eintrag("d1", "vertrag", GOOGLE_DOC),
                eintrag("x", "Bild", "image/png"),
                eintrag("a/b", "Ordner kaputt", ORDNER),
                {"id": "y", "name": 5, "mimeType": WORD},
                "kaputt",
            ],
        }
    ).encode()

    ordner, dateien, weiter = auswerte_ordner(antwort)

    assert ordner == [
        {"id": "f1", "name": "Alpha"},
        {"id": "f3", "name": "alpha"},
        {"id": "f2", "name": "zeta"},
    ]
    assert dateien == [
        {"id": "d1", "name": "vertrag", "mime": GOOGLE_DOC, "eigene": True},
        {"id": "d2", "name": "VERTRAG", "mime": WORD, "eigene": False},
    ]
    assert weiter == "weiter"


def test_auswerte_ordner_behandelt_leere_und_fehlerhafte_listen():
    assert auswerte_ordner(b"{}") == ([], [], "")
    assert auswerte_ordner(b'{"files": null, "nextPageToken": null}') == ([], [], "")
    with pytest.raises(ValueError, match="files"):
        auswerte_ordner(b'{"files": {}}')
    with pytest.raises(ValueError, match="nextPageToken"):
        auswerte_ordner(b'{"files": [], "nextPageToken": 5}')
    with pytest.raises(ValueError, match="JSON"):
        auswerte_ordner(b"<html>")
    with pytest.raises(ValueError, match="Invalid"):
        auswerte_ordner(b'{"error": {"message": "Invalid Credentials"}}')


def test_suche_in_filtert_ohne_gross_kleinschreibung_und_trimmt():
    eintraege = [
        {"id": "1", "name": "Übergabe Protokoll"},
        {"id": "2", "name": "Rechnung"},
        "kaputt",
        {"id": "3", "name": 5},
    ]
    assert suche_in(eintraege, "  PROTOKOLL ") == [eintraege[0]]
    assert suche_in(eintraege, "übergabe") == [eintraege[0]]
    assert suche_in(eintraege, "   ") == eintraege
    assert suche_in(eintraege, "xyz") == []


def test_suche_in_prueft_liste_und_text():
    with pytest.raises(ValueError, match="eintraege"):
        suche_in("x", "a")
    with pytest.raises(ValueError, match="text"):
        suche_in([], None)
