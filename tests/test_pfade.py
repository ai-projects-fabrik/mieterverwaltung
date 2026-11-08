"""Tests fuer projekt.pfade mit synthetischen Ordnern und Pfaden."""

from pathlib import Path

import pytest

from projekt.einstellungen import DRIVE_STANDARD, normalisiere_einstellungen
from projekt.pfade import (
    drive_ordner,
    einstellungen_aus_ordnern,
    erkenne_drive,
    lege_ordner_an,
    lokaler_ordner,
    standard_lokal,
)


def test_standard_lokal_nutzt_home_oder_benutzerordner(tmp_path):
    assert standard_lokal(tmp_path) == str(tmp_path / "Documents" / "Mietverwaltung")
    assert standard_lokal(str(tmp_path)) == str(tmp_path / "Documents" / "Mietverwaltung")
    assert Path(standard_lokal()).name == "Mietverwaltung"
    assert not (tmp_path / "Documents").exists()


def test_standard_lokal_meldet_ungueltiges_home():
    with pytest.raises(ValueError, match="home"):
        standard_lokal(5)


def test_erkenne_drive_nimmt_den_ersten_ordner_und_ignoriert_dateien(tmp_path):
    datei = tmp_path / "datei"
    datei.write_text("x", encoding="utf-8")
    erster = tmp_path / "erster"
    zweiter = tmp_path / "zweiter"
    erster.mkdir()
    zweiter.mkdir()

    assert erkenne_drive((str(datei), str(erster), str(zweiter))) == str(erster)
    assert erkenne_drive((str(tmp_path / "fehlt"),)) == DRIVE_STANDARD
    assert erkenne_drive(()) == DRIVE_STANDARD
    assert erkenne_drive(None) == DRIVE_STANDARD


def test_erkenne_drive_meldet_nicht_text_kandidaten():
    with pytest.raises(ValueError, match="Google-Drive-Ordner"):
        erkenne_drive((5,))


def test_drive_ordner_bevorzugt_getrimmte_einstellung(tmp_path):
    vorhanden = tmp_path / "vorhanden"
    vorhanden.mkdir()
    daten = {"drive_wurzel": f"  {tmp_path / 'gespeichert'}  "}
    assert drive_ordner(daten, (str(vorhanden),)) == str(tmp_path / "gespeichert")


def test_drive_ordner_erkennt_ohne_gespeicherte_wurzel(tmp_path):
    vorhanden = tmp_path / "vorhanden"
    vorhanden.mkdir()
    assert drive_ordner({}, (str(vorhanden),)) == str(vorhanden)
    assert drive_ordner({"drive_wurzel": "   "}, (str(vorhanden),)) == str(vorhanden)
    assert drive_ordner({"drive_wurzel": ""}, ()) == DRIVE_STANDARD


@pytest.mark.parametrize("daten", [None, [], "text"])
def test_drive_ordner_braucht_ein_dict(daten):
    with pytest.raises(ValueError, match="Einstellungen"):
        drive_ordner(daten)


@pytest.mark.parametrize("wert", [5, None, ["x"]])
def test_drive_ordner_meldet_ungueltige_wurzel(wert):
    with pytest.raises(ValueError, match="drive_wurzel"):
        drive_ordner({"drive_wurzel": wert})


def test_drive_ordner_lehnt_nul_ab():
    with pytest.raises(ValueError, match="drive_wurzel"):
        drive_ordner({"drive_wurzel": "G:/a\x00b"})


def test_lokaler_ordner_nimmt_elternordner_der_objektdatei(tmp_path):
    daten = {"objekte_datei": f"  {tmp_path / 'daten' / 'objekte.json'}  "}
    assert lokaler_ordner(daten) == str(tmp_path / "daten")
    assert lokaler_ordner({"objekte_datei": "objekte.json"}) == "."


def test_lokaler_ordner_faellt_auf_standard_zurueck(tmp_path):
    erwartet = str(tmp_path / "Documents" / "Mietverwaltung")
    assert lokaler_ordner({}, tmp_path) == erwartet
    assert lokaler_ordner({"objekte_datei": ""}, tmp_path) == erwartet
    assert lokaler_ordner({"objekte_datei": "   "}, tmp_path) == erwartet


@pytest.mark.parametrize("daten", [None, [], "text"])
def test_lokaler_ordner_braucht_ein_dict(daten):
    with pytest.raises(ValueError, match="Einstellungen"):
        lokaler_ordner(daten)


@pytest.mark.parametrize("wert", [5, False, ["x"]])
def test_lokaler_ordner_meldet_ungueltige_objektdatei(wert):
    with pytest.raises(ValueError, match="objekte_datei"):
        lokaler_ordner({"objekte_datei": wert})


def test_lokaler_ordner_lehnt_nul_ab():
    with pytest.raises(ValueError, match="objekte_datei"):
        lokaler_ordner({"objekte_datei": "a\x00b.json"})


def test_einstellungen_aus_ordnern_trimmt_und_leitet_ab(tmp_path):
    drive = tmp_path / "drive"
    lokal = tmp_path / "lokal"
    ergebnis = einstellungen_aus_ordnern(f"  {drive}  ", f"  {lokal}  ")

    assert ergebnis == {
        "drive_wurzel": str(drive),
        "objekte_datei": str(lokal / "objekte.json"),
        "vorlagen_lokal": str(lokal / "Vorlagen"),
        "ausgabe_lokal": str(lokal / "Ausgabe"),
        "vorlagen_drive": str(drive / "Mietverwaltung" / "Vorlagen"),
        "ausgabe_drive": str(drive / "Mietverwaltung" / "Ausgabe"),
    }
    assert normalisiere_einstellungen(ergebnis) == ergebnis
    assert not drive.exists()
    assert not lokal.exists()


def test_einstellungen_aus_ordnern_akzeptiert_300_zeichen(tmp_path):
    drive = "d" * 300
    lokal = "l" * 300
    ergebnis = einstellungen_aus_ordnern(drive, lokal)
    assert ergebnis["drive_wurzel"] == drive
    assert ergebnis["objekte_datei"] == str(Path(lokal) / "objekte.json")


@pytest.mark.parametrize("drive", ["", "   ", "x" * 301, "a\x00b", 5, None])
def test_einstellungen_aus_ordnern_meldet_drive(drive):
    with pytest.raises(ValueError, match="Google-Drive-Ordner"):
        einstellungen_aus_ordnern(drive, "lokal")


@pytest.mark.parametrize("lokal", ["", "   ", "x" * 301, "a\x00b", 5, None])
def test_einstellungen_aus_ordnern_meldet_lokal(lokal):
    with pytest.raises(ValueError, match="Lokaler Ordner"):
        einstellungen_aus_ordnern("drive", lokal)


def test_lege_ordner_an_legt_ziele_samt_eltern_an(tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    daten = einstellungen_aus_ordnern(str(drive), str(tmp_path / "lokal"))
    erwartet = {
        tmp_path / "lokal" / "Vorlagen",
        tmp_path / "lokal" / "Ausgabe",
        drive / "Mietverwaltung" / "Vorlagen",
        drive / "Mietverwaltung" / "Ausgabe",
        drive / "MV-zu-pdf",
    }

    assert {Path(p) for p in lege_ordner_an(daten)} == erwartet
    assert all(pfad.is_dir() for pfad in erwartet)
    assert (tmp_path / "lokal").is_dir()
    assert (drive / "Mietverwaltung").is_dir()
    assert lege_ordner_an(daten) == []


def test_lege_ordner_an_prueft_alle_felder_vor_dem_anlegen(tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    daten = einstellungen_aus_ordnern(str(drive), str(tmp_path / "lokal"))
    for feld in ("vorlagen_lokal", "ausgabe_lokal", "vorlagen_drive", "ausgabe_drive"):
        unvollstaendig = dict(daten)
        del unvollstaendig[feld]
        with pytest.raises(ValueError, match=feld):
            lege_ordner_an(unvollstaendig)
    assert list(drive.iterdir()) == []
    assert not (tmp_path / "lokal").exists()


def test_lege_ordner_an_meldet_falsche_typen_und_leere_werte(tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    daten = einstellungen_aus_ordnern(str(drive), str(tmp_path / "lokal"))
    for wert in (5, None, "", "   "):
        fehlerhaft = dict(daten)
        fehlerhaft["vorlagen_lokal"] = wert
        with pytest.raises(ValueError, match="vorlagen_lokal"):
            lege_ordner_an(fehlerhaft)
    assert list(drive.iterdir()) == []


def test_lege_ordner_an_ohne_drive_legt_nichts_an(tmp_path):
    daten = einstellungen_aus_ordnern(str(tmp_path / "fehlt"), str(tmp_path / "lokal"))
    with pytest.raises(ValueError, match="Google-Drive-Ordner"):
        lege_ordner_an(daten)
    assert not (tmp_path / "fehlt").exists()
    assert not (tmp_path / "lokal").exists()


def test_lege_ordner_an_meldet_drive_als_datei(tmp_path):
    drive = tmp_path / "drive"
    drive.write_text("x", encoding="utf-8")
    daten = einstellungen_aus_ordnern(str(drive), str(tmp_path / "lokal"))
    with pytest.raises(ValueError, match="Google-Drive-Ordner"):
        lege_ordner_an(daten)
    assert not (tmp_path / "lokal").exists()


def test_lege_ordner_an_meldet_existierende_datei_am_ziel(tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    daten = einstellungen_aus_ordnern(str(drive), str(tmp_path / "lokal"))
    ziel = Path(daten["vorlagen_lokal"])
    ziel.parent.mkdir(parents=True)
    ziel.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="vorlagen_lokal"):
        lege_ordner_an(daten)
    assert not Path(daten["ausgabe_lokal"]).exists()


@pytest.mark.parametrize("daten", [None, [], "text"])
def test_lege_ordner_an_braucht_ein_dict(daten):
    with pytest.raises(ValueError, match="Einstellungen"):
        lege_ordner_an(daten)
