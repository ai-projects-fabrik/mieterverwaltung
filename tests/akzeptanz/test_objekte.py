"""Akzeptanztest (spec-first) fuer projekt.objekte (Ziel `mv-objekte`)."""

import importlib.util
import json

import pytest

if importlib.util.find_spec("projekt.objekte") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.objekte import (  # noqa: E402
    entferne_objekt,
    lade_objekte,
    normalisiere_objekt,
    objekt_als_felder,
    setze_objekt,
    speichere_objekte,
)

VOLL = {
    "id": "weg-1",
    "bezeichnung": "Musterweg 1, 8000 Zürich",
    "miete_netto": 1200,
    "nebenkosten": "200",
    "kaution": "CHF 3'600",
}
VOLL_NORM = {
    "id": "weg-1",
    "bezeichnung": "Musterweg 1, 8000 Zürich",
    "miete_netto": "1'200.00",
    "nebenkosten": "200.00",
    "kaution": "3'600.00",
}


def test_normalisiere_objekt_vollstaendig_und_minimal():
    assert normalisiere_objekt(VOLL) == VOLL_NORM
    minimal = {"id": " a_1 ", "bezeichnung": "  Haus  "}
    assert normalisiere_objekt(minimal) == {"id": "a_1", "bezeichnung": "Haus"}
    assert VOLL["miete_netto"] == 1200


@pytest.mark.parametrize(
    ("aenderung", "feld"),
    [
        ({"id": "Weg 1"}, "id"),
        ({"id": ""}, "id"),
        ({"id": "-x"}, "id"),
        ({"id": "a" * 41}, "id"),
        ({"bezeichnung": ""}, "bezeichnung"),
        ({"bezeichnung": "Haus {{x}}"}, "bezeichnung"),
        ({"bezeichnung": "x" * 121}, "bezeichnung"),
        ({"miete_netto": "viel"}, "miete_netto"),
        ({"kaution": -1}, "kaution"),
        ({"farbe": "rot"}, "farbe"),
    ],
)
def test_ungueltige_objekte_sind_value_error_mit_feldname(aenderung, feld):
    with pytest.raises(ValueError, match=feld):
        normalisiere_objekt({**VOLL, **aenderung})


def test_fehlende_pflichtfelder_und_falscher_typ():
    with pytest.raises(ValueError, match="id"):
        normalisiere_objekt({"bezeichnung": "Haus"})
    with pytest.raises(ValueError, match="bezeichnung"):
        normalisiere_objekt({"id": "a"})
    with pytest.raises(ValueError):
        normalisiere_objekt(["id"])


def test_objekt_als_felder_liefert_vertragsfelder_ohne_id():
    assert objekt_als_felder(VOLL_NORM) == {
        "objekt": "Musterweg 1, 8000 Zürich",
        "miete_netto": "1'200.00",
        "nebenkosten": "200.00",
        "kaution": "3'600.00",
    }
    assert objekt_als_felder({"id": "a", "bezeichnung": "Haus"}) == {"objekt": "Haus"}


def test_setze_und_entferne_objekt_sind_rein_und_sortiert():
    a = {"id": "b", "bezeichnung": "B"}
    b = {"id": "a", "bezeichnung": "A"}
    start = [a]
    neu = setze_objekt(start, b)
    assert [o["id"] for o in neu] == ["a", "b"]
    assert start == [a]
    ersetzt = setze_objekt(neu, {"id": "b", "bezeichnung": "Neu", "kaution": 500})
    assert ersetzt[1] == {"id": "b", "bezeichnung": "Neu", "kaution": "500.00"}
    assert len(ersetzt) == 2
    assert [o["id"] for o in entferne_objekt(ersetzt, "a")] == ["b"]
    with pytest.raises(ValueError, match="id"):
        entferne_objekt(ersetzt, "gibt-es-nicht")


def test_speichern_und_laden_roundtrip(tmp_path):
    datei = tmp_path / "objekte.json"
    assert lade_objekte(datei) == []
    objekte = [VOLL_NORM, {"id": "a", "bezeichnung": "Haus A"}]
    speichere_objekte(datei, objekte)
    assert [o["id"] for o in lade_objekte(datei)] == ["a", "weg-1"]
    assert lade_objekte(str(datei))[1] == VOLL_NORM
    text = datei.read_text(encoding="utf-8")
    assert "Zürich" in text
    assert isinstance(json.loads(text), list)
    assert [p.name for p in tmp_path.iterdir()] == ["objekte.json"]


def test_speichern_ist_atomar_und_prueft_vorher(tmp_path):
    datei = tmp_path / "objekte.json"
    speichere_objekte(datei, [VOLL_NORM])
    vorher = datei.read_text(encoding="utf-8")
    doppelt = [{"id": "a", "bezeichnung": "A"}, {"id": "a", "bezeichnung": "B"}]
    with pytest.raises(ValueError, match="id"):
        speichere_objekte(datei, doppelt)
    with pytest.raises(ValueError, match="miete_netto"):
        speichere_objekte(datei, [{"id": "z", "bezeichnung": "Z", "miete_netto": "x"}])
    assert datei.read_text(encoding="utf-8") == vorher
    with pytest.raises(ValueError):
        speichere_objekte(tmp_path / "fehlt" / "o.json", [VOLL_NORM])
    assert not (tmp_path / "fehlt").exists()


@pytest.mark.parametrize("inhalt", ["{kaputt", "{}", '[{"id": "Ungültig!"}]', "[1]"])
def test_unlesbare_dateien_sind_value_error(tmp_path, inhalt):
    datei = tmp_path / "objekte.json"
    datei.write_text(inhalt, encoding="utf-8")
    with pytest.raises(ValueError):
        lade_objekte(datei)
