"""Tests fuer projekt.gui mit synthetischen Vertragsdaten."""

import html
import io
import json
import re
import zipfile

import pytest

import projekt.gui as gui
from projekt.gui import antwort, main, starte

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
GRENZE = "----mvgrenze"
DATEN = {
    "mieter_name": "Bert Beispiel",
    "objekt": "Musterweg 1, 8000 Zuerich",
    "mietbeginn": "2026-01-01",
    "miete_netto": 1200,
    "nebenkosten": 200,
    "kaution": 3600,
}


def docx_bytes(absaetze=None):
    if absaetze is None:
        absaetze = [
            "Mietvertrag fuer {{objekt}}",
            "Mieter: {{mieter_name}}, Beginn {{mietbeginn}}",
            "Netto {{miete_netto}} plus NK {{nebenkosten}}, Kaution {{kaution}}",
        ]
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>'
    for absatz in absaetze:
        xml += f'<w:p><w:r><w:t xml:space="preserve">{absatz}</w:t></w:r></w:p>'
    xml += "</w:body></w:document>"
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as paket:
        paket.writestr("[Content_Types].xml", "<Types/>")
        paket.writestr("word/document.xml", xml)
    return puffer.getvalue()


def multipart(felder=None, dateien=None):
    felder = felder or {}
    dateien = dateien or {}
    teile = []
    for name, wert in felder.items():
        kopf = f'--{GRENZE}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
        teile.append(f"{kopf}{wert}\r\n".encode())
    for name, (dateiname, inhalt) in dateien.items():
        kopf = (
            f'--{GRENZE}\r\nContent-Disposition: form-data; name="{name}"; '
            f'filename="{dateiname}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        )
        teile.append(kopf.encode() + inhalt + b"\r\n")
    teile.append(f"--{GRENZE}--\r\n".encode())
    return {"Content-Type": f"multipart/form-data; boundary={GRENZE}"}, b"".join(teile)


def erstelle(felder=None, daten=None):
    dateien = {"vorlage": ("v.docx", docx_bytes())}
    if daten is not False:
        dateien["daten"] = ("d.json", json.dumps(DATEN if daten is None else daten).encode())
    return antwort("POST", "/erstellen", *multipart(felder, dateien))


def text(daten):
    return html.unescape(daten.decode("utf-8"))


def test_leere_und_unbekannte_formularfelder_werden_ignoriert():
    status, _, koerper = erstelle({"mieter_name": "   ", "unbekannt": "egal"})
    assert status == 200
    assert "keine Aenderungen" in text(koerper)


def test_json_muss_ein_objekt_sein_und_fehler_nennt_daten():
    status, _, koerper = erstelle(daten=[])
    assert status == 400
    assert "daten" in text(koerper)


def test_fehlertexte_werden_maskiert():
    status, _, koerper = erstelle(daten={"<script>x</script>": "1"})
    assert status == 400
    assert "<script>" not in koerper.decode("utf-8")
    assert "&lt;script&gt;" in koerper.decode("utf-8")


def test_vorlage_und_daten_muessen_dateien_sein():
    kopf, koerper = multipart({"vorlage": "kein dokument"}, {"daten": ("d.json", b"{}")})
    status, _, seite = antwort("POST", "/erstellen", kopf, koerper)
    assert status == 400
    assert "vorlage" in text(seite)

    kopf, koerper = multipart({"daten": "{}"}, {"vorlage": ("v.docx", docx_bytes())})
    status, _, seite = antwort("POST", "/erstellen", kopf, koerper)
    assert status == 400
    assert "daten" in text(seite)


@pytest.mark.parametrize(
    ("kopf", "koerper"),
    [
        ({"Content-Type": "text/plain"}, b"x"),
        ({"Content-Type": "multipart/form-data"}, b"x"),
        ({"Content-Type": f"multipart/form-data; boundary={GRENZE}"}, b"kaputt"),
        ({"Content-Type": f"multipart/form-data; boundary={GRENZE}"}, b"--andere--\r\n"),
    ],
)
def test_kaputtes_multipart_ist_400(kopf, koerper):
    status, _, _ = antwort("POST", "/erstellen", kopf, koerper)
    assert status == 400


def test_zu_grosser_koerper_ist_413_ohne_download():
    kopf = {"Content-Type": f"multipart/form-data; boundary={GRENZE}"}
    status, _, koerper = antwort("POST", "/erstellen", kopf, b"x" * (5 * 1024 * 1024 + 1))
    assert status == 413
    assert "/download/" not in koerper.decode("utf-8")


def test_download_ist_nur_mit_get_und_kleinbuchstaben_token_erreichbar():
    status, _, seite = erstelle()
    assert status == 200
    token = re.search(r"/download/([0-9a-f]{32})", seite.decode("utf-8")).group(1)

    assert antwort("POST", f"/download/{token}", {}, b"")[0] == 405
    assert antwort("GET", "/download/" + token.upper(), {}, b"")[0] == 404


def test_starte_normalisiert_localhost_und_lehnt_ungueltige_ports_ab():
    server = starte(host="localhost", port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()

    for port in (-1, 65536, True, "8765"):
        with pytest.raises(ValueError, match="Port"):
            starte(port=port)


def test_main_lehnt_negativen_und_zu_grossen_port_ab(capsys):
    assert main(["--port", "-1"]) == 2
    assert main(["--port", "65536"]) == 2
    assert "Port" in capsys.readouterr().err


def test_selbsttest_braucht_keinen_socket(monkeypatch):
    def kein_server(*args, **kwargs):
        raise AssertionError("Selbsttest darf keinen Server starten")

    monkeypatch.setattr(gui, "starte", kein_server)
    assert main(["--selbsttest"]) == 0
