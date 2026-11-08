import json

import pytest

from projekt.objekte import (
    entferne_objekt,
    lade_objekte,
    normalisiere_objekt,
    objekt_als_felder,
    setze_objekt,
    speichere_objekte,
)


def objekt(**aenderungen):
    daten = {"id": "haus-1", "bezeichnung": "Musterweg 1"}
    daten.update(aenderungen)
    return daten


@pytest.mark.parametrize("objekt_id", ["a", "0", "a_1", "haus-1", "a" * 40])
def test_id_grenzwerte_werden_akzeptiert(objekt_id):
    assert normalisiere_objekt(objekt(id=f"  {objekt_id}  "))["id"] == objekt_id


@pytest.mark.parametrize(
    "objekt_id",
    ["", " ", "_a", "-a", "A", "Haus", "a b", "ä", "a" * 41, None, 1, True],
)
def test_ungueltige_ids_nennen_das_feld(objekt_id):
    with pytest.raises(ValueError, match="id"):
        normalisiere_objekt(objekt(id=objekt_id))


def test_normalisierung_prueft_bezeichnung_und_betraege():
    assert normalisiere_objekt(
        objekt(bezeichnung="  Haus  ", miete_netto="CHF 1'200", nebenkosten=0, kaution=3600)
    ) == {
        "id": "haus-1",
        "bezeichnung": "Haus",
        "miete_netto": "1'200.00",
        "nebenkosten": "0.00",
        "kaution": "3'600.00",
    }

    for aenderung in (
        {"bezeichnung": " "},
        {"bezeichnung": "x" * 121},
        {"bezeichnung": "{{mieter_name}}"},
        {"miete_netto": -1},
        {"miete_netto": 1.5},
        {"kaution": "viel"},
        {"farbe": "rot"},
    ):
        with pytest.raises(ValueError):
            normalisiere_objekt(objekt(**aenderung))


def test_fehlende_pflichtfelder_und_falsche_typen():
    with pytest.raises(ValueError, match="id"):
        normalisiere_objekt({"bezeichnung": "Haus"})
    with pytest.raises(ValueError, match="bezeichnung"):
        normalisiere_objekt({"id": "haus-1"})
    with pytest.raises(ValueError, match="bezeichnung"):
        normalisiere_objekt(objekt(bezeichnung=1))
    with pytest.raises(ValueError, match="objekt"):
        normalisiere_objekt(["haus-1"])


def test_normalisierung_veraendert_die_eingabe_nicht():
    daten = objekt(miete_netto=1200)
    kopie = dict(daten)
    normalisiere_objekt(daten)
    assert daten == kopie


def test_objekt_als_felder_normalisiert_und_laesst_id_weg():
    assert objekt_als_felder(objekt(miete_netto=1200)) == {
        "objekt": "Musterweg 1",
        "miete_netto": "1'200.00",
    }
    with pytest.raises(ValueError, match="bezeichnung"):
        objekt_als_felder({"id": "haus-1", "bezeichnung": ""})


def test_setze_objekt_ist_rein_normalisierend_und_sortiert():
    start = [objekt(id="b", bezeichnung="B"), objekt(id="a", bezeichnung="A")]
    alt = [dict(eintrag) for eintrag in start]
    neu = setze_objekt(start, objekt(id="b", bezeichnung="Neu", kaution=500))

    assert start == alt
    assert [eintrag["id"] for eintrag in neu] == ["a", "b"]
    assert neu[1] == {"id": "b", "bezeichnung": "Neu", "kaution": "500.00"}


def test_setze_objekt_prueft_liste_und_doppelte_ids():
    with pytest.raises(ValueError, match="objekte"):
        setze_objekt((objekt(),), objekt())
    with pytest.raises(ValueError, match="id"):
        setze_objekt([objekt(), objekt(bezeichnung="Anders")], objekt(id="neu"))
    with pytest.raises(ValueError, match="kaution"):
        setze_objekt([objekt()], objekt(id="neu", kaution=-1))


def test_entferne_objekt_ist_rein_und_prueft_id():
    start = [objekt(id="b"), objekt(id="a")]
    assert entferne_objekt(start, "a") == [{"id": "b", "bezeichnung": "Musterweg 1"}]
    assert [eintrag["id"] for eintrag in start] == ["b", "a"]
    with pytest.raises(ValueError, match="id"):
        entferne_objekt(start, "fehlt")
    with pytest.raises(ValueError, match="id"):
        entferne_objekt(start, "Ungueltig")


def test_lade_objekte_fehlende_datei_und_sortierung(tmp_path):
    datei = tmp_path / "objekte.json"
    assert lade_objekte(datei) == []
    datei.write_text(
        json.dumps([objekt(id="b"), objekt(id="a", miete_netto=1200)]), encoding="utf-8"
    )
    assert lade_objekte(datei) == [
        {"id": "a", "bezeichnung": "Musterweg 1", "miete_netto": "1'200.00"},
        {"id": "b", "bezeichnung": "Musterweg 1"},
    ]


@pytest.mark.parametrize(
    "inhalt",
    [
        "{kaputt",
        "{}",
        "[1]",
        '[{"id": "A", "bezeichnung": "Haus"}]',
        '[{"id": "a", "bezeichnung": "A"}, {"id": "a", "bezeichnung": "B"}]',
    ],
)
def test_lade_objekte_lehnt_ungueltige_dateien_ab(tmp_path, inhalt):
    datei = tmp_path / "objekte.json"
    datei.write_text(inhalt, encoding="utf-8")
    with pytest.raises(ValueError):
        lade_objekte(datei)


def test_lade_objekte_lehnt_ordner_und_nicht_utf8_ab(tmp_path):
    with pytest.raises(ValueError):
        lade_objekte(tmp_path)
    datei = tmp_path / "objekte.json"
    datei.write_bytes(b"\xff")
    with pytest.raises(ValueError):
        lade_objekte(datei)


def test_speichern_und_laden_roundtrip(tmp_path):
    datei = tmp_path / "objekte.json"
    speichere_objekte(datei, [objekt(id="b"), objekt(id="a", bezeichnung="Zürich")])

    assert [eintrag["id"] for eintrag in lade_objekte(datei)] == ["a", "b"]
    assert "Zürich" in datei.read_text(encoding="utf-8")
    assert [pfad.name for pfad in tmp_path.iterdir()] == ["objekte.json"]


def test_speichern_prueft_vor_dem_schreiben(tmp_path):
    datei = tmp_path / "objekte.json"
    speichere_objekte(datei, [objekt()])
    vorher = datei.read_bytes()

    with pytest.raises(ValueError, match="id"):
        speichere_objekte(datei, [objekt(), objekt(bezeichnung="B")])
    with pytest.raises(ValueError, match="miete_netto"):
        speichere_objekte(datei, [objekt(miete_netto="viel")])
    assert datei.read_bytes() == vorher


def test_speichern_legt_ordner_nicht_an(tmp_path):
    with pytest.raises(ValueError, match="Ordner"):
        speichere_objekte(tmp_path / "fehlt" / "objekte.json", [objekt()])
    assert not (tmp_path / "fehlt").exists()


def test_speichern_bleibt_bei_replace_fehler_atomar(tmp_path, monkeypatch):
    datei = tmp_path / "objekte.json"
    speichere_objekte(datei, [objekt()])
    vorher = datei.read_bytes()

    def fehler(*args, **kwargs):
        raise OSError("Testfehler")

    monkeypatch.setattr("projekt.objekte.os.replace", fehler)
    with pytest.raises(ValueError, match="geschrieben"):
        speichere_objekte(datei, [objekt(bezeichnung="Neu")])

    assert datei.read_bytes() == vorher
    assert [pfad.name for pfad in tmp_path.iterdir()] == ["objekte.json"]


def test_speichern_lehnt_ordner_als_ziel_ab(tmp_path):
    with pytest.raises(ValueError, match="Ordner"):
        speichere_objekte(tmp_path, [objekt()])
