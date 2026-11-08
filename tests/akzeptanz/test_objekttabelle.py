"""Akzeptanztest (spec-first) fuer projekt.objekttabelle (Ziel `mv-objekttabelle`)."""

import importlib.util

import pytest

if importlib.util.find_spec("projekt.objekttabelle") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.objekttabelle import (  # noqa: E402
    SPALTEN,
    neue_id,
    objekte_aus_zeilen,
    zeilen_aus_formular,
)


def test_spalten_haben_deutsche_beschriftungen():
    assert SPALTEN == (
        ("bezeichnung", "Bezeichnung"),
        ("miete_netto", "Miete netto (CHF)"),
        ("nebenkosten", "Nebenkosten (CHF)"),
        ("kaution", "Kaution (CHF)"),
    )


def test_neue_id():
    assert neue_id("Musterweg 1, Zürich", []) == "musterweg-1-zuerich"
    assert neue_id("Haus A", ["haus-a"]) == "haus-a-2"
    assert neue_id("Haus A", ["haus-a", "haus-a-2"]) == "haus-a-3"
    assert neue_id("§§§", []) == "objekt"
    lang = neue_id("a" * 100, [])
    assert len(lang) <= 40 and lang.startswith("aaaa")
    assert len(neue_id("a" * 100, [lang])) <= 40
    with pytest.raises(ValueError):
        neue_id(5, [])


def test_zeilen_aus_formular_sortiert_nach_nummer_und_ignoriert_fremdes():
    form = {
        "zeile_10_bezeichnung": "Zehn",
        "zeile_2_bezeichnung": " Zwei ",
        "zeile_2_miete_netto": "1000",
        "zeile_2_id": "zwei",
        "zeile_x_bezeichnung": "falsch",
        "zeile_3_unbekannt": "x",
        "drive_ordner": "G:",
    }
    assert zeilen_aus_formular(form) == [
        {"bezeichnung": "Zwei", "miete_netto": "1000", "id": "zwei"},
        {"bezeichnung": "Zehn"},
    ]


def test_neue_zeile_bekommt_automatisch_eine_id():
    zeilen = [{"bezeichnung": "Haus A", "miete_netto": "1250.5", "kaution": "CHF 3000"}]
    assert objekte_aus_zeilen(zeilen, []) == [
        {"id": "haus-a", "bezeichnung": "Haus A", "miete_netto": "1'250.50", "kaution": "3'000.00"}
    ]


def test_bestehende_id_bleibt_auch_bei_umbenennung():
    bestehend = [{"id": "weg-1", "bezeichnung": "Musterweg 1"}]
    zeilen = [{"id": "weg-1", "bezeichnung": "Musterweg 1a", "nebenkosten": "200"}]
    assert objekte_aus_zeilen(zeilen, bestehend) == [
        {"id": "weg-1", "bezeichnung": "Musterweg 1a", "nebenkosten": "200.00"}
    ]


def test_leere_zeilen_entfallen_und_entfernen_objekte():
    bestehend = [{"id": "a", "bezeichnung": "A"}, {"id": "b", "bezeichnung": "B"}]
    zeilen = [{"id": "a", "bezeichnung": "A"}, {"id": "b"}, {}, {"bezeichnung": "  "}]
    assert objekte_aus_zeilen(zeilen, bestehend) == [{"id": "a", "bezeichnung": "A"}]
    assert objekte_aus_zeilen([], bestehend) == []


def test_gleiche_bezeichnung_ergibt_verschiedene_ids_und_ergebnis_ist_sortiert():
    zeilen = [{"bezeichnung": "Zebra"}, {"bezeichnung": "Haus"}, {"bezeichnung": "Haus"}]
    assert [o["id"] for o in objekte_aus_zeilen(zeilen, [])] == ["haus", "haus-2", "zebra"]


def test_unbekannte_id_wird_nicht_uebernommen():
    ergebnis = objekte_aus_zeilen([{"id": "frei-erfunden", "bezeichnung": "Haus"}], [])
    assert ergebnis == [{"id": "haus", "bezeichnung": "Haus"}]


def test_fehler_nennen_zeile_und_deutsche_beschriftung():
    with pytest.raises(ValueError, match=r"Zeile 2.*Miete netto \(CHF\)"):
        objekte_aus_zeilen([{"bezeichnung": "A"}, {"bezeichnung": "B", "miete_netto": "viel"}], [])
    with pytest.raises(ValueError, match=r"Zeile 1.*Kaution \(CHF\)"):
        objekte_aus_zeilen([{"bezeichnung": "A", "kaution": "-5"}], [])
    with pytest.raises(ValueError, match=r"Zeile 1.*Bezeichnung"):
        objekte_aus_zeilen([{"miete_netto": "100"}], [])
    with pytest.raises(ValueError, match="zeilen"):
        objekte_aus_zeilen("x", [])
    with pytest.raises(ValueError, match="Zeile 1"):
        objekte_aus_zeilen(["x"], [])
