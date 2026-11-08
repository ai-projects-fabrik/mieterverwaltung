"""Tests fuer projekt.auswahl mit synthetischen Dateien."""

import json

import pytest

import projekt.auswahl as auswahl_modul
from projekt.auswahl import AUSWAHL_FELDER, auswahl_pfad, lade_auswahl, speichere_auswahl


def test_felder_sind_fest():
    assert AUSWAHL_FELDER == ("objekt_id", "vertrag_vorlage", "protokoll_vorlage", "format", "ziel")


def test_pfad_nutzt_lokalen_ordner_und_home(tmp_path):
    assert (
        auswahl_pfad({"objekte_datei": str(tmp_path / "daten" / "objekte.json")})
        == tmp_path / "daten" / "letzte_auswahl.json"
    )
    assert (
        auswahl_pfad({}, tmp_path)
        == tmp_path / "Documents" / "Mietverwaltung" / "letzte_auswahl.json"
    )
    assert not (tmp_path / "Documents").exists()


def test_pfad_meldet_ungueltige_einstellungen():
    with pytest.raises(ValueError, match="Einstellungen|objekte_datei"):
        auswahl_pfad([], None)
    with pytest.raises(ValueError, match="objekte_datei"):
        auswahl_pfad({"objekte_datei": 5})


def test_fehlende_datei_und_nicht_nutzbarer_pfad_ergeben_leer(tmp_path):
    assert lade_auswahl(tmp_path / "fehlt.json") == {}
    assert lade_auswahl(tmp_path) == {}
    assert lade_auswahl(None) == {}


@pytest.mark.parametrize(
    "inhalt",
    [b"{nicht json", b"[1, 2]", b"null", b'"text"', b"\xff\xfe", b"123"],
)
def test_kaputte_dateien_ergeben_leer(tmp_path, inhalt):
    datei = tmp_path / "a.json"
    datei.write_bytes(inhalt)
    assert lade_auswahl(datei) == {}


def test_laden_trimmt_und_ignoriert_unbekanntes_und_ungueltiges(tmp_path):
    datei = tmp_path / "a.json"
    datei.write_text(
        json.dumps(
            {
                "objekt_id": "  haus-a  ",
                "vertrag_vorlage": "lokal:V.docx",
                "protokoll_vorlage": "",
                "format": 3,
                "ziel": "drive",
                "fremd": "x",
                "kaputt": "a\x00b",
                "lang": "x" * 201,
            }
        ),
        encoding="utf-8",
    )
    assert lade_auswahl(datei) == {
        "objekt_id": "haus-a",
        "vertrag_vorlage": "lokal:V.docx",
        "ziel": "drive",
    }


def test_laden_nimmt_hoechstens_200_getrimmte_zeichen(tmp_path):
    datei = tmp_path / "a.json"
    datei.write_text(
        json.dumps({"ziel": "x" * 200, "format": " " + "x" * 200 + " "}), encoding="utf-8"
    )
    assert lade_auswahl(datei) == {"ziel": "x" * 200, "format": "x" * 200}


def test_speichern_trimmt_und_fuehrt_zusammen(tmp_path):
    datei = tmp_path / "daten" / "letzte_auswahl.json"
    speichere_auswahl(datei, {"objekt_id": " haus-a ", "format": "pdf"})
    speichere_auswahl(datei, {"format": "docx", "ziel": "lokal"})

    assert lade_auswahl(datei) == {"objekt_id": "haus-a", "format": "docx", "ziel": "lokal"}
    assert [pfad.name for pfad in datei.parent.iterdir()] == ["letzte_auswahl.json"]


def test_speichern_prueft_daten_und_laesst_datei_unveraendert(tmp_path):
    datei = tmp_path / "a.json"
    speichere_auswahl(datei, {"ziel": "drive"})
    vorher = datei.read_bytes()

    for schlecht in (
        [],
        "text",
        {"unbekannt": "x"},
        {5: "x"},
        {"ziel": ""},
        {"ziel": "   "},
        {"ziel": 5},
        {"ziel": None},
        {"ziel": "x" * 201},
        {"ziel": "a\x00b"},
    ):
        with pytest.raises(ValueError):
            speichere_auswahl(datei, schlecht)

    assert datei.read_bytes() == vorher
    assert [pfad.name for pfad in tmp_path.iterdir()] == ["a.json"]


def test_speichern_nennt_unbekanntes_feld(tmp_path):
    with pytest.raises(ValueError, match="unbekannt"):
        speichere_auswahl(tmp_path / "a.json", {"unbekannt": "x"})
    assert not (tmp_path / "a.json").exists()


def test_speichern_prueft_vor_dem_anlegen(tmp_path):
    datei = tmp_path / "neu" / "a.json"
    with pytest.raises(ValueError, match="ziel"):
        speichere_auswahl(datei, {"ziel": 5})
    assert not datei.parent.exists()


def test_speichern_ergaenzt_kaputte_vorherige_datei(tmp_path):
    datei = tmp_path / "a.json"
    datei.write_text("{nicht json", encoding="utf-8")
    speichere_auswahl(datei, {"ziel": "drive"})
    assert lade_auswahl(datei) == {"ziel": "drive"}


def test_speichern_laesst_alte_datei_bei_schreibfehler_unveraendert(tmp_path, monkeypatch):
    datei = tmp_path / "a.json"
    speichere_auswahl(datei, {"ziel": "drive"})
    vorher = datei.read_bytes()

    def fehlschlag(*_args, **_kwargs):
        raise OSError("Testschreibfehler")

    monkeypatch.setattr(auswahl_modul.os, "replace", fehlschlag)
    with pytest.raises(ValueError, match="pfad"):
        speichere_auswahl(datei, {"format": "pdf"})

    assert datei.read_bytes() == vorher
    assert [pfad.name for pfad in tmp_path.iterdir()] == ["a.json"]


def test_speichern_meldet_nicht_kodierbaren_text_ohne_temp_rest(tmp_path):
    datei = tmp_path / "a.json"
    speichere_auswahl(datei, {"ziel": "drive"})
    vorher = datei.read_bytes()
    with pytest.raises(ValueError, match="pfad"):
        speichere_auswahl(datei, {"ziel": "\ud800"})
    assert datei.read_bytes() == vorher
    assert [pfad.name for pfad in tmp_path.iterdir()] == ["a.json"]


def test_speichern_meldet_nicht_nutzbaren_ordner(tmp_path):
    blockiert = tmp_path / "blockiert"
    blockiert.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="pfad"):
        speichere_auswahl(blockiert / "a.json", {"ziel": "drive"})


def test_speichern_prueft_den_pfad(tmp_path):
    with pytest.raises(ValueError, match="pfad"):
        speichere_auswahl(None, {"ziel": "drive"})
    with pytest.raises(ValueError, match="pfad"):
        speichere_auswahl("a\x00b.json", {"ziel": "drive"})


def test_eingabe_wird_nicht_veraendert(tmp_path):
    daten = {"objekt_id": " haus-a "}
    speichere_auswahl(tmp_path / "a.json", daten)
    assert daten == {"objekt_id": " haus-a "}
