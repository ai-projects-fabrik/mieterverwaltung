"""Tests fuer projekt.bericht mit synthetischen Vertragsdaten."""

import pytest

from projekt.bericht import bericht
from projekt.felder import FELDER

ALT = {
    "mieter_name": "Bert Beispiel",
    "objekt": "Weg 1",
    "mietbeginn": "01.01.2026",
    "miete_netto": "1'000.00",
    "nebenkosten": "200.00",
    "kaution": "3'000.00",
}


def test_geaenderte_felder_stehen_in_der_reihenfolge_von_felder():
    neu = {
        "kaution": "3'500.00",
        "objekt": "Weg 2",
        "mieter_name": "Anna Muster",
        "miete_netto": "1'250.00",
        "nebenkosten": "200.00",
        "mietbeginn": "01.01.2026",
    }
    assert bericht(ALT, neu) == (
        "mieter_name: Bert Beispiel -> Anna Muster\n"
        "objekt: Weg 1 -> Weg 2\n"
        "miete_netto: 1'000.00 -> 1'250.00\n"
        "kaution: 3'000.00 -> 3'500.00"
    )
    assert [zeile.split(":", 1)[0] for zeile in bericht(ALT, neu).splitlines()] == [
        "mieter_name",
        "objekt",
        "miete_netto",
        "kaution",
    ]


def test_unveraenderte_felder_fehlen_und_ohne_unterschied_keine_aenderungen():
    assert bericht(ALT, dict(ALT)) == "keine Aenderungen"
    assert bericht({}, {}) == "keine Aenderungen"


def test_fehlende_werte_werden_als_leer_dargestellt():
    neu = {"mieter_name": "Bert Beispiel", "objekt": "Weg 1", "kaution": "3'000.00"}
    assert bericht(ALT, neu) == (
        "mietbeginn: 01.01.2026 -> (leer)\n"
        "miete_netto: 1'000.00 -> (leer)\n"
        "nebenkosten: 200.00 -> (leer)"
    )
    assert bericht(neu, ALT) == (
        "mietbeginn: (leer) -> 01.01.2026\n"
        "miete_netto: (leer) -> 1'000.00\n"
        "nebenkosten: (leer) -> 200.00"
    )


def test_fehlendes_feld_auf_beiden_seiten_ist_keine_aenderung():
    assert bericht({"objekt": "Weg 1"}, {"objekt": "Weg 1"}) == "keine Aenderungen"


def test_ergebnis_hat_kein_zeilenende():
    ergebnis = bericht(ALT, {**ALT, "objekt": "Weg 2"})
    assert ergebnis == "objekt: Weg 1 -> Weg 2"
    assert not ergebnis.endswith("\n")


def test_leerzeichen_werden_nicht_normalisiert():
    assert bericht({"objekt": "Weg 1"}, {"objekt": "Weg 1 "}) == "objekt: Weg 1 -> Weg 1 "


def test_eingaben_werden_nicht_veraendert():
    alt = {"objekt": "Weg 1"}
    neu = {"objekt": "Weg 2"}
    bericht(alt, neu)
    assert alt == {"objekt": "Weg 1"}
    assert neu == {"objekt": "Weg 2"}


@pytest.mark.parametrize("daten", [None, "text", [("objekt", "Weg 1")]])
def test_nicht_dict_ist_value_error(daten):
    with pytest.raises(ValueError, match="dict"):
        bericht(daten, {})
    with pytest.raises(ValueError, match="dict"):
        bericht({}, daten)


def test_unbekanntes_feld_ist_value_error_und_nennt_den_namen():
    with pytest.raises(ValueError, match="unbekannt"):
        bericht({"unbekannt": "x"}, {})
    with pytest.raises(ValueError, match="unbekannt"):
        bericht({}, {"unbekannt": "x"})


@pytest.mark.parametrize("wert", [None, 1, 1.5, True, []])
def test_nicht_text_werte_sind_value_error_und_nennen_das_feld(wert):
    with pytest.raises(ValueError, match="objekt"):
        bericht({"objekt": wert}, {})
    with pytest.raises(ValueError, match="objekt"):
        bericht({}, {"objekt": wert})


def test_alle_felder_aus_felder_werden_beruecksichtigt():
    alt = {feld: f"alt-{feld}" for feld in FELDER}
    neu = {feld: f"neu-{feld}" for feld in FELDER}
    assert bericht(alt, neu).splitlines() == [
        f"{feld}: alt-{feld} -> neu-{feld}" for feld in FELDER
    ]
