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


def dokument_mit_runs(*absaetze: list[str]) -> bytes:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>'
    for runs in absaetze:
        xml += "<w:p>" + "".join(f"<w:r><w:t>{text}</w:t></w:r>" for text in runs) + "</w:p>"
    xml += "</w:body></w:document>"
    return xml.encode()


def texte(daten: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(daten)) as paket:
        wurzel = ET.fromstring(paket.read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(f"{{{W}}}t")) for p in wurzel.iter(f"{{{W}}}p")]


def docx_mit_teilen(haupt: str, **teile: str) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as paket:
        paket.writestr("[Content_Types].xml", "<Types/>")
        paket.writestr("word/document.xml", dokument(haupt))
        paket.writestr("word/styles.xml", b"<styles/>")
        for name, text in teile.items():
            wurzel = "hdr" if name.startswith(("header", "footer")) else "footnotes"
            paket.writestr(
                f"word/{name}.xml",
                f'<w:{wurzel} xmlns:w="{W}"><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:{wurzel}>',
            )
    return puffer.getvalue()


def teiltext(daten: bytes, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(daten)) as paket:
        wurzel = ET.fromstring(paket.read(f"word/{name}.xml"))
    return "".join(t.text or "" for t in wurzel.iter(f"{{{W}}}t"))


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


def test_platzhalter_und_fuelle_in_kopf_fuss_und_noten():
    d = docx_mit_teilen(
        "Mieter {{mieter_name}}",
        header1="Kopf {{mieter_name}}",
        footer2="Fuss {{objekt}}",
        footnotes="Note {{kaution}}",
        endnotes="Ende {{mietbeginn}}",
    )
    assert platzhalter(d) == ["kaution", "mietbeginn", "mieter_name", "objekt"]

    ergebnis = fuelle(
        d,
        {
            "mieter_name": "Anna",
            "objekt": "Weg 1",
            "kaution": "3'000.00",
            "mietbeginn": "01.01.2026",
        },
    )
    assert texte(ergebnis) == ["Mieter Anna"]
    assert teiltext(ergebnis, "header1") == "Kopf Anna"
    assert teiltext(ergebnis, "footer2") == "Fuss Weg 1"
    assert teiltext(ergebnis, "footnotes") == "Note 3'000.00"
    assert teiltext(ergebnis, "endnotes") == "Ende 01.01.2026"
    with zipfile.ZipFile(io.BytesIO(ergebnis)) as paket:
        assert paket.read("word/styles.xml") == b"<styles/>"


def test_fehlende_werte_in_teilen_bleiben_stehen():
    d = docx_mit_teilen("", header1="{{mieter_name}} / {{objekt}}")
    ergebnis = fuelle(d, {"mieter_name": "Anna"})
    assert teiltext(ergebnis, "header1") == "Anna / {{objekt}}"
    assert unersetzt(ergebnis) == ["Kopfzeile: {{objekt}}"]


def test_unersetzt_nennt_stelle_und_text_in_fester_reihenfolge():
    d = docx_mit_teilen(
        "Mieter {{Mieter_Name}} und {{mieter_name}}",
        header2="{{h2}}",
        header1="Kopf {{Name des Mieters}}",
        footer1="Fuss {{ objekt }}",
        footnotes="Note {{kaution}}",
        endnotes="Ende {{mietbeginn}}",
    )
    assert unersetzt(d) == [
        "Text: {{Mieter_Name}}",
        "Text: {{mieter_name}}",
        "Kopfzeile: {{Name des Mieters}}",
        "Kopfzeile: {{h2}}",
        "Fusszeile: {{ objekt }}",
        "Fussnoten: {{kaution}}",
        "Endnoten: {{mietbeginn}}",
    ]


def test_unersetzt_findet_ueber_run_grenzen_und_alle_formen():
    d = docx(dokument_mit_runs(["{{Mieter", "_Name}} und {{ objekt }} und {{}} und {einfach}"]))
    assert unersetzt(d) == ["Text: {{Mieter_Name}}", "Text: {{ objekt }}", "Text: {{}}"]


def test_unersetzt_ohne_reste_ist_leer():
    d = fuelle(docx_mit_teilen("{{objekt}}", header1="{{mieter_name}}"), {"objekt": "Weg 1"})
    assert unersetzt(d) == ["Kopfzeile: {{mieter_name}}"]
    assert unersetzt(fuelle(d, {"mieter_name": "Anna"})) == []


def test_unersetzt_ungueltiges_paket_und_xml_sind_value_error():
    for roh in (b"kein zip", b"", None, "text", bytearray(b"zip")):
        with pytest.raises(ValueError):
            unersetzt(roh)

    ohne_dokument = io.BytesIO()
    with zipfile.ZipFile(ohne_dokument, "w") as paket:
        paket.writestr("word/header1.xml", f'<w:hdr xmlns:w="{W}"/>')
    with pytest.raises(ValueError):
        unersetzt(ohne_dokument.getvalue())

    kaputter_kopf = io.BytesIO()
    with zipfile.ZipFile(kaputter_kopf, "w") as paket:
        paket.writestr("word/document.xml", dokument("ok"))
        paket.writestr("word/header1.xml", b"<w:hdr>")
    with pytest.raises(ValueError, match="header1"):
        unersetzt(kaputter_kopf.getvalue())
    with pytest.raises(ValueError, match="header1"):
        platzhalter(kaputter_kopf.getvalue())
    with pytest.raises(ValueError, match="header1"):
        fuelle(kaputter_kopf.getvalue(), {})


def test_fuelle_legt_fehlende_teile_nicht_an():
    d = docx(dokument("{{objekt}}"))
    with zipfile.ZipFile(io.BytesIO(d)) as paket:
        vorher = set(paket.namelist())
    with zipfile.ZipFile(io.BytesIO(fuelle(d, {"objekt": "Weg 1"}))) as paket:
        assert set(paket.namelist()) == vorher
