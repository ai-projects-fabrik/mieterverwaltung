"""Akzeptanztest (spec-first) fuer projekt.dokumente (Ziel `mv-dokumente`)."""

import importlib.util
import io
import sys
import textwrap
import xml.etree.ElementTree as ET
import zipfile

import pytest

if importlib.util.find_spec("projekt.dokumente") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.dokumente import FORMATE, erzeuge  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FAKE = textwrap.dedent(
    """
    import pathlib, sys
    outdir, datei = pathlib.Path(sys.argv[5]), pathlib.Path(sys.argv[6])
    (outdir / (datei.stem + ".pdf")).write_bytes(b"%PDF-fake")
    """
)


def docx_bytes(*absaetze):
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>'
    for a in absaetze:
        xml += f'<w:p><w:r><w:t xml:space="preserve">{a}</w:t></w:r></w:p>'
    xml += "</w:body></w:document>"
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return puffer.getvalue()


def absaetze(daten):
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        wurzel = ET.fromstring(z.read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(f"{{{W}}}t")) for p in wurzel.iter(f"{{{W}}}p")]


@pytest.fixture
def konverter(tmp_path):
    skript = tmp_path / "fake_soffice.py"
    skript.write_text(FAKE, encoding="utf-8")
    return [sys.executable, str(skript)]


VORLAGE = docx_bytes("Mieter {{mieter_name}}", "Objekt {{objekt}}")
WERTE = {"mieter_name": "Anna", "objekt": "Haus 1", "kaution": "ungenutzt"}


def test_formate():
    assert FORMATE == ("docx", "pdf", "docx+pdf")


def test_nur_docx_braucht_keinen_konverter():
    ergebnis = erzeuge(VORLAGE, WERTE)
    assert list(ergebnis) == ["docx"]
    assert absaetze(ergebnis["docx"]) == ["Mieter Anna", "Objekt Haus 1"]
    assert list(erzeuge(VORLAGE, WERTE, "docx")) == ["docx"]


def test_pdf_und_beides(konverter):
    nur_pdf = erzeuge(VORLAGE, WERTE, "pdf", konverter=konverter)
    assert nur_pdf == {"pdf": b"%PDF-fake"}
    beides = erzeuge(VORLAGE, WERTE, "docx+pdf", konverter=konverter)
    assert list(beides) == ["docx", "pdf"]
    assert absaetze(beides["docx"])[0] == "Mieter Anna"


def test_fehlende_werte_werden_benannt_und_nichts_wird_umgewandelt(konverter):
    with pytest.raises(ValueError, match="objekt"):
        erzeuge(VORLAGE, {"mieter_name": "Anna"}, "docx+pdf", konverter=konverter)


def test_unbekanntes_format_und_ungueltige_eingaben():
    with pytest.raises(ValueError, match="format"):
        erzeuge(VORLAGE, WERTE, "odt")
    with pytest.raises(ValueError):
        erzeuge(b"kein zip", WERTE)
    with pytest.raises(ValueError):
        erzeuge(VORLAGE, {"mieter_name": 5, "objekt": "x"})


def test_fehlender_konverter_liefert_kein_teilergebnis(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ValueError, match="Konverter"):
        erzeuge(VORLAGE, WERTE, "docx+pdf")
    with pytest.raises(ValueError, match="Konverter"):
        erzeuge(VORLAGE, WERTE, "pdf", konverter=[str(tmp_path / "fehlt")])
    assert list(erzeuge(VORLAGE, WERTE, "docx")) == ["docx"]
