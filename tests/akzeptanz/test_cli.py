"""Akzeptanztest (spec-first) fuer projekt.cli: Beispiele aus dem Ziel `mv-cli`."""

import importlib.util
import io
import json
import xml.etree.ElementTree as ET
import zipfile

import pytest

if importlib.util.find_spec("projekt.cli") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.cli import main  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DATEN = {
    "mieter_name": "Bert Beispiel",
    "objekt": "Musterweg 1, 8000 Zuerich",
    "mietbeginn": "2026-01-01",
    "miete_netto": 1200,
    "nebenkosten": 200,
    "kaution": 3600,
}
VORLAGE_TEXT = [
    "Mietvertrag fuer {{objekt}}",
    "Mieter: {{mieter_name}}, Beginn {{mietbeginn}}",
    "Netto {{miete_netto}} plus NK {{nebenkosten}}, Kaution {{kaution}}",
]


def docx_bytes(absaetze):
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>'
    for a in absaetze:
        xml += f'<w:p><w:r><w:t xml:space="preserve">{a}</w:t></w:r></w:p>'
    xml += "</w:body></w:document>"
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return puffer.getvalue()


def absaetze(pfad):
    with zipfile.ZipFile(pfad) as z:
        wurzel = ET.fromstring(z.read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(f"{{{W}}}t")) for p in wurzel.iter(f"{{{W}}}p")]


@pytest.fixture
def arbeit(tmp_path):
    (tmp_path / "vorlage.docx").write_bytes(docx_bytes(VORLAGE_TEXT))
    (tmp_path / "daten.json").write_text(json.dumps(DATEN), encoding="utf-8")
    return tmp_path


def lauf(arbeit, *extra):
    return main(
        [
            "--vorlage", str(arbeit / "vorlage.docx"),
            "--daten", str(arbeit / "daten.json"),
            "--ausgabe", str(arbeit / "neu.docx"),
            *extra,
        ]
    )  # fmt: skip


def test_ohne_anfrage_wird_nur_der_bestand_eingesetzt(arbeit, capsys):
    assert lauf(arbeit) == 0
    assert absaetze(arbeit / "neu.docx") == [
        "Mietvertrag fuer Musterweg 1, 8000 Zuerich",
        "Mieter: Bert Beispiel, Beginn 01.01.2026",
        "Netto 1'200.00 plus NK 200.00, Kaution 3'600.00",
    ]
    assert "keine Aenderungen" in capsys.readouterr().out


def test_anfrage_ueberschreibt_felder_und_bericht_nennt_sie(arbeit, capsys):
    (arbeit / "anfrage.txt").write_text(
        "Hallo\nMieter name: Anna Muster\nMietbeginn: 01.12.2026\nGruss", encoding="utf-8"
    )
    assert lauf(arbeit, "--anfrage", str(arbeit / "anfrage.txt")) == 0
    text = absaetze(arbeit / "neu.docx")
    assert text[1] == "Mieter: Anna Muster, Beginn 01.12.2026"
    out = capsys.readouterr().out
    assert "mieter_name: Bert Beispiel -> Anna Muster" in out
    assert "mietbeginn: 01.01.2026 -> 01.12.2026" in out
    assert "kaution" not in out


def test_fehlende_felder_fuer_die_vorlage_sind_exit_1_ohne_ausgabedatei(arbeit, capsys):
    daten = {k: v for k, v in DATEN.items() if k != "kaution"}
    (arbeit / "daten.json").write_text(json.dumps(daten), encoding="utf-8")
    assert lauf(arbeit) == 1
    assert "kaution" in capsys.readouterr().err
    assert not (arbeit / "neu.docx").exists()


def test_fehler_sind_exit_1_ohne_ausgabedatei(arbeit):
    (arbeit / "anfrage.txt").write_text("Miete netto: viel", encoding="utf-8")
    assert lauf(arbeit, "--anfrage", str(arbeit / "anfrage.txt")) == 1
    assert not (arbeit / "neu.docx").exists()
    (arbeit / "daten.json").write_text("{kaputt", encoding="utf-8")
    assert lauf(arbeit) == 1
    (arbeit / "vorlage.docx").unlink()
    assert lauf(arbeit) == 1


def test_vorhandene_ausgabedatei_wird_nie_ueberschrieben(arbeit):
    (arbeit / "neu.docx").write_bytes(b"alt")
    assert lauf(arbeit) == 1
    assert (arbeit / "neu.docx").read_bytes() == b"alt"


def test_aufruffehler_sind_exit_2(arbeit):
    assert main(["--unbekannt"]) == 2
    assert main(["--vorlage", str(arbeit / "vorlage.docx")]) == 2


def test_selbsttest(capsys):
    assert main(["--selbsttest"]) == 0
    assert "Selbsttest OK" in capsys.readouterr().out
