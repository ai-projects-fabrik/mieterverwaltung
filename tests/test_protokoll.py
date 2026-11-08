"""Tests fuer projekt.protokoll mit synthetischen Protokolldaten."""

import pytest

from projekt.protokoll import PROTOKOLL_FELDER, normalisiere_protokoll


def test_felder_haben_feste_reihenfolge():
    assert PROTOKOLL_FELDER == (
        "mieter_name",
        "objekt",
        "uebergabedatum",
        "art",
        "zaehler_strom",
        "zaehler_wasser",
        "schluessel_anzahl",
        "bemerkungen",
    )


def test_fehlende_felder_sind_erlaubt():
    assert normalisiere_protokoll({}) == {}
    assert normalisiere_protokoll({"art": "Auszug"}) == {"art": "Auszug"}


def test_eingabe_wird_nicht_veraendert():
    eingabe = {
        "mieter_name": "  Anna Muster ",
        "zaehler_strom": "007",
        "bemerkungen": "Kratzer \r\n im Flur",
    }
    normalisiere_protokoll(eingabe)
    assert eingabe == {
        "mieter_name": "  Anna Muster ",
        "zaehler_strom": "007",
        "bemerkungen": "Kratzer \r\n im Flur",
    }


@pytest.mark.parametrize("feld", ["mieter_name", "objekt"])
def test_textfelder_werden_wie_vertragsfelder_geprueft(feld):
    assert normalisiere_protokoll({feld: "  Musterweg 1  "}) == {feld: "Musterweg 1"}
    assert normalisiere_protokoll({feld: "x" * 120}) == {feld: "x" * 120}

    for wert in ("", "   ", "x" * 121, "{{kaution}}", 5, None):
        with pytest.raises(ValueError, match=feld):
            normalisiere_protokoll({feld: wert})


@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [
        ("2026-02-01", "01.02.2026"),
        ("1.2.2026", "01.02.2026"),
        ("01.02.2026", "01.02.2026"),
        ("29.02.2024", "29.02.2024"),
        ("0001-01-01", "01.01.0001"),
    ],
)
def test_gueltige_uebergabedaten_werden_normalisiert(wert, erwartet):
    assert normalisiere_protokoll({"uebergabedatum": wert}) == {"uebergabedatum": erwartet}


@pytest.mark.parametrize(
    "wert",
    [
        "2026-02-30",
        "2023-02-29",
        "2026-13-01",
        "2026-1-1",
        "1.2.26",
        "01/02/2026",
        "morgen",
        "",
        None,
        20260201,
    ],
)
def test_ungueltige_uebergabedaten_nennen_das_feld(wert):
    with pytest.raises(ValueError, match="uebergabedatum"):
        normalisiere_protokoll({"uebergabedatum": wert})


@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [
        ("Einzug", "Einzug"),
        ("einzug", "Einzug"),
        ("EINZUG", "Einzug"),
        ("Auszug", "Auszug"),
        ("auszug", "Auszug"),
        ("AUSZUG", "Auszug"),
    ],
)
def test_art_wird_normalisiert(wert, erwartet):
    assert normalisiere_protokoll({"art": wert}) == {"art": erwartet}


@pytest.mark.parametrize("wert", ["Besichtigung", "Einzug ", "", None, 1, True])
def test_ungueltige_art_nennt_das_feld(wert):
    with pytest.raises(ValueError, match="art"):
        normalisiere_protokoll({"art": wert})


@pytest.mark.parametrize("feld", ["zaehler_strom", "zaehler_wasser"])
@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [
        (0, "0"),
        (7, "7"),
        (12345, "12345"),
        ("0", "0"),
        ("007", "7"),
        ("000", "0"),
        ("1234.50", "1234.5"),
        ("0.250", "0.25"),
        ("0.000", "0"),
        ("1.000", "1"),
        ("00.005", "0.005"),
        ("000.010", "0.01"),
    ],
)
def test_gueltige_zaehlerwerte_werden_normalisiert(feld, wert, erwartet):
    assert normalisiere_protokoll({feld: wert}) == {feld: erwartet}


@pytest.mark.parametrize("feld", ["zaehler_strom", "zaehler_wasser"])
@pytest.mark.parametrize(
    "wert",
    [
        -1,
        -0.01,
        "-1",
        "-0",
        "1,5",
        "1.2345",
        ".5",
        "1.",
        " 1",
        "1 ",
        "1 000",
        "1'000",
        "+1",
        1.5,
        0.0,
        True,
        False,
        None,
        [],
    ],
)
def test_ungueltige_zaehlerwerte_nennen_das_feld(feld, wert):
    with pytest.raises(ValueError, match=feld):
        normalisiere_protokoll({feld: wert})


@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [
        (0, "0"),
        (99, "99"),
        ("0", "0"),
        ("00", "0"),
        ("007", "7"),
        ("099", "99"),
        ("00099", "99"),
    ],
)
def test_gueltige_schluessel_anzahl_wird_normalisiert(wert, erwartet):
    assert normalisiere_protokoll({"schluessel_anzahl": wert}) == {"schluessel_anzahl": erwartet}


@pytest.mark.parametrize(
    "wert",
    [
        -1,
        100,
        "100",
        "-1",
        "1.0",
        " 1",
        "1 ",
        "",
        True,
        False,
        1.0,
        None,
    ],
)
def test_ungueltige_schluessel_anzahl_nennt_das_feld(wert):
    with pytest.raises(ValueError, match="schluessel_anzahl"):
        normalisiere_protokoll({"schluessel_anzahl": wert})


@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [
        ("", ""),
        ("   ", ""),
        ("  Kratzer im Flur  ", "Kratzer im Flur"),
        ("Kratzer\nim Flur", "Kratzer im Flur"),
        ("Kratzer\r\nim Flur", "Kratzer im Flur"),
        ("Kratzer\r im Flur", "Kratzer im Flur"),
        ("Kratzer  \n\t im Flur", "Kratzer im Flur"),
        ("Kratzer\n\nim Flur", "Kratzer im Flur"),
        ("Kratzer im Flur,  Fenster dicht", "Kratzer im Flur,  Fenster dicht"),
        ("x" * 500, "x" * 500),
    ],
)
def test_bemerkungen_werden_normalisiert(wert, erwartet):
    assert normalisiere_protokoll({"bemerkungen": wert}) == {"bemerkungen": erwartet}


@pytest.mark.parametrize(
    "wert",
    [
        "x" * 501,
        "{{kaution}}",
        "Weg }} 1",
        5,
        None,
        True,
    ],
)
def test_ungueltige_bemerkungen_nennen_das_feld(wert):
    with pytest.raises(ValueError, match="bemerkungen"):
        normalisiere_protokoll({"bemerkungen": wert})


def test_laengenpruefung_gilt_nach_der_normalisierung():
    assert normalisiere_protokoll({"bemerkungen": "  " + "x" * 500 + "  "}) == {
        "bemerkungen": "x" * 500
    }
    with pytest.raises(ValueError, match="bemerkungen"):
        normalisiere_protokoll({"bemerkungen": "x" * 400 + "\n" + "x" * 101})


def test_unbekanntes_feld_nennt_den_namen():
    with pytest.raises(ValueError, match="farbe"):
        normalisiere_protokoll({"farbe": "rot"})


def test_nicht_dict_nennt_daten():
    for roh in (None, "art: Einzug", [("art", "Einzug")]):
        with pytest.raises(ValueError, match="daten"):
            normalisiere_protokoll(roh)
