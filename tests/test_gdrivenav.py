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


def test_konstanten_sind_fest():
    assert WURZEL == "root"
    assert GETEILT == "geteilt"
    assert ORDNER == "application/vnd.google-apps.folder"


def test_konto_anfrage_hat_nur_das_vereinbarte_feld():
    teile = urlsplit(konto_anfrage())
    assert f"{teile.scheme}://{teile.netloc}{teile.path}" == (
        "https://www.googleapis.com/drive/v3/about"
    )
    assert abfrage(konto_anfrage()) == {"fields": "user(displayName,emailAddress)"}


@pytest.mark.parametrize(
    ("antwort", "erwartet"),
    [
        ({"user": {"emailAddress": "a@b.ch", "displayName": "Name"}}, "a@b.ch"),
        ({"user": {"emailAddress": " a@b.ch "}}, "a@b.ch"),
        ({"user": {"displayName": " Nur Name "}}, "Nur Name"),
        ({"user": {"emailAddress": " ", "displayName": " Ersatz "}}, "Ersatz"),
    ],
)
def test_auswerte_konto_nutzt_email_dann_anzeigenamen(antwort, erwartet):
    assert auswerte_konto(json.dumps(antwort).encode()) == erwartet


@pytest.mark.parametrize(
    "antwort",
    [
        b"{}",
        b'{"user": {}}',
        b'{"user": {"emailAddress": " "}}',
        b'{"user": {"emailAddress": 5, "displayName": 7}}',
        b'{"user": "Name"}',
    ],
)
def test_auswerte_konto_meldet_fehlendes_konto(antwort):
    with pytest.raises(ValueError, match="Konto"):
        auswerte_konto(antwort)


@pytest.mark.parametrize(
    ("antwort", "meldung"), [(b"<html>", "JSON"), (b"\xff", "JSON"), (b"[]", "Objekt")]
)
def test_auswerte_konto_meldet_ungueltiges_json(antwort, meldung):
    with pytest.raises(ValueError, match=meldung):
        auswerte_konto(antwort)


@pytest.mark.parametrize("antwort", [None, "<html>", 5])
def test_auswerte_konto_verlangt_bytes(antwort):
    with pytest.raises(ValueError, match="antwort"):
        auswerte_konto(antwort)


def test_auswerte_konto_meldet_google_fehler():
    fehler = json.dumps({"error": {"message": "Invalid Credentials"}}).encode()
    with pytest.raises(ValueError, match="Invalid Credentials"):
        auswerte_konto(fehler)
    with pytest.raises(ValueError, match="quotaExceeded"):
        auswerte_konto(b'{"error": "quotaExceeded"}')
    with pytest.raises(ValueError, match="Unbekannter Fehler"):
        auswerte_konto(b'{"error": {}}')


def test_datei_anfrage_hat_die_vereinbarten_parameter():
    url = datei_anfrage("abc-DEF_1")
    assert urlsplit(url).path == "/drive/v3/files/abc-DEF_1"
    assert abfrage(url) == {
        "fields": "id,name,mimeType,ownedByMe",
        "supportsAllDrives": "true",
    }


def test_datei_anfrage_akzeptiert_die_grenzlaenge():
    assert datei_anfrage("a" * 200).endswith(
        "?fields=id%2Cname%2CmimeType%2CownedByMe&supportsAllDrives=true"
    )


@pytest.mark.parametrize(
    "kennung",
    ["", "a/b", "a b", "a?x=1", "a=b", "ä", "a" * 201, 5, None],
)
def test_datei_anfrage_meldet_die_id(kennung):
    with pytest.raises(ValueError, match="id"):
        datei_anfrage(kennung)


def test_auswerte_datei_liefert_die_vereinbarten_felder():
    antwort = json.dumps(eintrag("7", "Mein Vertrag", WORD, eigene=False)).encode()
    assert auswerte_datei(antwort) == {
        "id": "7",
        "name": "Mein Vertrag",
        "mime": WORD,
        "eigene": False,
    }


def test_auswerte_datei_ohne_flag_ist_nicht_eigen():
    antwort = json.dumps({"id": "1", "name": "Vertrag", "mimeType": GOOGLE_DOC}).encode()
    assert auswerte_datei(antwort)["eigene"] is False


@pytest.mark.parametrize(
    ("antwort", "meldung"),
    [
        ({"id": "1", "name": "Bild", "mimeType": "image/png"}, "Google Docs"),
        ({"id": "1", "name": "Bild"}, "Google Docs"),
        ({"name": "ohne id", "mimeType": WORD}, "Datei"),
        ({"id": "", "name": "x", "mimeType": WORD}, "id"),
        ({"id": "a/b", "name": "x", "mimeType": WORD}, "id"),
        ({"id": "1", "name": 5, "mimeType": WORD}, "name"),
        ({"id": "1", "name": "  ", "mimeType": WORD}, "name"),
    ],
)
def test_auswerte_datei_meldet_ungueltige_eintraege(antwort, meldung):
    with pytest.raises(ValueError, match=meldung):
        auswerte_datei(json.dumps(antwort).encode())


def test_auswerte_datei_meldet_ungueltiges_json():
    with pytest.raises(ValueError, match="JSON"):
        auswerte_datei(b"<html>")
    with pytest.raises(ValueError, match="antwort"):
        auswerte_datei("kein bytes")


def test_ordner_anfrage_wurzeln_und_geteilt():
    typen = f"(mimeType='{ORDNER}' or mimeType='{GOOGLE_DOC}' or mimeType='{WORD}')"
    assert abfrage(ordner_anfrage())["q"] == (f"'root' in parents and trashed=false and {typen}")
    assert abfrage(ordner_anfrage(GETEILT))["q"] == (
        f"sharedWithMe=true and trashed=false and {typen}"
    )
    assert abfrage(ordner_anfrage("F1"))["q"] == f"'F1' in parents and trashed=false and {typen}"


def test_ordner_anfrage_hat_die_vereinbarten_parameter():
    parameter = abfrage(ordner_anfrage("F1"))
    assert parameter["fields"] == "nextPageToken,files(id,name,mimeType,ownedByMe)"
    assert parameter["pageSize"] == "200"
    assert parameter["orderBy"] == "folder,name"
    assert parameter["supportsAllDrives"] == "true"
    assert parameter["includeItemsFromAllDrives"] == "true"
    assert "pageToken" not in parameter


@pytest.mark.parametrize("seitentoken", ["a/b c", "x+y", "Grüße & mehr"])
def test_ordner_anfrage_kodiert_den_seitentoken(seitentoken):
    assert abfrage(ordner_anfrage("F1", seitentoken))["pageToken"] == seitentoken


@pytest.mark.parametrize("seitentoken", [None, 5, b"abc"])
def test_ordner_anfrage_verlangt_einen_texttoken(seitentoken):
    with pytest.raises(ValueError, match="seitentoken"):
        ordner_anfrage("F1", seitentoken)


@pytest.mark.parametrize(
    "ordner_id",
    ["", "x' or name contains '", "a b", "a/b", "ä", "a" * 201, 7, None],
)
def test_ordner_anfrage_meldet_die_ordner_id(ordner_id):
    with pytest.raises(ValueError, match="ordner_id"):
        ordner_anfrage(ordner_id)


def test_ordner_anfrage_akzeptiert_die_grenzlaenge():
    assert "'" + "a" * 200 + "' in parents" in abfrage(ordner_anfrage("a" * 200))["q"]


def test_auswerte_ordner_trennt_sortiert_und_meldet_den_token():
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
    assert auswerte_ordner(antwort) == (
        [{"id": "f1", "name": "Alpha"}, {"id": "f2", "name": "zeta"}],
        [
            {"id": "d1", "name": "august Protokoll", "mime": GOOGLE_DOC, "eigene": True},
            {"id": "d2", "name": "Vertrag B", "mime": WORD, "eigene": False},
        ],
        "weiter",
    )


def test_auswerte_ordner_sortiert_gleichnamige_eintraege_nach_id():
    antwort = json.dumps(
        {
            "files": [
                eintrag("10", "Vertrag", WORD),
                eintrag("2", "vertrag", ORDNER),
                eintrag("1", "VERTRAG", ORDNER),
            ]
        }
    ).encode()
    ordner, dateien, _ = auswerte_ordner(antwort)
    assert [eintrag["id"] for eintrag in ordner] == ["1", "2"]
    assert [eintrag["id"] for eintrag in dateien] == ["10"]


@pytest.mark.parametrize(
    "antwort",
    [b"{}", b'{"files": []}', b'{"files": null}', b'{"files": [], "nextPageToken": null}'],
)
def test_auswerte_ordner_leere_antworten(antwort):
    assert auswerte_ordner(antwort) == ([], [], "")


@pytest.mark.parametrize(
    ("antwort", "meldung"),
    [
        (b"<html>", "JSON"),
        (b"\xff", "JSON"),
        (b"[]", "Objekt"),
        (b'{"files": 5}', "files"),
        (b'{"files": [], "nextPageToken": 5}', "nextPageToken"),
        (b'{"error": {"message": "Invalid Credentials"}}', "Invalid Credentials"),
    ],
)
def test_auswerte_ordner_meldet_ungueltige_antworten(antwort, meldung):
    with pytest.raises(ValueError, match=meldung):
        auswerte_ordner(antwort)


def test_auswerte_ordner_verlangt_bytes():
    with pytest.raises(ValueError, match="antwort"):
        auswerte_ordner("kein bytes")


def test_auswerte_ordner_uebergeht_ungueltige_ids():
    antwort = json.dumps(
        {
            "files": [
                eintrag("a/b", "Ordner", ORDNER),
                eintrag("", "Leer", ORDNER),
                eintrag("ok", "Gut", ORDNER),
            ]
        }
    ).encode()
    assert auswerte_ordner(antwort) == ([{"id": "ok", "name": "Gut"}], [], "")


def test_suche_in_trimmt_und_ignoriert_gross_kleinschreibung():
    dateien = [
        {"id": "1", "name": "Feltenbummler Vertrag"},
        {"id": "2", "name": "Rechnung"},
        {"id": "3", "name": "GRÜSSE"},
    ]
    assert suche_in(dateien, "  VERTRAG  ") == dateien[:1]
    assert suche_in(dateien, "grüsse") == dateien[2:]


@pytest.mark.parametrize("text", ["", "   "])
def test_suche_in_leerer_text_behaelt_alle(text):
    dateien = [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}]
    assert suche_in(dateien, text) == dateien


def test_suche_in_ohne_treffer_und_uebergeht_kaputte_eintraege():
    dateien = [{"id": "1", "name": "A"}, "kaputt", {"id": "2"}, {"id": "3", "name": 5}]
    assert suche_in(dateien, "xyz") == []
    assert suche_in(dateien, "a") == [{"id": "1", "name": "A"}]
    assert suche_in([], "a") == []


@pytest.mark.parametrize("eintraege", ["x", None, {"name": "A"}])
def test_suche_in_verlangt_eine_liste(eintraege):
    with pytest.raises(ValueError, match="eintraege"):
        suche_in(eintraege, "a")


@pytest.mark.parametrize("text", [None, 5, b"a"])
def test_suche_in_verlangt_einen_text(text):
    with pytest.raises(ValueError, match="text"):
        suche_in([], text)
