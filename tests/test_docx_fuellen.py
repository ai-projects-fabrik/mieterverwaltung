"""Tests fuer projekt.docx_fuellen mit synthetischen DOCX-Paketen."""

import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

from projekt.docx_fuellen import fuelle, platzhalter

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx(rohes_dokument: bytes, *, style: bytes = b"<styles/>") -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as paket:
        paket.writestr("[Content_Types].xml", "<Types/>")
        paket.writestr("word/document.xml", rohes_dokument)
        paket.writestr("word/styles.xml", style)
    return puffer.getvalue()


def dokument(*absaetze: str) -> bytes:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>'
    for text in absaetze:
        xml += f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    xml += "</w:body></w:document>"
    return xml.encode()


def texte(daten: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(daten)) as paket:
        wurzel = ET.fromstring(paket.read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(f"{{{W}}}t")) for p in wurzel.iter(f"{{{W}}}p")]


def test_platzhalter_sind_sortiert_und_eindeutig():
    d = docx(dokument("{{kaution}} {{mieter_name}}", "{{kaution}}"))
    assert platzhalter(d) == ["kaution", "mieter_name"]


def test_nur_kleinbuchstaben_und_unterstrich_sind_platzhalter():
    d = docx(dokument("{{Miete}} {{miete-extra}} {{miete_netto}}"))
    assert platzhalter(d) == ["miete_netto"]


def test_leere_werte_entfernen_platzhalter():
    assert texte(fuelle(docx(dokument("{{objekt}}")), {"objekt": ""})) == [""]


def test_unbekannte_platzhalter_bleiben_stehen():
    ergebnis = fuelle(docx(dokument("{{objekt}} {{unbekannt}}")), {"objekt": "Weg 1"})
    assert texte(ergebnis) == ["Weg 1 {{unbekannt}}"]
    assert platzhalter(ergebnis) == ["unbekannt"]


def test_werte_muessen_ein_dict_mit_textwerten_sein():
    d = docx(dokument("{{objekt}}"))
    for werte in (None, [], {"objekt": 1}, {"objekt": None}, {5: "x"}):
        with pytest.raises(ValueError):
            fuelle(d, werte)


def test_feldname_steht_in_fehlertext():
    with pytest.raises(ValueError, match="objekt"):
        fuelle(docx(dokument("{{objekt}}")), {"objekt": 5})


def test_kaputtes_dokument_xml_ist_value_error():
    d = docx(b"<w:document>", style=b"unveraendert")
    with pytest.raises(ValueError):
        platzhalter(d)
    with pytest.raises(ValueError):
        fuelle(d, {})


def test_falsches_wurzelelement_ist_value_error():
    d = docx(f'<w:body xmlns:w="{W}"/>'.encode())
    with pytest.raises(ValueError):
        platzhalter(d)
    with pytest.raises(ValueError):
        fuelle(d, {})


def test_nicht_bytes_ist_value_error():
    for roh in (None, "text", bytearray(b"zip")):
        with pytest.raises(ValueError):
            platzhalter(roh)
        with pytest.raises(ValueError):
            fuelle(roh, {})


def test_leerzeichen_an_den_raendern_bleiben_erhalten():
    ergebnis = fuelle(docx(dokument("{{objekt}}")), {"objekt": " Weg 1 "})
    with zipfile.ZipFile(io.BytesIO(ergebnis)) as paket:
        wurzel = ET.fromstring(paket.read("word/document.xml"))
    text_knoten = next(wurzel.iter(f"{{{W}}}t"))
    assert text_knoten.text == " Weg 1 "
    assert text_knoten.attrib == {"{http://www.w3.org/XML/1998/namespace}space": "preserve"}


def test_unbenutzte_namensraeume_bleiben_deklariert():
    roh = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'mc:Ignorable="w14"><w:body><w:p><w:r><w:t>{{objekt}}</w:t></w:r></w:p>'
        "</w:body></w:document>"
    )
    ergebnis = fuelle(docx(roh.encode()), {"objekt": "Weg 1"})
    with zipfile.ZipFile(io.BytesIO(ergebnis)) as paket:
        neu = paket.read("word/document.xml")
    assert b'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"' in neu
    assert texte(ergebnis) == ["Weg 1"]
