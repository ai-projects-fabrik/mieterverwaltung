"""Tests fuer projekt.felder mit synthetischen Vertragsdaten."""

import pytest

from projekt.felder import FELDER, normalisiere


def test_felder_haben_feste_reihenfolge():
    assert FELDER == (
        "mieter_name",
        "wohnraumnutzer_name",
        "objekt",
        "mietbeginn",
        "mietende",
        "miete_netto",
        "nebenkosten",
        "kaution",
    )


def test_fehlende_felder_sind_erlaubt():
    assert normalisiere({}) == {}
    assert normalisiere({"objekt": "Weg 1"}) == {"objekt": "Weg 1"}


def test_eingabe_wird_nicht_veraendert():
    eingabe = {"mieter_name": "  Anna Muster ", "miete_netto": "CHF 1'250.50"}
    normalisiere(eingabe)
    assert eingabe == {
        "mieter_name": "  Anna Muster ",
        "miete_netto": "CHF 1'250.50",
    }


@pytest.mark.parametrize("feld", ["mieter_name", "wohnraumnutzer_name", "objekt"])
def test_textfelder_werden_getrimmt(feld):
    assert normalisiere({feld: "  Musterweg 1  "}) == {feld: "Musterweg 1"}


@pytest.mark.parametrize("feld", ["mieter_name", "wohnraumnutzer_name", "objekt"])
def test_textfelder_erlauben_ein_bis_120_zeichen(feld):
    assert normalisiere({feld: "x"}) == {feld: "x"}
    assert normalisiere({feld: "x" * 120}) == {feld: "x" * 120}
    with pytest.raises(ValueError, match=feld):
        normalisiere({feld: "x" * 121})


@pytest.mark.parametrize(
    ("feld", "wert"),
    [
        ("mieter_name", ""),
        ("mieter_name", "   "),
        ("mieter_name", 5),
        ("mieter_name", "{{kaution}}"),
        ("wohnraumnutzer_name", ""),
        ("wohnraumnutzer_name", "   "),
        ("wohnraumnutzer_name", 5),
        ("wohnraumnutzer_name", "{{kaution}}"),
        ("objekt", "Weg }} 1"),
    ],
)
def test_ungueltige_textfelder_nennen_das_feld(feld, wert):
    with pytest.raises(ValueError, match=feld):
        normalisiere({feld: wert})


@pytest.mark.parametrize(
    "feld",
    ["mietbeginn", "mietende"],
)
@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [
        ("2026-12-01", "01.12.2026"),
        ("2026-02-28", "28.02.2026"),
        ("1.12.2026", "01.12.2026"),
        ("01.12.2026", "01.12.2026"),
        ("29.02.2024", "29.02.2024"),
        ("0001-01-01", "01.01.0001"),
    ],
)
def test_gueltige_daten_werden_normalisiert(feld, wert, erwartet):
    assert normalisiere({feld: wert}) == {feld: erwartet}


@pytest.mark.parametrize(
    "feld",
    ["mietbeginn", "mietende"],
)
@pytest.mark.parametrize(
    "wert",
    [
        "2026-02-29",
        "2023-02-29",
        "2026-04-31",
        "2026-13-01",
        "2026-00-01",
        "2026-1-1",
        "1.2.26",
        "01/12/2026",
        "morgen",
        "",
        None,
        20260101,
    ],
)
def test_ungueltige_daten_nennen_das_feld(feld, wert):
    with pytest.raises(ValueError, match=feld):
        normalisiere({feld: wert})


def test_mietende_wird_nicht_gegen_mietbeginn_geprueft():
    assert normalisiere({"mietbeginn": "2027-01-01", "mietende": "2026-01-01"}) == {
        "mietbeginn": "01.01.2027",
        "mietende": "01.01.2026",
    }


@pytest.mark.parametrize(
    ("feld", "wert", "erwartet"),
    [
        ("miete_netto", 0, "0.00"),
        ("miete_netto", 1250, "1'250.00"),
        ("miete_netto", 1000000, "1'000'000.00"),
        ("miete_netto", "0", "0.00"),
        ("miete_netto", "0.5", "0.50"),
        ("miete_netto", "1250.5", "1'250.50"),
        ("miete_netto", "1250.50", "1'250.50"),
        ("miete_netto", "1'250", "1'250.00"),
        ("miete_netto", "1'234'567.89", "1'234'567.89"),
        ("miete_netto", "CHF 1250.00", "1'250.00"),
        ("nebenkosten", 200, "200.00"),
        ("kaution", "3000", "3'000.00"),
    ],
)
def test_gueltige_betraege_werden_normalisiert(feld, wert, erwartet):
    assert normalisiere({feld: wert}) == {feld: erwartet}


@pytest.mark.parametrize(
    "wert",
    [
        -1,
        "-5",
        "-0.01",
        "12,50",
        "1234.567",
        "1.234,56",
        "1'23.00",
        "1'2345.00",
        "'1250.00",
        "1250.",
        ".50",
        "1 250.00",
        "CHF1250.00",
        "CHF -1.00",
        "chf 1.00",
        " 1250.00",
        "1250.00 ",
        "1_250.00",
    ],
)
def test_ungueltige_betraege_nennen_das_feld(wert):
    with pytest.raises(ValueError, match="miete_netto"):
        normalisiere({"miete_netto": wert})


@pytest.mark.parametrize("wert", [1250.5, True, False, None, [1250]])
def test_betraege_mit_falschem_typ_sind_ungueltig(wert):
    with pytest.raises(ValueError, match="miete_netto"):
        normalisiere({"miete_netto": wert})


def test_unbekanntes_feld_nennt_den_namen():
    with pytest.raises(ValueError, match="unbekannt"):
        normalisiere({"unbekannt": "x"})


def test_nicht_dict_nennt_daten():
    for roh in (None, "text", [("mieter_name", "A")]):
        with pytest.raises(ValueError, match="daten"):
            normalisiere(roh)
