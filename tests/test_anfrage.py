"""Tests fuer projekt.anfrage mit synthetischen Anfragen."""

import pytest

from projekt.anfrage import aenderungen_aus_text


def test_leerer_text_und_prosa_ergeben_keine_aenderungen():
    assert aenderungen_aus_text("") == {}
    assert aenderungen_aus_text("Bitte um Rueckmeldung.\nOhne Feldangabe") == {}


def test_feldnamen_werden_getrimmt_kleingeschrieben_und_mit_unterstrich_verbunden():
    assert aenderungen_aus_text(" MIETER NAME : Anna Muster ") == {"mieter_name": "Anna Muster"}


def test_alle_bekannten_felder_werden_gelesen():
    text = (
        "Mieter name: Anna Muster\n"
        "Objekt: Musterweg 1, 8000 Zuerich\n"
        "Mietbeginn: 1.12.2026\n"
        "Miete netto: CHF 1'250.50\n"
        "Nebenkosten: 200\n"
        "Kaution: 3000.00\n"
    )
    assert aenderungen_aus_text(text) == {
        "mieter_name": "Anna Muster",
        "objekt": "Musterweg 1, 8000 Zuerich",
        "mietbeginn": "01.12.2026",
        "miete_netto": "1'250.50",
        "nebenkosten": "200.00",
        "kaution": "3'000.00",
    }


def test_nur_der_erste_doppelpunkt_trennt():
    assert aenderungen_aus_text("Objekt: Weg 1, 8000 Zuerich: 2. OG") == {
        "objekt": "Weg 1, 8000 Zuerich: 2. OG"
    }


def test_unbekannte_felder_und_zeilen_ohne_doppelpunkt_werden_ignoriert():
    assert aenderungen_aus_text(
        "Hinweis: keine Vertragsaenderung\nnur Prosa\nMiete netto: 1000\nWeitere Info: 2026-12-01"
    ) == {"miete_netto": "1'000.00"}


def test_zitierte_zeilen_werden_ignoriert_auch_mit_leading_whitespace():
    assert aenderungen_aus_text(
        "  > Kaution: 99\n\t> Miete netto: 500\nMieter name: Anna Muster"
    ) == {"mieter_name": "Anna Muster"}


def test_crlf_und_lf_sind_gleichwertig():
    lf = "Miete netto: 1000\nmietbeginn: 2026-12-01"
    crlf = "Miete netto: 1000\r\nmietbeginn: 2026-12-01"
    assert aenderungen_aus_text(lf) == aenderungen_aus_text(crlf)


def test_gleiches_feld_mit_gleichem_normalisierten_wert_kommt_einmal_vor():
    assert aenderungen_aus_text("Kaution: 3000\nKaution: CHF 3'000.00") == {"kaution": "3'000.00"}


def test_mehrere_felder_bleiben_vollstaendig():
    assert aenderungen_aus_text("Kaution: 3000\nMiete netto: 1000") == {
        "kaution": "3'000.00",
        "miete_netto": "1'000.00",
    }


@pytest.mark.parametrize(
    ("text", "feld"),
    [
        ("Miete netto: viel", "miete_netto"),
        ("Mietbeginn: 2026-02-30", "mietbeginn"),
        ("Mieter name:", "mieter_name"),
        ("Kaution: -1", "kaution"),
    ],
)
def test_ungueltiger_wert_nennt_das_feld(text, feld):
    with pytest.raises(ValueError, match=feld):
        aenderungen_aus_text(text)


def test_widerspruechliche_doppelung_nennt_das_feld():
    with pytest.raises(ValueError, match="kaution"):
        aenderungen_aus_text("Kaution: 100\nKaution: 200")


@pytest.mark.parametrize("roh", [None, 5, b"Kaution: 1", ["Kaution: 1"]])
def test_kein_text_ist_value_error(roh):
    with pytest.raises(ValueError, match="Text"):
        aenderungen_aus_text(roh)
