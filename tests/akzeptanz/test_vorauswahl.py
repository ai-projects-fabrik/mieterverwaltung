"""Akzeptanztest (spec-first) fuer projekt.vorauswahl (Ziel `mv-vorauswahl`)."""

import importlib.util

import pytest

if importlib.util.find_spec("projekt.vorauswahl") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.vorauswahl import merke, vorauswahl  # noqa: E402

OBJEKTE = [{"id": "a", "bezeichnung": "Haus A"}, {"id": "b", "bezeichnung": "Haus B"}]
VORLAGEN = {
    "lokal": ["Allgemein.docx", "Mietvertrag 2026.docx"],
    "drive": ["Uebergabeprotokoll.docx"],
}


def test_ohne_letzte_auswahl_gelten_die_standards():
    assert vorauswahl("vertrag", OBJEKTE, VORLAGEN, {}) == {
        "objekt_id": "a",
        "vorlage": "lokal:Mietvertrag 2026.docx",
        "format": "docx+pdf",
        "ziel": "drive",
    }
    assert (
        vorauswahl("protokoll", OBJEKTE, VORLAGEN, {})["vorlage"] == "drive:Uebergabeprotokoll.docx"
    )


def test_vorlage_ohne_passenden_namen_ist_die_erste():
    assert (
        vorauswahl("vertrag", OBJEKTE, {"lokal": ["x.docx", "y.docx"]}, {})["vorlage"]
        == "lokal:x.docx"
    )
    assert vorauswahl("vertrag", OBJEKTE, {"drive": ["z.docx"]}, {})["vorlage"] == "drive:z.docx"


def test_letzte_auswahl_gewinnt_wenn_sie_noch_gueltig_ist():
    letzte = {
        "objekt_id": "b",
        "vertrag_vorlage": "lokal:Allgemein.docx",
        "protokoll_vorlage": "drive:Uebergabeprotokoll.docx",
        "format": "pdf",
        "ziel": "lokal",
    }
    assert vorauswahl("vertrag", OBJEKTE, VORLAGEN, letzte) == {
        "objekt_id": "b",
        "vorlage": "lokal:Allgemein.docx",
        "format": "pdf",
        "ziel": "lokal",
    }
    assert (
        vorauswahl("protokoll", OBJEKTE, VORLAGEN, letzte)["vorlage"]
        == "drive:Uebergabeprotokoll.docx"
    )


def test_veraltete_oder_ungueltige_letzte_auswahl_faellt_auf_standard_zurueck():
    letzte = {
        "objekt_id": "weg",
        "vertrag_vorlage": "lokal:geloescht.docx",
        "format": "xls",
        "ziel": "x",
    }
    assert vorauswahl("vertrag", OBJEKTE, VORLAGEN, letzte) == vorauswahl(
        "vertrag", OBJEKTE, VORLAGEN, {}
    )


def test_ohne_objekte_und_vorlagen_sind_die_werte_leer():
    assert vorauswahl("vertrag", [], {}, {}) == {
        "objekt_id": "",
        "vorlage": "",
        "format": "docx+pdf",
        "ziel": "drive",
    }
    assert vorauswahl("vertrag", [], {"lokal": []}, {})["vorlage"] == ""


def test_unbekannte_art_ist_ein_fehler():
    with pytest.raises(ValueError, match="art"):
        vorauswahl("brief", OBJEKTE, VORLAGEN, {})
    with pytest.raises(ValueError, match="art"):
        merke("brief", {})


def test_merke_waehlt_nur_vorhandene_werte_und_benennt_die_vorlage_nach_art():
    form = {
        "objekt_id": " b ",
        "vorlage": "drive:V.docx",
        "format": "pdf",
        "ziel": "",
        "mieter_name": "Geheim",
    }
    assert merke("vertrag", form) == {
        "objekt_id": "b",
        "vertrag_vorlage": "drive:V.docx",
        "format": "pdf",
    }
    assert merke("protokoll", form)["protokoll_vorlage"] == "drive:V.docx"
    assert merke("vertrag", {}) == {}
