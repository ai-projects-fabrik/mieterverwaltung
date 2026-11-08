"""Akzeptanztest (spec-first) fuer projekt.auswahl (Ziel `mv-auswahl`)."""

import importlib.util
import json
from pathlib import Path

import pytest

if importlib.util.find_spec("projekt.auswahl") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.auswahl import (  # noqa: E402
    AUSWAHL_FELDER,
    auswahl_pfad,
    lade_auswahl,
    speichere_auswahl,
)


def test_felder():
    assert AUSWAHL_FELDER == ("objekt_id", "vertrag_vorlage", "protokoll_vorlage", "format", "ziel")


def test_pfad_liegt_im_lokalen_ordner(tmp_path):
    e = {"objekte_datei": str(tmp_path / "daten" / "objekte.json")}
    assert auswahl_pfad(e) == tmp_path / "daten" / "letzte_auswahl.json"
    assert (
        auswahl_pfad({}, tmp_path)
        == tmp_path / "Documents" / "Mietverwaltung" / "letzte_auswahl.json"
    )


def test_fehlende_oder_defekte_datei_ergibt_leer(tmp_path):
    assert lade_auswahl(tmp_path / "nichts.json") == {}
    kaputt = tmp_path / "kaputt.json"
    kaputt.write_text("{nicht json", encoding="utf-8")
    assert lade_auswahl(kaputt) == {}
    kaputt.write_text("[1, 2]", encoding="utf-8")
    assert lade_auswahl(kaputt) == {}


def test_speichern_legt_ordner_an_und_fuehrt_zusammen(tmp_path):
    pfad = tmp_path / "neu" / "a.json"
    speichere_auswahl(pfad, {"objekt_id": " haus-a ", "format": "pdf"})
    assert lade_auswahl(pfad) == {"objekt_id": "haus-a", "format": "pdf"}
    speichere_auswahl(pfad, {"format": "docx", "ziel": "lokal"})
    assert lade_auswahl(pfad) == {"objekt_id": "haus-a", "format": "docx", "ziel": "lokal"}
    assert [p.name for p in pfad.parent.iterdir()] == ["a.json"]


def test_speichern_prueft_eingaben_und_laesst_datei_unveraendert(tmp_path):
    pfad = tmp_path / "a.json"
    speichere_auswahl(pfad, {"ziel": "drive"})
    vorher = pfad.read_bytes()
    for schlecht in (
        {"unbekannt": "x"},
        {"ziel": ""},
        {"ziel": 5},
        {"ziel": "x" * 201},
        {"ziel": "a\x00b"},
    ):
        with pytest.raises(ValueError):
            speichere_auswahl(pfad, schlecht)
    with pytest.raises(ValueError, match="unbekannt"):
        speichere_auswahl(pfad, {"unbekannt": "x"})
    with pytest.raises(ValueError):
        speichere_auswahl(pfad, [])
    assert pfad.read_bytes() == vorher


def test_laden_ignoriert_unbekanntes_und_ungueltiges(tmp_path):
    pfad = Path(tmp_path) / "a.json"
    pfad.write_text(
        json.dumps({"ziel": "drive", "fremd": "x", "format": 3, "objekt_id": "  "}),
        encoding="utf-8",
    )
    assert lade_auswahl(pfad) == {"ziel": "drive"}
