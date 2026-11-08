"""Akzeptanztest (spec-first) fuer projekt.pfade (Ziel `mv-pfade`)."""

import importlib.util
from pathlib import Path

import pytest

if importlib.util.find_spec("projekt.pfade") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.einstellungen import DRIVE_STANDARD, normalisiere_einstellungen  # noqa: E402
from projekt.pfade import (  # noqa: E402
    drive_ordner,
    einstellungen_aus_ordnern,
    erkenne_drive,
    lege_ordner_an,
    lokaler_ordner,
    standard_lokal,
)


def test_standard_lokal_liegt_unter_dokumente(tmp_path):
    assert Path(standard_lokal(tmp_path)) == tmp_path / "Documents" / "Mietverwaltung"
    assert Path(standard_lokal()).name == "Mietverwaltung"


def test_erkenne_drive_nimmt_ersten_vorhandenen_ordner(tmp_path):
    (tmp_path / "zweiter").mkdir()
    kandidaten = (str(tmp_path / "fehlt"), str(tmp_path / "zweiter"), str(tmp_path))
    assert erkenne_drive(kandidaten) == str(tmp_path / "zweiter")
    assert erkenne_drive((str(tmp_path / "fehlt"),)) == DRIVE_STANDARD
    assert erkenne_drive(()) == DRIVE_STANDARD


def test_einstellungen_aus_ordnern_leitet_alles_ab(tmp_path):
    drive, lokal = tmp_path / "drive", tmp_path / "lokal"
    e = einstellungen_aus_ordnern(str(drive), str(lokal))
    assert e == {
        "drive_wurzel": str(drive),
        "objekte_datei": str(lokal / "objekte.json"),
        "vorlagen_lokal": str(lokal / "Vorlagen"),
        "ausgabe_lokal": str(lokal / "Ausgabe"),
        "vorlagen_drive": str(drive / "Mietverwaltung" / "Vorlagen"),
        "ausgabe_drive": str(drive / "Mietverwaltung" / "Ausgabe"),
    }
    assert normalisiere_einstellungen(e) == e


def test_einstellungen_aus_ordnern_trimmt_und_prueft(tmp_path):
    e = einstellungen_aus_ordnern(f"  {tmp_path / 'd'}  ", str(tmp_path / "l"))
    assert e["drive_wurzel"] == str(tmp_path / "d")
    with pytest.raises(ValueError, match="Google-Drive-Ordner"):
        einstellungen_aus_ordnern("  ", str(tmp_path))
    with pytest.raises(ValueError, match="Lokaler Ordner"):
        einstellungen_aus_ordnern(str(tmp_path), "")
    with pytest.raises(ValueError, match="Lokaler Ordner"):
        einstellungen_aus_ordnern(str(tmp_path), "x" * 301)
    with pytest.raises(ValueError, match="Google-Drive-Ordner"):
        einstellungen_aus_ordnern(5, str(tmp_path))


def test_rueckwaerts_aus_alten_einstellungen(tmp_path):
    alt = {"objekte_datei": str(tmp_path / "daten" / "o.json"), "drive_wurzel": "Z:\\Laufwerk"}
    assert lokaler_ordner(alt) == str(tmp_path / "daten")
    assert drive_ordner(alt) == "Z:\\Laufwerk"
    assert lokaler_ordner({}, tmp_path) == standard_lokal(tmp_path)
    assert drive_ordner({}, (str(tmp_path),)) == str(tmp_path)
    assert drive_ordner({}, ()) == DRIVE_STANDARD


def test_lege_ordner_an_legt_alles_an_und_meldet_nur_neue(tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    e = einstellungen_aus_ordnern(str(drive), str(tmp_path / "lokal"))
    neu = lege_ordner_an(e)
    erwartet = {
        tmp_path / "lokal" / "Vorlagen",
        tmp_path / "lokal" / "Ausgabe",
        drive / "Mietverwaltung" / "Vorlagen",
        drive / "Mietverwaltung" / "Ausgabe",
        drive / "MV-zu-pdf",
    }
    assert {Path(p) for p in neu} == erwartet
    assert all(p.is_dir() for p in erwartet)
    assert lege_ordner_an(e) == []


def test_lege_ordner_an_ohne_drive_legt_nichts_an(tmp_path):
    e = einstellungen_aus_ordnern(str(tmp_path / "gibt-es-nicht"), str(tmp_path / "lokal"))
    with pytest.raises(ValueError, match="Google-Drive-Ordner"):
        lege_ordner_an(e)
    assert not (tmp_path / "lokal").exists()
    with pytest.raises(ValueError, match="vorlagen_lokal"):
        lege_ordner_an({"drive_wurzel": str(tmp_path)})
