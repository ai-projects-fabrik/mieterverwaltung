"""Akzeptanztest (spec-first) fuer projekt.docx_fuellen (Ziel `mv-docx-fuellen`)."""

import importlib.util
import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

if importlib.util.find_spec("projekt.docx_fuellen") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.docx_fuellen import fuelle, platzhalter  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
STYLES = b"<styles>unveraendert</styles>"


def docx(*absaetze):
    """Jeder Absatz ist eine Liste von Run-Texten."""
    xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}"><w:body>'
    )
    for runs in absaetze:
        xml += "<w:p>"
        for t in runs:
            t = t.replace("&", "&amp;").replace("<", "&lt;")
            xml += f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r>'
        xml += "</w:p>"
    xml += "</w:body></w:document>"
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
        z.writestr("word/styles.xml", STYLES)
    return puffer.getvalue()


def absaetze(daten):
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        wurzel = ET.fromstring(z.read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(f"{{{W}}}t")) for p in wurzel.iter(f"{{{W}}}p")]


def test_platzhalter_einfach_und_ueber_mehrere_runs():
    d = docx(["Mieter: {{mieter_name}}, Miete {{miete_netto}}"], ["Kaut", "ion {{kau", "tion}}"])
    assert platzhalter(d) == ["kaution", "miete_netto", "mieter_name"]


def test_fuellen_ersetzt_auch_ueber_run_grenzen():
    d = docx(["Mieter: {{mieter", "_name}} wohnt"], ["Miete {{miete_netto}} CHF"])
    ergebnis = fuelle(d, {"mieter_name": "Anna Muster", "miete_netto": "1'250.50"})
    assert absaetze(ergebnis) == ["Mieter: Anna Muster wohnt", "Miete 1'250.50 CHF"]


def test_wert_mit_sonderzeichen_bleibt_gueltiges_xml():
    ergebnis = fuelle(docx(["{{objekt}}"]), {"objekt": "Muster & Sohn <AG>"})
    assert absaetze(ergebnis) == ["Muster & Sohn <AG>"]


def test_fehlende_werte_bleiben_als_platzhalter_stehen():
    ergebnis = fuelle(docx(["{{mieter_name}} / {{kaution}}"]), {"mieter_name": "Anna"})
    assert absaetze(ergebnis) == ["Anna / {{kaution}}"]
    assert platzhalter(ergebnis) == ["kaution"]


def test_mehrfach_vorkommen_werden_alle_ersetzt():
    ergebnis = fuelle(
        docx(["{{mieter_name}}"], ["Unterschrift {{mieter_name}}"]), {"mieter_name": "Anna"}
    )
    assert absaetze(ergebnis) == ["Anna", "Unterschrift Anna"]


def test_andere_dateien_im_paket_bleiben_unveraendert():
    ergebnis = fuelle(docx(["{{objekt}}"]), {"objekt": "x"})
    with zipfile.ZipFile(io.BytesIO(ergebnis)) as z:
        assert z.read("word/styles.xml") == STYLES
        assert z.testzip() is None
        assert set(z.namelist()) == {"[Content_Types].xml", "word/document.xml", "word/styles.xml"}


def test_ohne_platzhalter_und_ohne_werte():
    d = docx(["Nur Text"])
    assert platzhalter(d) == []
    assert absaetze(fuelle(d, {})) == ["Nur Text"]


def test_ungueltige_eingaben_sind_value_error():
    ohne_dokument = io.BytesIO()
    with zipfile.ZipFile(ohne_dokument, "w") as z:
        z.writestr("x.txt", "x")
    for kaputt in (b"kein zip", b"", ohne_dokument.getvalue()):
        with pytest.raises(ValueError):
            platzhalter(kaputt)
        with pytest.raises(ValueError):
            fuelle(kaputt, {})
    for werte in ({"objekt": 5}, {"objekt": None}):
        with pytest.raises(ValueError):
            fuelle(docx(["{{objekt}}"]), werte)
