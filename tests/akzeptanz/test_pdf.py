"""Akzeptanztest (spec-first) fuer projekt.pdf (Ziel `mv-pdf`)."""

import importlib.util
import sys
import textwrap

import pytest

if importlib.util.find_spec("projekt.pdf") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.pdf import KonverterFehlt, PdfFehler, docx_zu_pdf, konverter_finden  # noqa: E402

DOCX = b"PK-fake-docx"

# Ersatz fuer LibreOffice: gleiche Aufrufform `... --headless --convert-to pdf --outdir DIR DATEI`.
FAKE = textwrap.dedent(
    """
    import pathlib, sys, time
    args = sys.argv[1:]
    modus = pathlib.Path(__file__).with_name("modus.txt").read_text()
    assert args[:3] == ["--headless", "--convert-to", "pdf"], args
    assert args[3] == "--outdir", args
    outdir, datei = pathlib.Path(args[4]), pathlib.Path(args[5])
    if modus == "fehler":
        sys.stderr.write("kaputt")
        sys.exit(3)
    if modus == "langsam":
        time.sleep(30)
    if modus == "ohne_datei":
        sys.exit(0)
    inhalt = datei.read_bytes()
    (outdir / (datei.stem + ".pdf")).write_bytes(b"%PDF-fake:" + inhalt)
    """
)


@pytest.fixture
def fake(tmp_path):
    skript = tmp_path / "fake_soffice.py"
    skript.write_text(FAKE, encoding="utf-8")
    modus = tmp_path / "modus.txt"
    modus.write_text("ok", encoding="utf-8")

    def setze(wert):
        modus.write_text(wert, encoding="utf-8")
        return [sys.executable, str(skript)]

    return setze


def test_umwandlung_liefert_pdf_bytes(fake):
    assert docx_zu_pdf(DOCX, konverter=fake("ok")) == b"%PDF-fake:" + DOCX


def test_klassen_sind_value_error():
    assert issubclass(PdfFehler, ValueError)
    assert issubclass(KonverterFehlt, PdfFehler)


@pytest.mark.parametrize("modus", ["fehler", "ohne_datei"])
def test_konverterfehler_sind_pdf_fehler(fake, modus):
    with pytest.raises(PdfFehler) as fehler:
        docx_zu_pdf(DOCX, konverter=fake(modus))
    assert not isinstance(fehler.value, KonverterFehlt)


def test_zeitueberschreitung_ist_pdf_fehler(fake):
    with pytest.raises(PdfFehler, match="Zeit"):
        docx_zu_pdf(DOCX, konverter=fake("langsam"), timeout=1)


def test_fehlender_konverter_ist_klare_meldung(tmp_path, monkeypatch):
    with pytest.raises(KonverterFehlt, match="Konverter"):
        docx_zu_pdf(DOCX, konverter=[str(tmp_path / "gibt-es-nicht")])
    monkeypatch.setenv("PATH", str(tmp_path))
    assert konverter_finden() is None
    with pytest.raises(KonverterFehlt, match="soffice"):
        docx_zu_pdf(DOCX)


def test_konverter_finden_sucht_soffice_im_pfad(tmp_path):
    assert konverter_finden(suchpfad=str(tmp_path)) is None
    name = "soffice.exe" if sys.platform == "win32" else "soffice"
    programm = tmp_path / name
    programm.write_bytes(b"")
    programm.chmod(0o755)
    gefunden = konverter_finden(suchpfad=str(tmp_path))
    assert gefunden is not None
    assert len(gefunden) == 1
    assert gefunden[0].lower().endswith(name)


@pytest.mark.parametrize("docx", ["text", b"", None, 5])
def test_ungueltige_eingabe_ist_value_error(fake, docx):
    with pytest.raises(ValueError, match="docx"):
        docx_zu_pdf(docx, konverter=fake("ok"))
