"""Tests fuer projekt.ablage mit synthetischen Dateien und Ordnern."""

from pathlib import Path

import pytest

import projekt.ablage as ablage_modul
from projekt.ablage import lese_vorlage, liste_vorlagen, schreibe_ausgabe


def test_liste_vorlagen_filtert_und_sortiert_casefold(tmp_path):
    for name in ("z.docx", "B.DOCX", "a.docx", "~$z.docx", "~$B.DOCX", "notiz.txt"):
        (tmp_path / name).write_bytes(name.encode())
    (tmp_path / "unter.docx").mkdir()

    assert liste_vorlagen(tmp_path) == ["a.docx", "B.DOCX", "z.docx"]
    assert liste_vorlagen(str(tmp_path)) == ["a.docx", "B.DOCX", "z.docx"]


@pytest.mark.parametrize("art", ["fehlt", "datei"])
def test_liste_vorlagen_braucht_einen_ordner(tmp_path, art):
    ordner = tmp_path / "fehlt"
    if art == "datei":
        ordner.write_bytes(b"x")
    with pytest.raises(ValueError, match="ordner"):
        liste_vorlagen(ordner)


def test_liste_vorlagen_meldet_nicht_lesbaren_ordner(tmp_path, monkeypatch):
    def fehler(_pfad):
        raise OSError("Testfehler")

    monkeypatch.setattr(ablage_modul.Path, "iterdir", fehler)
    with pytest.raises(ValueError, match="ordner"):
        liste_vorlagen(tmp_path)


def test_lese_vorlage_liefert_bytes(tmp_path):
    (tmp_path / "Vorlage.DOCX").write_bytes(b"docx-inhalt")
    assert lese_vorlage(tmp_path, "Vorlage.DOCX") == b"docx-inhalt"


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "../x.docx", "unter/x.docx", "x\\y.docx", "nicht.docx", "x.pdf", None, 1],
)
def test_lese_vorlage_lehnt_ungueltige_namen_ab(tmp_path, name):
    (tmp_path / "x.docx").write_bytes(b"x")
    with pytest.raises(ValueError, match="vorlage"):
        lese_vorlage(tmp_path, name)


def test_lese_vorlage_meldet_lesefehler(tmp_path, monkeypatch):
    (tmp_path / "x.docx").write_bytes(b"x")

    def fehler(_pfad):
        raise OSError("Testfehler")

    monkeypatch.setattr(ablage_modul.Path, "read_bytes", fehler)
    with pytest.raises(ValueError, match="vorlage"):
        lese_vorlage(tmp_path, "x.docx")


def test_schreibe_ausgabe_nummeriert_bei_mehreren_kollisionen(tmp_path):
    for name in ("vertrag.docx", "vertrag-2.docx", "vertrag-3.docx"):
        (tmp_path / name).write_bytes(b"alt")

    assert schreibe_ausgabe(tmp_path, "vertrag.docx", b"neu") == "vertrag-4.docx"
    assert (tmp_path / "vertrag.docx").read_bytes() == b"alt"
    assert (tmp_path / "vertrag-4.docx").read_bytes() == b"neu"


def test_schreibe_ausgabe_akzeptiert_pdf_und_mehrteiligen_stamm(tmp_path):
    assert schreibe_ausgabe(tmp_path, "vertrag.anna.pdf", b"%PDF-1") == "vertrag.anna.pdf"
    assert schreibe_ausgabe(tmp_path, "vertrag.anna.pdf", b"%PDF-2") == "vertrag.anna-2.pdf"


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "/x.docx", "a/b.docx", "a\\b.docx", "x", "x.DOCX", "x.PDF", ".docx", ".pdf"],
)
def test_schreibe_ausgabe_lehnt_ungueltige_namen_ab(tmp_path, name):
    with pytest.raises(ValueError, match="name"):
        schreibe_ausgabe(tmp_path, name, b"x")
    assert list(tmp_path.iterdir()) == []


def test_schreibe_ausgabe_prueft_ordner_und_daten_vor_dem_schreiben(tmp_path):
    fehlt = tmp_path / "fehlt"
    with pytest.raises(ValueError, match="ordner"):
        schreibe_ausgabe(fehlt, "x.docx", b"x")
    assert not fehlt.exists()

    with pytest.raises(ValueError, match="daten"):
        schreibe_ausgabe(tmp_path, "x.docx", bytearray(b"x"))
    assert list(tmp_path.iterdir()) == []


def test_schreibe_ausgabe_entfernt_teil_datei_bei_schreibfehler(tmp_path, monkeypatch):
    original_open = Path.open

    class Fehlerdatei:
        def __init__(self, datei):
            self._datei = datei

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self._datei.close()

        def write(self, _daten):
            raise OSError("Testschreibfehler")

    def oeffnen(pfad, *args, **kwargs):
        return Fehlerdatei(original_open(pfad, *args, **kwargs))

    monkeypatch.setattr(Path, "open", oeffnen)
    with pytest.raises(ValueError, match="name"):
        schreibe_ausgabe(tmp_path, "x.docx", b"x")
    assert list(tmp_path.iterdir()) == []
