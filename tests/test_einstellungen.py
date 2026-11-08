"""Tests fuer projekt.einstellungen mit synthetischen Pfaden und Dateien."""

import json
from pathlib import Path

import pytest

import projekt.einstellungen as einstellungen_modul
from projekt.einstellungen import (
    DRIVE_STANDARD,
    EINSTELLUNGEN_FELDER,
    einstellungen_pfad,
    lade_einstellungen,
    normalisiere_einstellungen,
    ordner,
    pdf_ordner,
    speichere_einstellungen,
)


def test_felder_haben_feste_reihenfolge():
    assert EINSTELLUNGEN_FELDER == (
        "objekte_datei",
        "vorlagen_lokal",
        "vorlagen_drive",
        "ausgabe_lokal",
        "ausgabe_drive",
        "drive_wurzel",
    )


def test_normalisierung_trimmt_und_entfernt_leere_werte():
    eingabe = {"vorlagen_lokal": "  C:/Vorlagen  ", "ausgabe_lokal": "   "}
    assert normalisiere_einstellungen(eingabe) == {"vorlagen_lokal": "C:/Vorlagen"}
    assert eingabe == {"vorlagen_lokal": "  C:/Vorlagen  ", "ausgabe_lokal": "   "}


def test_normalisierung_akzeptiert_400_zeichen_und_lehnt_401_ab():
    assert normalisiere_einstellungen({"ausgabe_lokal": "x" * 400}) == {"ausgabe_lokal": "x" * 400}
    with pytest.raises(ValueError, match="ausgabe_lokal"):
        normalisiere_einstellungen({"ausgabe_lokal": "x" * 401})


@pytest.mark.parametrize(
    ("daten", "feld"),
    [
        ({"objekte_datei": 1}, "objekte_datei"),
        ({"vorlagen_drive": None}, "vorlagen_drive"),
        ({"ausgabe_drive": "a\x00b"}, "ausgabe_drive"),
        ({"unbekannt": "x"}, "unbekannt"),
        ({1: "x"}, "1"),
    ],
)
def test_ungueltige_einstellungen_nennen_das_feld(daten, feld):
    with pytest.raises(ValueError, match=feld):
        normalisiere_einstellungen(daten)


@pytest.mark.parametrize("roh", [None, [], "text", [("ausgabe_lokal", "x")]])
def test_nicht_dict_ist_value_error(roh):
    with pytest.raises(ValueError, match="Einstellungen"):
        normalisiere_einstellungen(roh)


def test_fehlende_datei_liefert_leere_einstellungen(tmp_path):
    assert lade_einstellungen(tmp_path / "fehlt.json") == {}
    assert not (tmp_path / "fehlt.json").exists()


def test_laden_trimmt_und_prueft_die_datei(tmp_path):
    datei = tmp_path / "einstellungen.json"
    datei.write_text('{"vorlagen_lokal": "  C:/V  ", "ausgabe_lokal": ""}', encoding="utf-8")
    assert lade_einstellungen(datei) == {"vorlagen_lokal": "C:/V"}


@pytest.mark.parametrize(
    "inhalt",
    [b"{kaputt", b"[]", b'{"unbekannt": "x"}', b'{"ausgabe_lokal": 1}', b"\xff"],
)
def test_ungueltige_dateien_sind_value_error(tmp_path, inhalt):
    datei = tmp_path / "einstellungen.json"
    datei.write_bytes(inhalt)
    with pytest.raises(ValueError, match="Einstellungsdatei"):
        lade_einstellungen(datei)


def test_nicht_lesbare_datei_ist_value_error(tmp_path):
    verzeichnis = tmp_path / "einstellungen.json"
    verzeichnis.mkdir()
    with pytest.raises(ValueError, match="Einstellungsdatei"):
        lade_einstellungen(verzeichnis)


def test_speichern_legt_ordner_an_und_laedt_wieder(tmp_path):
    datei = tmp_path / "neu" / "einstellungen.json"
    speichere_einstellungen(datei, {"drive_wurzel": "G:/Mein Drive", "ausgabe_lokal": "  "})
    assert lade_einstellungen(datei) == {"drive_wurzel": "G:/Mein Drive"}
    assert [pfad.name for pfad in datei.parent.iterdir()] == ["einstellungen.json"]
    assert json.loads(datei.read_text(encoding="utf-8")) == {"drive_wurzel": "G:/Mein Drive"}


def test_speichern_prueft_vor_dem_anlegen(tmp_path):
    datei = tmp_path / "neu" / "einstellungen.json"
    with pytest.raises(ValueError, match="ausgabe_lokal"):
        speichere_einstellungen(datei, {"ausgabe_lokal": 5})
    assert not datei.parent.exists()


def test_speichern_laesst_alte_datei_bei_schreibfehler_unveraendert(tmp_path, monkeypatch):
    datei = tmp_path / "einstellungen.json"
    speichere_einstellungen(datei, {"ausgabe_lokal": "alt"})
    vorher = datei.read_bytes()

    def fehlschlag(*_args, **_kwargs):
        raise OSError("Testschreibfehler")

    monkeypatch.setattr(einstellungen_modul.os, "replace", fehlschlag)
    with pytest.raises(ValueError, match="Einstellungsdatei"):
        speichere_einstellungen(datei, {"ausgabe_lokal": "neu"})
    assert datei.read_bytes() == vorher
    assert [pfad.name for pfad in tmp_path.iterdir()] == ["einstellungen.json"]


def test_speichern_meldet_nicht_kodierbaren_text_ohne_temp_rest(tmp_path):
    datei = tmp_path / "einstellungen.json"
    speichere_einstellungen(datei, {"ausgabe_lokal": "alt"})
    vorher = datei.read_bytes()
    with pytest.raises(ValueError, match="Einstellungsdatei"):
        speichere_einstellungen(datei, {"ausgabe_lokal": "\ud800"})
    assert datei.read_bytes() == vorher
    assert [pfad.name for pfad in tmp_path.iterdir()] == ["einstellungen.json"]


def test_speichern_meldet_nicht_nutzbaren_ordner(tmp_path):
    blockiert = tmp_path / "blockiert"
    blockiert.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Ordner"):
        speichere_einstellungen(blockiert / "einstellungen.json", {"ausgabe_lokal": "x"})


def test_einstellungen_pfad_aus_umgebung(tmp_path):
    datei = tmp_path / "eigen.json"
    assert einstellungen_pfad({"MIETER_EINSTELLUNGEN": str(datei)}, home=tmp_path) == datei
    assert not datei.exists()


def test_einstellungen_pfad_standard_und_leere_umgebung(tmp_path):
    standard = tmp_path / ".mieterverwaltung" / "einstellungen.json"
    assert einstellungen_pfad({}, home=tmp_path) == standard
    assert einstellungen_pfad({"MIETER_EINSTELLUNGEN": ""}, home=tmp_path) == standard
    assert not standard.parent.exists()


def test_einstellungen_pfad_nutzt_standard_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MIETER_EINSTELLUNGEN", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert einstellungen_pfad() == tmp_path / ".mieterverwaltung" / "einstellungen.json"


@pytest.mark.parametrize(
    ("art", "ort", "erwartet"),
    [
        ("vorlagen", "lokal", "C:/Vorlagen"),
        ("vorlagen", "drive", "G:/Drive/Vorlagen"),
        ("ausgabe", "lokal", "C:/Ausgabe"),
        ("ausgabe", "drive", "G:/Drive/Ausgabe"),
    ],
)
def test_ordner_liefert_den_gewaehlten_pfad(art, ort, erwartet):
    daten = {
        "vorlagen_lokal": "C:/Vorlagen",
        "vorlagen_drive": "G:/Drive/Vorlagen",
        "ausgabe_lokal": "C:/Ausgabe",
        "ausgabe_drive": "G:/Drive/Ausgabe",
    }
    assert ordner(daten, art, ort) == Path(erwartet)


@pytest.mark.parametrize(("art", "ort"), [("sonstiges", "lokal"), ("vorlagen", "cloud")])
def test_ordner_nennt_ungueltige_art_oder_ort(art, ort):
    with pytest.raises(ValueError, match="art|ort"):
        ordner({}, art, ort)


def test_ordner_nennt_fehlende_einstellung():
    with pytest.raises(ValueError, match="ausgabe_drive"):
        ordner({"ausgabe_lokal": "C:/Ausgabe"}, "ausgabe", "drive")
    with pytest.raises(ValueError, match="ausgabe_drive"):
        ordner({"ausgabe_drive": "   "}, "ausgabe", "drive")
    with pytest.raises(ValueError, match="ausgabe_drive"):
        ordner({"ausgabe_drive": 5}, "ausgabe", "drive")


def test_pdf_ordner_nutzt_die_drive_wurzel():
    daten = {"drive_wurzel": "G:/Mein Drive"}
    assert pdf_ordner(daten, "eingang") == Path("G:/Mein Drive/MV-zu-pdf")
    assert pdf_ordner(daten, "ausgabe") == Path("G:/Mein Drive/MV-pdf")
    assert pdf_ordner(daten, "erledigt") == Path("G:/Mein Drive/MV-erledigt")


@pytest.mark.parametrize("daten", [{}, {"drive_wurzel": ""}, {"drive_wurzel": "   "}])
def test_pdf_ordner_nutzt_den_standard_ohne_wurzel(daten):
    assert pdf_ordner(daten, "ausgabe") == Path(DRIVE_STANDARD) / "MV-pdf"
    assert DRIVE_STANDARD == "G:\\My Drive"


def test_pdf_ordner_fehler_nennen_art_oder_wurzel():
    with pytest.raises(ValueError, match="art"):
        pdf_ordner({}, "sonstiges")
    with pytest.raises(ValueError, match="drive_wurzel"):
        pdf_ordner({"drive_wurzel": 5}, "eingang")
    with pytest.raises(ValueError, match="drive_wurzel"):
        pdf_ordner({"drive_wurzel": None}, "eingang")
