"""Akzeptanztest (spec-first) fuer projekt.bericht: Beispiele aus dem Ziel `mv-bericht`."""

import importlib.util

import pytest

if importlib.util.find_spec("projekt.bericht") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.bericht import bericht  # noqa: E402

ALT = {"mieter_name": "Bert Beispiel", "miete_netto": "1'000.00", "objekt": "Weg 1"}


def test_geaenderte_felder_in_fester_reihenfolge():
    neu = {**ALT, "miete_netto": "1'250.00", "mieter_name": "Anna Muster"}
    assert bericht(ALT, neu) == (
        "mieter_name: Bert Beispiel -> Anna Muster\nmiete_netto: 1'000.00 -> 1'250.00"
    )


def test_neue_und_entfernte_felder():
    neu = {"mieter_name": "Bert Beispiel", "objekt": "Weg 1", "kaution": "3'000.00"}
    assert bericht(ALT, neu) == "miete_netto: 1'000.00 -> (leer)\nkaution: (leer) -> 3'000.00"


def test_ohne_aenderung():
    assert bericht(ALT, dict(ALT)) == "keine Aenderungen"
    assert bericht({}, {}) == "keine Aenderungen"


def test_unbekanntes_feld_oder_kein_dict_ist_value_error():
    for alt, neu in (({"x": "1"}, {}), ({}, {"x": "1"}), (None, {}), ({}, "text")):
        with pytest.raises(ValueError):
            bericht(alt, neu)
