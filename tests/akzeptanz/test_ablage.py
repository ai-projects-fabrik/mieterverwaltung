"""Akzeptanztest (spec-first) fuer projekt.ablage (Ziel `mv-ablage`)."""

import importlib.util

import pytest

if importlib.util.find_spec("projekt.ablage") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.ablage import liste_vorlagen, lese_vorlage, schreibe_ausgabe  # noqa: E402


@pytest.fixture
def ordner(tmp_path):
    for name in ("b.docx", "A.DOCX", "~$b.docx", "notiz.txt"):
        (tmp_path / name).write_bytes(b"inhalt-" + name.encode())
    (tmp_path / "unter.docx").mkdir()
    return tmp_path


def test_liste_vorlagen_nur_docx_sortiert(ordner):
    assert liste_vorlagen(ordner) == ["A.DOCX", "b.docx"]
    assert liste_vorlagen(str(ordner)) == ["A.DOCX", "b.docx"]


def test_liste_vorlagen_ungueltiger_ordner(tmp_path):
    with pytest.raises(ValueError):
        liste_vorlagen(tmp_path / "fehlt")
    datei = tmp_path / "datei.docx"
    datei.write_bytes(b"x")
    with pytest.raises(ValueError):
        liste_vorlagen(datei)


def test_lese_vorlage(ordner):
    assert lese_vorlage(ordner, "b.docx") == b"inhalt-b.docx"
    assert lese_vorlage(ordner, "A.DOCX") == b"inhalt-A.DOCX"


@pytest.mark.parametrize(
    "name",
    [
        "../b.docx",
        "unter/b.docx",
        "a\\b.docx",
        "",
        "fehlt.docx",
        "notiz.txt",
        "~$b.docx",
        "unter.docx",
    ],
)
def test_lese_vorlage_nur_vorhandene_docx_im_ordner(ordner, name):
    with pytest.raises(ValueError, match="vorlage"):
        lese_vorlage(ordner, name)


def test_schreibe_ausgabe_ueberschreibt_nie(tmp_path):
    assert schreibe_ausgabe(tmp_path, "vertrag-anna.docx", b"eins") == "vertrag-anna.docx"
    assert schreibe_ausgabe(tmp_path, "vertrag-anna.docx", b"zwei") == "vertrag-anna-2.docx"
    assert schreibe_ausgabe(tmp_path, "vertrag-anna.docx", b"drei") == "vertrag-anna-3.docx"
    assert (tmp_path / "vertrag-anna.docx").read_bytes() == b"eins"
    assert (tmp_path / "vertrag-anna-2.docx").read_bytes() == b"zwei"
    assert schreibe_ausgabe(tmp_path, "vertrag-anna.pdf", b"%PDF") == "vertrag-anna.pdf"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "vertrag-anna-2.docx",
        "vertrag-anna-3.docx",
        "vertrag-anna.docx",
        "vertrag-anna.pdf",
    ]


@pytest.mark.parametrize(
    "name",
    ["../x.docx", "a/b.docx", "a\\b.docx", "", "x.exe", "x", "x.docx.exe", ".docx"],
)
def test_schreibe_ausgabe_ungueltige_namen(tmp_path, name):
    with pytest.raises(ValueError, match="name"):
        schreibe_ausgabe(tmp_path, name, b"x")
    assert list(tmp_path.iterdir()) == []


def test_schreibe_ausgabe_ordner_und_daten_pruefen(tmp_path):
    fehlt = tmp_path / "fehlt"
    with pytest.raises(ValueError, match="ordner"):
        schreibe_ausgabe(fehlt, "x.docx", b"x")
    assert not fehlt.exists()
    with pytest.raises(ValueError, match="daten"):
        schreibe_ausgabe(tmp_path, "x.docx", "text")
    assert list(tmp_path.iterdir()) == []
