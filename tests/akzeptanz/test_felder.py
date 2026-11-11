"""Akzeptanztest (spec-first) fuer projekt.felder: Beispiele aus dem Ziel `mv-felder`."""

import importlib.util

import pytest

if importlib.util.find_spec("projekt.felder") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.felder import FELDER, normalisiere  # noqa: E402

GUELTIG = [
    ({}, {}),
    ({"mieter_name": "  Anna Muster "}, {"mieter_name": "Anna Muster"}),
    ({"mietbeginn": "2026-12-01"}, {"mietbeginn": "01.12.2026"}),
    ({"mietbeginn": "1.12.2026"}, {"mietbeginn": "01.12.2026"}),
    ({"miete_netto": 1250}, {"miete_netto": "1'250.00"}),
    ({"miete_netto": "1250.5"}, {"miete_netto": "1'250.50"}),
    ({"miete_netto": "CHF 1'250.50"}, {"miete_netto": "1'250.50"}),
    ({"kaution": "0"}, {"kaution": "0.00"}),
    (
        {"objekt": "Musterweg 1, 8000 Zuerich", "nebenkosten": 200},
        {"objekt": "Musterweg 1, 8000 Zuerich", "nebenkosten": "200.00"},
    ),
]

UNGUELTIG = [
    {"mietbeginn": "2026-02-30"},
    {"mietbeginn": "morgen"},
    {"miete_netto": "-5"},
    {"miete_netto": "12,50"},
    {"miete_netto": "1234.567"},
    {"miete_netto": 1250.5},
    {"miete_netto": True},
    {"miete_netto": None},
    {"mieter_name": ""},
    {"mieter_name": "   "},
    {"mieter_name": "x" * 121},
    {"mieter_name": 5},
    {"mieter_name": "{{kaution}}"},
    {"objekt": "Weg }} 1"},
    {"unbekannt": "x"},
]


# Ziel `mv-wohnraumnutzer`: bis das Feld umgesetzt ist, gilt die bisherige Reihenfolge.
WOHNRAUMNUTZER = "wohnraumnutzer_name" in FELDER
# Ziel `mv-feld-mietende`: bis das Feld umgesetzt ist, gilt die bisherige Reihenfolge.
MIETENDE = "mietende" in FELDER


def test_felder_reihenfolge_ist_fest():
    erwartet = (
        "mieter_name",
        "wohnraumnutzer_name",
        "objekt",
        "mietbeginn",
        "mietende",
        "miete_netto",
        "nebenkosten",
        "kaution",
    )
    if not WOHNRAUMNUTZER:
        erwartet = tuple(f for f in erwartet if f != "wohnraumnutzer_name")
    if not MIETENDE:
        erwartet = tuple(f for f in erwartet if f != "mietende")
    assert FELDER == erwartet


@pytest.mark.skipif(not WOHNRAUMNUTZER, reason="Feld wohnraumnutzer_name noch nicht umgesetzt")
def test_wohnraumnutzer_name_ist_ein_pruefter_textfeld():
    assert normalisiere({"wohnraumnutzer_name": "  Karl Kind "}) == {
        "wohnraumnutzer_name": "Karl Kind"
    }
    assert normalisiere({"mieter_name": "Anna Muster"}) == {"mieter_name": "Anna Muster"}
    for roh in ("", "   ", "x" * 121, 5, "{{kaution}}", "Weg }} 1"):
        with pytest.raises(ValueError, match="wohnraumnutzer_name"):
            normalisiere({"wohnraumnutzer_name": roh})


@pytest.mark.parametrize(("eingabe", "erwartet"), GUELTIG)
def test_gueltige_eingaben_werden_normalisiert(eingabe, erwartet):
    assert normalisiere(eingabe) == erwartet


@pytest.mark.parametrize("eingabe", UNGUELTIG)
def test_ungueltige_eingaben_sind_value_error(eingabe):
    with pytest.raises(ValueError):
        normalisiere(eingabe)


def test_kein_dict_ist_value_error():
    for roh in (None, "text", [("mieter_name", "A")]):
        with pytest.raises(ValueError):
            normalisiere(roh)


def test_eingabe_wird_nicht_veraendert():
    eingabe = {"miete_netto": "1250"}
    normalisiere(eingabe)
    assert eingabe == {"miete_netto": "1250"}


@pytest.mark.skipif(not MIETENDE, reason="Feld mietende noch nicht umgesetzt")
def test_mietende_ist_ein_datum_wie_mietbeginn():
    assert normalisiere({"mietende": "2027-12-31"}) == {"mietende": "31.12.2027"}
    assert normalisiere({"mietende": "1.2.2028"}) == {"mietende": "01.02.2028"}
    assert normalisiere({"mietbeginn": "2026-12-01"}) == {"mietbeginn": "01.12.2026"}
    for roh in ("2027-02-30", "irgendwann", "", 5, None):
        with pytest.raises(ValueError, match="mietende"):
            normalisiere({"mietende": roh})
