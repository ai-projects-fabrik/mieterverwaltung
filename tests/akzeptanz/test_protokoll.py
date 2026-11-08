"""Akzeptanztest (spec-first) fuer projekt.protokoll (Ziel `mv-protokoll`)."""

import importlib.util

import pytest

if importlib.util.find_spec("projekt.protokoll") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.protokoll import PROTOKOLL_FELDER, normalisiere_protokoll  # noqa: E402

VOLL = {
    "mieter_name": "  Anna Muster ",
    "objekt": "Musterweg 1, 8000 Zürich",
    "uebergabedatum": "2026-02-01",
    "art": "einzug",
    "zaehler_strom": "1234.50",
    "zaehler_wasser": 56,
    "schluessel_anzahl": "3",
    "bemerkungen": "Kratzer\nim Flur,  Fenster dicht",
}


def test_felder_und_vollstaendiger_datensatz():
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
    assert normalisiere_protokoll(VOLL) == {
        "mieter_name": "Anna Muster",
        "objekt": "Musterweg 1, 8000 Zürich",
        "uebergabedatum": "01.02.2026",
        "art": "Einzug",
        "zaehler_strom": "1234.5",
        "zaehler_wasser": "56",
        "schluessel_anzahl": "3",
        "bemerkungen": "Kratzer im Flur,  Fenster dicht",
    }
    assert normalisiere_protokoll({}) == {}
    assert VOLL["zaehler_wasser"] == 56


@pytest.mark.parametrize(
    ("feld", "wert", "erwartet"),
    [
        ("uebergabedatum", "1.2.2026", "01.02.2026"),
        ("art", "AUSZUG", "Auszug"),
        ("zaehler_strom", 12345, "12345"),
        ("zaehler_strom", "007", "7"),
        ("zaehler_wasser", "0.250", "0.25"),
        ("schluessel_anzahl", 0, "0"),
        ("schluessel_anzahl", "99", "99"),
        ("bemerkungen", "   ", ""),
    ],
)
def test_gueltige_einzelwerte(feld, wert, erwartet):
    assert normalisiere_protokoll({feld: wert}) == {feld: erwartet}


@pytest.mark.parametrize(
    ("feld", "wert"),
    [
        ("mieter_name", ""),
        ("mieter_name", "{{x}}"),
        ("objekt", "x" * 121),
        ("uebergabedatum", "2026-02-30"),
        ("uebergabedatum", "morgen"),
        ("art", "Besichtigung"),
        ("zaehler_strom", "-1"),
        ("zaehler_strom", "1,5"),
        ("zaehler_strom", "1.2345"),
        ("zaehler_wasser", True),
        ("zaehler_wasser", 1.5),
        ("zaehler_wasser", None),
        ("schluessel_anzahl", 100),
        ("schluessel_anzahl", "-1"),
        ("schluessel_anzahl", True),
        ("bemerkungen", "x" * 501),
        ("bemerkungen", "{{kaution}}"),
        ("bemerkungen", 5),
    ],
)
def test_ungueltige_einzelwerte_sind_value_error_mit_feldname(feld, wert):
    with pytest.raises(ValueError, match=feld):
        normalisiere_protokoll({feld: wert})


def test_unbekannte_felder_und_falsche_typen():
    with pytest.raises(ValueError, match="farbe"):
        normalisiere_protokoll({"farbe": "rot"})
    with pytest.raises(ValueError):
        normalisiere_protokoll("art: Einzug")
