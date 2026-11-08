"""Tests fuer projekt.vorauswahl mit synthetischen Objekten und Vorlagen."""

import pytest

from projekt.auftraege import FORMATE
from projekt.vorauswahl import merke, vorauswahl

OBJEKTE = [
    {"id": "haus-a", "bezeichnung": "Haus A"},
    {"id": "haus-b", "bezeichnung": "Haus B"},
]
VORLAGEN = {
    "lokal": ["Allgemein.docx", "Mietvertrag 2026.docx"],
    "drive": ["Uebergabeprotokoll.docx"],
}


def test_ohne_letzte_auswahl_gelten_objekt_und_format_standards():
    assert vorauswahl("vertrag", OBJEKTE, {"lokal": ["Mietvertrag.docx"]}, {}) == {
        "objekt_id": "haus-a",
        "vorlage": "lokal:Mietvertrag.docx",
        "format": "docx+pdf",
        "ziel": "drive",
    }


def test_objekt_id_der_letzten_auswahl_gewinnt_nur_wenn_vorhanden():
    assert vorauswahl("vertrag", OBJEKTE, VORLAGEN, {"objekt_id": "haus-b"})["objekt_id"] == (
        "haus-b"
    )
    assert vorauswahl("vertrag", OBJEKTE, VORLAGEN, {"objekt_id": "weg"})["objekt_id"] == "haus-a"
    assert vorauswahl("vertrag", [], VORLAGEN, {"objekt_id": "haus-b"})["objekt_id"] == ""


def test_vorlagenreihenfolge_ist_lokal_vor_drive():
    vorlagen = {"lokal": ["Erste.docx"], "drive": ["Zweite.docx"]}
    assert vorauswahl("vertrag", OBJEKTE, vorlagen, {})["vorlage"] == "lokal:Erste.docx"
    assert vorauswahl("vertrag", OBJEKTE, {"drive": ["Zweite.docx"]}, {})["vorlage"] == (
        "drive:Zweite.docx"
    )


def test_erste_vorlage_mit_art_im_namen_gewinnt_ohne_beachtung_der_schreibweise():
    vorlagen = {
        "lokal": ["Allgemein.docx", "MIETVERTRAG 2027.docx"],
        "drive": ["Mietvertrag Drive.docx"],
    }
    assert vorauswahl("vertrag", OBJEKTE, vorlagen, {})["vorlage"] == "lokal:MIETVERTRAG 2027.docx"
    assert vorauswahl("protokoll", OBJEKTE, VORLAGEN, {})["vorlage"] == (
        "drive:Uebergabeprotokoll.docx"
    )


def test_ohne_passende_vorlage_ist_die_erste_verfuegbare():
    assert vorauswahl("vertrag", OBJEKTE, {"lokal": ["x.docx", "y.docx"]}, {})["vorlage"] == (
        "lokal:x.docx"
    )
    assert vorauswahl("vertrag", OBJEKTE, {}, {})["vorlage"] == ""
    assert vorauswahl("vertrag", OBJEKTE, {"lokal": []}, {})["vorlage"] == ""


def test_letzte_vorlage_gewinnt_nur_wenn_sie_noch_verfuegbar_ist():
    letzte = {"vertrag_vorlage": "lokal:Allgemein.docx"}
    assert vorauswahl("vertrag", OBJEKTE, VORLAGEN, letzte)["vorlage"] == ("lokal:Allgemein.docx")
    assert (
        vorauswahl("vertrag", OBJEKTE, VORLAGEN, {"vertrag_vorlage": "lokal:Geloescht.docx"})[
            "vorlage"
        ]
        == "lokal:Mietvertrag 2026.docx"
    )


def test_format_und_ziel_werden_geprueft_und_fallen_zurueck():
    letzte = {"format": "pdf", "ziel": "lokal"}
    assert vorauswahl("vertrag", OBJEKTE, VORLAGEN, letzte) == {
        "objekt_id": "haus-a",
        "vorlage": "lokal:Mietvertrag 2026.docx",
        "format": "pdf",
        "ziel": "lokal",
    }
    assert vorauswahl("vertrag", OBJEKTE, VORLAGEN, {"format": "xls", "ziel": "x"})["format"] == (
        "docx+pdf"
    )
    assert vorauswahl("vertrag", OBJEKTE, VORLAGEN, {"format": "xls", "ziel": "x"})["ziel"] == (
        "drive"
    )
    assert set(FORMATE) == {"docx", "pdf", "docx+pdf"}


def test_unbekannte_art_wird_abgelehnt():
    with pytest.raises(ValueError, match="art"):
        vorauswahl("brief", OBJEKTE, VORLAGEN, {})
    with pytest.raises(ValueError, match="art"):
        vorauswahl(None, OBJEKTE, VORLAGEN, {})
    with pytest.raises(ValueError, match="art"):
        merke("brief", {})
    with pytest.raises(ValueError, match="art"):
        merke(1, {})


def test_falsche_strukturen_werden_mit_feldnamen_abgelehnt():
    with pytest.raises(ValueError, match="objekte"):
        vorauswahl("vertrag", {}, VORLAGEN, {})
    with pytest.raises(ValueError, match="objekte"):
        vorauswahl("vertrag", ["haus-a"], VORLAGEN, {})
    with pytest.raises(ValueError, match="vorlagen"):
        vorauswahl("vertrag", OBJEKTE, [], {})
    with pytest.raises(ValueError, match="vorlagen_lokal"):
        vorauswahl("vertrag", OBJEKTE, {"lokal": "x.docx"}, {})
    with pytest.raises(ValueError, match="vorlagen_drive"):
        vorauswahl("vertrag", OBJEKTE, {"drive": [1]}, {})
    with pytest.raises(ValueError, match="letzte"):
        vorauswahl("vertrag", OBJEKTE, VORLAGEN, [])


def test_merke_uebernimmt_nur_die_vier_erlaubten_werte_getrimmt():
    form = {
        "objekt_id": " haus-b ",
        "vorlage": " drive:Vertrag.docx ",
        "format": "pdf",
        "ziel": " lokal ",
        "mieter_name": "Geheim",
        "anfrage": "Nicht merken",
    }
    assert merke("vertrag", form) == {
        "objekt_id": "haus-b",
        "vertrag_vorlage": "drive:Vertrag.docx",
        "format": "pdf",
        "ziel": "lokal",
    }
    assert merke("protokoll", form)["protokoll_vorlage"] == "drive:Vertrag.docx"


def test_merke_laesst_leere_werte_weg_und_prueft_relevante_typen():
    assert merke("vertrag", {"objekt_id": "   ", "format": "", "ziel": "drive", "vorlage": ""}) == {
        "ziel": "drive"
    }
    assert merke("vertrag", {}) == {}
    with pytest.raises(ValueError, match="objekt_id"):
        merke("vertrag", {"objekt_id": 5})
    with pytest.raises(ValueError, match="form"):
        merke("vertrag", [])


def test_eingaben_werden_nicht_veraendert():
    objekte = [dict(eintrag) for eintrag in OBJEKTE]
    vorlagen = {"lokal": ["Mietvertrag.docx"], "drive": []}
    letzte = {"objekt_id": "haus-b", "format": "pdf", "ziel": "lokal"}
    form = {"objekt_id": " haus-b ", "format": "pdf", "ziel": "lokal", "vorlage": "lokal:V.docx"}

    vorauswahl("vertrag", objekte, vorlagen, letzte)
    merke("vertrag", form)

    assert objekte == OBJEKTE
    assert vorlagen == {"lokal": ["Mietvertrag.docx"], "drive": []}
    assert letzte == {"objekt_id": "haus-b", "format": "pdf", "ziel": "lokal"}
    assert form == {
        "objekt_id": " haus-b ",
        "format": "pdf",
        "ziel": "lokal",
        "vorlage": "lokal:V.docx",
    }
