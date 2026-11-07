"""Akzeptanztest (spec-first) fuer projekt.anfrage: Beispiele aus dem Ziel `mv-anfrage`."""

import importlib.util

import pytest

if importlib.util.find_spec("projekt.anfrage") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.anfrage import aenderungen_aus_text  # noqa: E402

MAIL = (
    "Hallo,\n"
    "\n"
    "bitte aendern:\n"
    "Mieter name: Anna Muster\n"
    "Miete netto: CHF 1'250.50\n"
    "> Kaution: 99\n"
    "Hinweis: bitte bis Freitag\n"
    "Viele Gruesse\n"
)

GUELTIG = [
    ("", {}),
    ("Nur Prosa ohne Felder.\nZweite Zeile.", {}),
    (MAIL, {"mieter_name": "Anna Muster", "miete_netto": "1'250.50"}),
    (
        "MIETE_NETTO: 1000\r\nmietbeginn: 2026-12-01",
        {"miete_netto": "1'000.00", "mietbeginn": "01.12.2026"},
    ),
    ("Kaution: 3000\nKaution: 3000.00", {"kaution": "3'000.00"}),
    ("Objekt: Weg 1, 8000 Zuerich: 2. OG", {"objekt": "Weg 1, 8000 Zuerich: 2. OG"}),
]

UNGUELTIG = [
    ("Miete netto: viel", "miete_netto"),
    ("Mietbeginn: 2026-02-30", "mietbeginn"),
    ("Kaution: 100\nKaution: 200", "kaution"),
    ("Mieter name:", "mieter_name"),
]


@pytest.mark.parametrize(("text", "erwartet"), GUELTIG)
def test_gueltige_mails(text, erwartet):
    assert aenderungen_aus_text(text) == erwartet


@pytest.mark.parametrize(("text", "feld"), UNGUELTIG)
def test_ungueltige_werte_sind_value_error_mit_feldname(text, feld):
    with pytest.raises(ValueError, match=feld):
        aenderungen_aus_text(text)


def test_kein_text_ist_value_error():
    for roh in (None, 5, b"Kaution: 1"):
        with pytest.raises(ValueError):
            aenderungen_aus_text(roh)
