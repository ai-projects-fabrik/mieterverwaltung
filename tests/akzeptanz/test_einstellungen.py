"""Akzeptanztest (spec-first) fuer projekt.einstellungen (Ziel `mv-einstellungen`)."""

import importlib.util
import json
from pathlib import Path

import pytest

if importlib.util.find_spec("projekt.einstellungen") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.einstellungen import (  # noqa: E402
    EINSTELLUNGEN_FELDER,
    einstellungen_pfad,
    lade_einstellungen,
    normalisiere_einstellungen,
    ordner,
    pdf_ordner,
    speichere_einstellungen,
)

VOLL = {
    "objekte_datei": "C:/Mieter/objekte.json",
    "vorlagen_lokal": "C:/Mieter/vorlagen",
    "vorlagen_drive": "G:/Mein Drive/Vorlagen",
    "ausgabe_lokal": "C:/Mieter/ausgabe",
    "ausgabe_drive": "G:/Mein Drive/Ausgabe",
    "pdf_eingang": "G:/Mein Drive/zu-pdf",
    "pdf_ausgabe": "G:/Mein Drive/pdf-fertig",
}


def test_felder_und_normalisierung():
    assert EINSTELLUNGEN_FELDER == (
        "objekte_datei",
        "vorlagen_lokal",
        "vorlagen_drive",
        "ausgabe_lokal",
        "ausgabe_drive",
        "pdf_eingang",
        "pdf_ausgabe",
    )
    assert normalisiere_einstellungen(VOLL) == VOLL
    assert normalisiere_einstellungen({"ausgabe_lokal": "  C:/x  "}) == {"ausgabe_lokal": "C:/x"}
    assert normalisiere_einstellungen({"ausgabe_lokal": "", "vorlagen_lokal": "   "}) == {}
    assert normalisiere_einstellungen({}) == {}


@pytest.mark.parametrize(
    ("daten", "feld"),
    [
        ({"objekte_datei": 5}, "objekte_datei"),
        ({"vorlagen_lokal": None}, "vorlagen_lokal"),
        ({"ausgabe_lokal": "x" * 401}, "ausgabe_lokal"),
        ({"ausgabe_drive": "a\x00b"}, "ausgabe_drive"),
        ({"unbekannt": "x"}, "unbekannt"),
    ],
)
def test_ungueltige_einstellungen_sind_value_error_mit_feldname(daten, feld):
    with pytest.raises(ValueError, match=feld):
        normalisiere_einstellungen(daten)
    with pytest.raises(ValueError):
        normalisiere_einstellungen(["x"])


def test_speichern_und_laden(tmp_path):
    datei = tmp_path / "neu" / "einstellungen.json"
    assert lade_einstellungen(datei) == {}
    speichere_einstellungen(datei, {**VOLL, "vorlagen_lokal": "  "})
    erwartet = {k: v for k, v in VOLL.items() if k != "vorlagen_lokal"}
    assert lade_einstellungen(datei) == erwartet
    assert json.loads(datei.read_text(encoding="utf-8")) == erwartet
    assert [p.name for p in datei.parent.iterdir()] == ["einstellungen.json"]


def test_speichern_prueft_vorher_und_aendert_nichts_bei_fehler(tmp_path):
    datei = tmp_path / "einstellungen.json"
    speichere_einstellungen(datei, VOLL)
    vorher = datei.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="ausgabe_lokal"):
        speichere_einstellungen(datei, {"ausgabe_lokal": 5})
    assert datei.read_text(encoding="utf-8") == vorher


@pytest.mark.parametrize("inhalt", ["{kaputt", "[]", '{"unbekannt": "x"}', '{"ausgabe_lokal": 1}'])
def test_unlesbare_dateien_sind_value_error(tmp_path, inhalt):
    datei = tmp_path / "einstellungen.json"
    datei.write_text(inhalt, encoding="utf-8")
    with pytest.raises(ValueError):
        lade_einstellungen(datei)


def test_einstellungen_pfad(tmp_path):
    eigener = {"MIETER_EINSTELLUNGEN": str(tmp_path / "x.json")}
    assert einstellungen_pfad(eigener, home=tmp_path) == tmp_path / "x.json"
    standard = tmp_path / ".mieterverwaltung" / "einstellungen.json"
    assert einstellungen_pfad({}, home=tmp_path) == standard
    assert einstellungen_pfad({"MIETER_EINSTELLUNGEN": ""}, home=tmp_path) == standard
    assert isinstance(einstellungen_pfad({}, home=tmp_path), Path)
    assert einstellungen_pfad({}).name == "einstellungen.json"


def test_ordner_nach_art_und_ort():
    assert ordner(VOLL, "vorlagen", "lokal") == Path("C:/Mieter/vorlagen")
    assert ordner(VOLL, "vorlagen", "drive") == Path("G:/Mein Drive/Vorlagen")
    assert ordner(VOLL, "ausgabe", "lokal") == Path("C:/Mieter/ausgabe")
    assert ordner(VOLL, "ausgabe", "drive") == Path("G:/Mein Drive/Ausgabe")


def test_ordner_fehler():
    with pytest.raises(ValueError, match="ausgabe_drive"):
        ordner({"ausgabe_lokal": "x"}, "ausgabe", "drive")
    with pytest.raises(ValueError, match="art"):
        ordner(VOLL, "sonstiges", "lokal")
    with pytest.raises(ValueError, match="ort"):
        ordner(VOLL, "vorlagen", "cloud")


def test_pdf_ordner():
    assert pdf_ordner(VOLL, "eingang") == Path("G:/Mein Drive/zu-pdf")
    assert pdf_ordner(VOLL, "ausgabe") == Path("G:/Mein Drive/pdf-fertig")
    with pytest.raises(ValueError, match="pdf_eingang"):
        pdf_ordner({"pdf_ausgabe": "x"}, "eingang")
    with pytest.raises(ValueError, match="art"):
        pdf_ordner(VOLL, "sonstiges")
