"""Tests fuer projekt.gdrive mit synthetischen Drive-Antworten ohne Netzwerk."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from projekt.gdrive import (
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


def test_konstanten_sind_fest():
    assert GOOGLE_DOC == "application/vnd.google-apps.document"
    assert WORD == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert STICHWORTE == ("vertrag", "protokoll")


@pytest.mark.parametrize(
    ("name", "stichworte", "erwartet"),
    [
        ("Kaufvertrag", STICHWORTE, True),
        ("August26-Uebergabeprotokoll", STICHWORTE, True),
        ("PROTOKOLL", STICHWORTE, True),
        ("Rechnung Strom", STICHWORTE, False),
        ("Irgendwas", (), True),
        ("Irgendwas", (" ",), True),
        ("Irgendwas", ("",), True),
        ("Stromrechnung", ("strom",), True),
        ("Stromrechnung", (" rechnung ",), True),
        ("Stromrechnung", ("", "vertrag"), False),
    ],
)
def test_passt_als_teilwort_ohne_gross_kleinschreibung(name, stichworte, erwartet):
    assert passt(name, stichworte) is erwartet


@pytest.mark.parametrize("name", [None, 5, b"Vertrag"])
def test_passt_verlangt_einen_textnamen(name):
    with pytest.raises(ValueError, match="name"):
        passt(name)


@pytest.mark.parametrize("stichworte", [None, ["vertrag"], ("vertrag", 5), (None,)])
def test_passt_verlangt_textstichworte(stichworte):
    with pytest.raises(ValueError, match="stichworte"):
        passt("Vertrag", stichworte)


def test_liste_anfrage_enthaelt_die_vereinbarten_parameter():
    teile = urlsplit(liste_anfrage())
    parameter = {k: v[0] for k, v in parse_qs(teile.query).items()}

    assert f"{teile.scheme}://{teile.netloc}{teile.path}" == (
        "https://www.googleapis.com/drive/v3/files"
    )
    assert parameter["q"] == (f"trashed=false and (mimeType='{GOOGLE_DOC}' or mimeType='{WORD}')")
    assert parameter["fields"] == "nextPageToken,files(id,name,mimeType,ownedByMe)"
    assert parameter["pageSize"] == "1000"
    assert parameter["supportsAllDrives"] == "true"
    assert parameter["includeItemsFromAllDrives"] == "true"
    assert "pageToken" not in parameter
    assert "name contains" not in parameter["q"]


@pytest.mark.parametrize("seitentoken", ["a/b c", "x+y", "Grüße & mehr"])
def test_liste_anfrage_kodiert_den_seitentoken(seitentoken):
    parameter = {k: v[0] for k, v in parse_qs(urlsplit(liste_anfrage(seitentoken)).query).items()}
    assert parameter["pageToken"] == seitentoken


@pytest.mark.parametrize("seitentoken", [None, 1, b"abc"])
def test_liste_anfrage_verlangt_einen_texttoken(seitentoken):
    with pytest.raises(ValueError, match="seitentoken"):
        liste_anfrage(seitentoken)


def test_auswerte_liste_filtert_sortiert_und_liefert_den_token():
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
                {"id": "7", "name": "   ", "mimeType": WORD},
                {"id": "8", "name": "Vertrag", "mimeType": 5},
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


def test_auswerte_liste_nutzt_eigene_und_geteilte_dateien():
    antwort = json.dumps(
        {
            "files": [
                datei("1", "Vertrag", GOOGLE_DOC, eigene=True),
                datei("2", "Protokoll", WORD, eigene=False),
                {"id": "3", "name": "Vertrag ohne Flag", "mimeType": WORD},
                {"id": "4", "name": "Vertrag mit Textflag", "mimeType": WORD, "ownedByMe": "true"},
            ]
        }
    ).encode()

    treffer, _ = auswerte_liste(antwort)

    assert [(datei["id"], datei["eigene"]) for datei in treffer] == [
        ("2", False),
        ("1", True),
        ("4", False),
        ("3", False),
    ]


def test_auswerte_liste_sortiert_gleichnamige_dateien_nach_id():
    antwort = json.dumps(
        {
            "files": [
                datei("10", "Vertrag"),
                datei("2", "vertrag"),
                datei("1", "VERTRAG"),
            ]
        }
    ).encode()

    treffer, _ = auswerte_liste(antwort)

    assert [datei["id"] for datei in treffer] == ["1", "10", "2"]


def test_auswerte_liste_nutzt_eigene_stichworte():
    antwort = json.dumps(
        {
            "files": [
                datei("1", "Rechnung Strom", WORD),
                datei("2", "Vertrag", WORD),
            ]
        }
    ).encode()

    treffer, _ = auswerte_liste(antwort, ("strom",))

    assert [datei["id"] for datei in treffer] == ["1"]


@pytest.mark.parametrize(
    "antwort",
    [b'{"files": []}', b"{}", b'{"files": null}', b'{"files": [], "nextPageToken": null}'],
)
def test_auswerte_liste_leere_antworten(antwort):
    assert auswerte_liste(antwort) == ([], "")


@pytest.mark.parametrize(
    ("antwort", "meldung"),
    [
        (b"<html>", "JSON"),
        (b"\xff", "JSON"),
        (b"[]", "Objekt"),
        (b'"text"', "Objekt"),
        (b'{"files": 5}', "files"),
        (b'{"files": [], "nextPageToken": 5}', "nextPageToken"),
    ],
)
def test_auswerte_liste_meldet_ungueltige_antworten(antwort, meldung):
    with pytest.raises(ValueError, match=meldung):
        auswerte_liste(antwort)


@pytest.mark.parametrize("antwort", [None, "<html>", b"", 5])
def test_auswerte_liste_verlangt_bytes(antwort):
    if isinstance(antwort, bytes):
        with pytest.raises(ValueError, match="JSON"):
            auswerte_liste(antwort)
    else:
        with pytest.raises(ValueError, match="antwort"):
            auswerte_liste(antwort)


def test_auswerte_liste_meldet_google_fehler():
    fehler = json.dumps({"error": {"code": 401, "message": "Invalid Credentials"}}).encode()
    with pytest.raises(ValueError, match="Invalid Credentials"):
        auswerte_liste(fehler)

    ohne_meldung = json.dumps({"error": {"code": 500}}).encode()
    with pytest.raises(ValueError, match="Unbekannter Fehler"):
        auswerte_liste(ohne_meldung)

    with pytest.raises(ValueError, match="quotaExceeded"):
        auswerte_liste(b'{"error": "quotaExceeded"}')


@pytest.mark.parametrize("stichworte", [None, ["vertrag"], ("vertrag", 5)])
def test_auswerte_liste_verlangt_textstichworte(stichworte):
    with pytest.raises(ValueError, match="stichworte"):
        auswerte_liste(b'{"files": []}', stichworte)


def test_abruf_anfrage_download_und_export():
    assert abruf_anfrage({"id": "abc", "mime": WORD}) == (
        "https://www.googleapis.com/drive/v3/files/abc?alt=media&supportsAllDrives=true"
    )
    export = abruf_anfrage({"id": "a/b", "mime": GOOGLE_DOC})
    teile = urlsplit(export)
    assert teile.path == "/drive/v3/files/a%2Fb/export"
    assert parse_qs(teile.query) == {"mimeType": [WORD]}


def test_abruf_anfrage_kodiert_die_id_vollstaendig():
    url = abruf_anfrage({"id": "a b+c?d#e", "mime": WORD})
    assert urlsplit(url).path == "/drive/v3/files/a%20b%2Bc%3Fd%23e"


@pytest.mark.parametrize(
    "datei",
    [
        "x",
        None,
        {},
        {"mime": WORD},
        {"id": "", "mime": WORD},
        {"id": "   ", "mime": WORD},
        {"id": 5, "mime": WORD},
    ],
)
def test_abruf_anfrage_nennt_die_id(datei):
    with pytest.raises(ValueError, match="id"):
        abruf_anfrage(datei)


@pytest.mark.parametrize(
    "datei",
    [{"id": "a"}, {"id": "a", "mime": "application/pdf"}, {"id": "a", "mime": 5}],
)
def test_abruf_anfrage_nennt_den_mime_typ(datei):
    with pytest.raises(ValueError, match="mime"):
        abruf_anfrage(datei)
