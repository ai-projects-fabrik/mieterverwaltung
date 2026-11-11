"""Tests fuer projekt.docx_fuellen mit synthetischen DOCX-Paketen."""

import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

from projekt.docx_fuellen import fuelle, platzhalter, unersetzt

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


def _teil_xml(wurzel: str, absaetze: list[list[str]]) -> bytes:
    text = f'<w:{wurzel} xmlns:w="{W}">'
    for runs in absaetze:
        text += "<w:p>"
        for run in runs:
            text += f'<w:r><w:t xml:space="preserve">{run}</w:t></w:r>'
        text += "</w:p>"
    return (text + f"</w:{wurzel}>").encode()


def docx_mit_teilen(haupt: list[list[str]], teile: dict[str, list[list[str]]]) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as paket:
        paket.writestr("[Content_Types].xml", "<Types/>")
        paket.writestr("word/document.xml", _teil_xml("document", haupt))
        paket.writestr("word/styles.xml", b"<styles>unveraendert</styles>")
        for name, absaetze in teile.items():
            if name.startswith(("header", "footer")):
                wurzel = "hdr"
            elif name == "footnotes":
                wurzel = "footnotes"
            else:
                wurzel = "endnotes"
            paket.writestr(f"word/{name}.xml", _teil_xml(wurzel, absaetze))
    return puffer.getvalue()


def teil_texte(daten: bytes, name: str) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(daten)) as paket:
        wurzel = ET.fromstring(paket.read(f"word/{name}.xml"))
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


def test_platzhalter_und_fuelle_verarbeiten_alle_textteile():
    daten = docx_mit_teilen(
        [["Mieter {{mieter_name}}"]],
        {
            "header10": [["Kopf {{kaution}}"]],
            "header2": [["Kopf zwei {{objekt}}"]],
            "footer1": [["Fuss {{mietbeginn}}"]],
            "footnotes": [["Note {{objekt}}"]],
            "endnotes": [["Ende {{kaution}}"]],
        },
    )
    assert platzhalter(daten) == ["kaution", "mietbeginn", "mieter_name", "objekt"]
    assert unersetzt(daten) == [
        "Text: {{mieter_name}}",
        "Kopfzeile: {{kaution}}",
        "Kopfzeile: {{objekt}}",
        "Fusszeile: {{mietbeginn}}",
        "Fussnoten: {{objekt}}",
        "Endnoten: {{kaution}}",
    ]

    ergebnis = fuelle(
        daten,
        {
            "mieter_name": "Anna",
            "kaution": "3'000.00",
            "objekt": "Weg 1",
            "mietbeginn": "01.01.2026",
        },
    )
    assert texte(ergebnis) == ["Mieter Anna"]
    assert teil_texte(ergebnis, "header10") == ["Kopf 3'000.00"]
    assert teil_texte(ergebnis, "header2") == ["Kopf zwei Weg 1"]
    assert teil_texte(ergebnis, "footer1") == ["Fuss 01.01.2026"]
    assert teil_texte(ergebnis, "footnotes") == ["Note Weg 1"]
    assert teil_texte(ergebnis, "endnotes") == ["Ende 3'000.00"]
    with zipfile.ZipFile(io.BytesIO(ergebnis)) as paket:
        assert paket.read("word/styles.xml") == b"<styles>unveraendert</styles>"


def test_unersetzt_findet_rest_ueber_run_grenzen_und_nach_fuellen():
    daten = docx_mit_teilen(
        [
            [
                "Mieter {{Mieter",
                "_Name}} und {{mieter_name}}",
            ]
        ],
        {"header1": [["Kopf {{Name des ", "Mieters}}"]]},
    )
    assert unersetzt(daten) == [
        "Text: {{Mieter_Name}}",
        "Text: {{mieter_name}}",
        "Kopfzeile: {{Name des Mieters}}",
    ]
    assert unersetzt(fuelle(daten, {"mieter_name": "Anna"})) == [
        "Text: {{Mieter_Name}}",
        "Kopfzeile: {{Name des Mieters}}",
    ]
    assert unersetzt(fuelle(daten, {"mieter_name": "Anna", "Mieter_Name": "x"})) == [
        "Text: {{Mieter_Name}}",
        "Kopfzeile: {{Name des Mieters}}",
    ]


def test_unersetzt_prueft_das_paket_und_meldet_keine_leeren_reste():
    assert unersetzt(docx(dokument("Alles Anna"))) == []
    for kaputt in (b"kein zip", b"", None, bytearray(b"zip")):
        with pytest.raises(ValueError):
            unersetzt(kaputt)
