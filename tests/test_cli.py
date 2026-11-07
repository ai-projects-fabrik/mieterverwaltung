"""Tests fuer projekt.cli mit synthetischen Dateien."""

import io
import json
import zipfile

import pytest

from projekt.cli import main

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DATEN = {
    "mieter_name": "Bert Beispiel",
    "objekt": "Musterweg 1, 8000 Zuerich",
    "mietbeginn": "2026-01-01",
    "miete_netto": 1200,
    "nebenkosten": 200,
    "kaution": 3600,
}


def docx_bytes(absaetze):
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>'
    for absatz in absaetze:
        xml += f'<w:p><w:r><w:t xml:space="preserve">{absatz}</w:t></w:r></w:p>'
    xml += "</w:body></w:document>"
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as paket:
        paket.writestr("[Content_Types].xml", "<Types/>")
        paket.writestr("word/document.xml", xml)
    return puffer.getvalue()


@pytest.fixture
def arbeit(tmp_path):
    (tmp_path / "vorlage.docx").write_bytes(
        docx_bytes(
            [
                "Mietvertrag fuer {{objekt}}",
                "Mieter: {{mieter_name}}, Beginn {{mietbeginn}}",
                "Netto {{miete_netto}} plus NK {{nebenkosten}}, Kaution {{kaution}}",
            ]
        )
    )
    (tmp_path / "daten.json").write_text(json.dumps(DATEN), encoding="utf-8")
    return tmp_path


def lauf(arbeit, *extra):
    return main(
        [
            "--vorlage",
            str(arbeit / "vorlage.docx"),
            "--daten",
            str(arbeit / "daten.json"),
            "--ausgabe",
            str(arbeit / "neu.docx"),
            *extra,
        ]
    )


def test_anfrage_ergaenzt_fehlendes_feld_und_bericht_nennt_es(arbeit, capsys):
    daten = {key: wert for key, wert in DATEN.items() if key != "kaution"}
    (arbeit / "daten.json").write_text(json.dumps(daten), encoding="utf-8")
    (arbeit / "anfrage.txt").write_text("Kaution: 3000\n", encoding="utf-8")

    assert lauf(arbeit, "--anfrage", str(arbeit / "anfrage.txt")) == 0
    assert "kaution: (leer) -> 3'000.00" in capsys.readouterr().out
    assert (arbeit / "neu.docx").exists()


def test_unbekanntes_feld_in_daten_ist_fehler_ohne_ausgabe(arbeit, capsys):
    (arbeit / "daten.json").write_text(json.dumps({"unbekannt": "x"}), encoding="utf-8")

    assert lauf(arbeit) == 1
    assert "unbekannt" in capsys.readouterr().err
    assert not (arbeit / "neu.docx").exists()


def test_mehrere_fehlende_platzhalter_werden_genannt(arbeit, capsys):
    daten = {"mieter_name": "Bert Beispiel"}
    (arbeit / "daten.json").write_text(json.dumps(daten), encoding="utf-8")

    assert lauf(arbeit) == 1
    fehler = capsys.readouterr().err
    assert "objekt" in fehler
    assert "mietbeginn" in fehler
    assert not (arbeit / "neu.docx").exists()


def test_ungueltiges_json_und_nicht_objekt_sind_fehler(arbeit, capsys):
    (arbeit / "daten.json").write_text("{kaputt", encoding="utf-8")
    assert lauf(arbeit) == 1
    assert "JSON" in capsys.readouterr().err

    (arbeit / "daten.json").write_text("[]", encoding="utf-8")
    assert lauf(arbeit) == 1
    assert not (arbeit / "neu.docx").exists()


def test_anfrage_muss_utf8_sein(arbeit, capsys):
    (arbeit / "anfrage.txt").write_bytes(b"Kaution: \xff\n")

    assert lauf(arbeit, "--anfrage", str(arbeit / "anfrage.txt")) == 1
    assert "UTF-8" in capsys.readouterr().err
    assert not (arbeit / "neu.docx").exists()


def test_fehlende_dateien_sind_fehler(arbeit, capsys):
    (arbeit / "anfrage.txt").unlink(missing_ok=True)
    assert lauf(arbeit, "--anfrage", str(arbeit / "anfrage.txt")) == 1
    assert "Anfragedatei" in capsys.readouterr().err

    assert lauf(arbeit, "--vorlage", str(arbeit / "fehlt.docx")) == 1
    assert not (arbeit / "neu.docx").exists()


def test_vorhandene_ausgabe_bleibt_auch_bei_fehlerhaften_daten_unveraendert(arbeit):
    (arbeit / "neu.docx").write_bytes(b"alt")
    (arbeit / "daten.json").write_text("{kaputt", encoding="utf-8")

    assert lauf(arbeit) == 1
    assert (arbeit / "neu.docx").read_bytes() == b"alt"


def test_fehler_beim_anlegen_der_ausgabe_ist_exit_1(arbeit, capsys):
    arbeit2 = arbeit / "fehlt"
    assert (
        main(
            [
                "--vorlage",
                str(arbeit / "vorlage.docx"),
                "--daten",
                str(arbeit / "daten.json"),
                "--ausgabe",
                str(arbeit2 / "neu.docx"),
            ]
        )
        == 1
    )
    assert "Ausgabedatei" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--vorlage", "vorlage.docx", "--daten", "daten.json"],
        ["--vorlage"],
        ["--unbekannt"],
    ],
)
def test_aufruffehler_sind_exit_2_ohne_ausnahme(argv, capsys):
    assert main(argv) == 2
    assert capsys.readouterr().err


def test_selbsttest_ohne_dateien(capsys):
    assert main(["--selbsttest"]) == 0
    assert capsys.readouterr().out == "Selbsttest OK\n"


def test_selbsttest_fehler_sind_exit_1(monkeypatch, capsys):
    def kaputt(*_args, **_kwargs):
        raise ValueError("kaputt")

    monkeypatch.setattr("projekt.cli.fuelle", kaputt)
    assert main(["--selbsttest"]) == 1
    assert "kaputt" in capsys.readouterr().err
