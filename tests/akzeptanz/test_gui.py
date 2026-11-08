"""Akzeptanztest (spec-first) fuer projekt.gui: Beispiele aus dem Ziel `mv-gui`."""

import html
import importlib.util
import io
import json
import re
import threading
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import pytest

if importlib.util.find_spec("projekt.gui") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.gui import antwort, main, starte  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX_TYP = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
GRENZE = "----mvgrenze"
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


def docx_bytes(absaetze=VORLAGE_TEXT):
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


def multipart(felder, dateien):
    """felder: {name: text}; dateien: {name: (dateiname, bytes)}."""
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
    return b"".join(teile)


def erstelle(felder=None, vorlage=True, daten=True, vorlage_bytes=None):
    dateien = {}
    if vorlage:
        inhalt = vorlage_bytes if vorlage_bytes is not None else docx_bytes()
        dateien["vorlage"] = ("v.docx", inhalt)
    if daten:
        dateien["daten"] = ("d.json", json.dumps(DATEN).encode())
    koerper = multipart(felder or {}, dateien)
    kopf = {"Content-Type": f"multipart/form-data; boundary={GRENZE}"}
    return antwort("POST", "/erstellen", kopf, koerper)


def kopfwert(antwort_kopf, name):
    return {k.lower(): v for k, v in antwort_kopf.items()}.get(name.lower(), "")


def text(daten):
    return html.unescape(daten.decode("utf-8"))


def test_startseite_ist_html_mit_formular():
    status, k, koerper = antwort("GET", "/", {}, b"")
    assert status == 200
    assert kopfwert(k, "Content-Type").startswith("text/html")
    seite = koerper.decode("utf-8")
    assert "<form" in seite
    assert "multipart/form-data" in seite
    assert 'action="/erstellen"' in seite
    for name in ("vorlage", "daten", "anfrage", *DATEN):
        assert f'name="{name}"' in seite


def test_unbekannte_pfade_und_methoden():
    assert antwort("GET", "/gibt-es-nicht", {}, b"")[0] == 404
    assert antwort("GET", "/erstellen", {}, b"")[0] == 405
    assert antwort("POST", "/", {}, b"")[0] == 405


def test_erstellen_ohne_anfrage_liefert_bericht_und_download():
    status, k, koerper = erstelle()
    assert status == 200
    assert kopfwert(k, "Content-Type").startswith("text/html")
    assert "keine Aenderungen" in text(koerper)
    link = re.search(r"/download/([0-9a-f]{32})", koerper.decode("utf-8"))
    assert link
    status, k, vertrag = antwort("GET", link.group(0), {}, b"")
    assert status == 200
    assert kopfwert(k, "Content-Type") == DOCX_TYP
    assert "attachment" in kopfwert(k, "Content-Disposition")
    assert absaetze(vertrag) == [
        "Mietvertrag fuer Musterweg 1, 8000 Zuerich",
        "Mieter: Bert Beispiel, Beginn 01.01.2026",
        "Netto 1'200.00 plus NK 200.00, Kaution 3'600.00",
    ]


def test_formularfelder_und_anfrage_aendern_den_vertrag():
    felder = {
        "kaution": "4000",
        "anfrage": "Hallo\r\nMieter name: Anna Muster\r\nMietbeginn: 01.12.2026\r\nGruss",
    }
    status, _, koerper = erstelle(felder)
    assert status == 200
    seite = text(koerper)
    assert "mieter_name: Bert Beispiel -> Anna Muster" in seite
    assert "mietbeginn: 01.01.2026 -> 01.12.2026" in seite
    link = re.search(r"/download/[0-9a-f]{32}", koerper.decode("utf-8")).group(0)
    vertrag = antwort("GET", link, {}, b"")[2]
    assert absaetze(vertrag)[1] == "Mieter: Anna Muster, Beginn 01.12.2026"
    assert absaetze(vertrag)[2].endswith("Kaution 4'000.00")


def test_bestand_nur_aus_formularfeldern_ohne_json():
    felder = {name: str(wert) for name, wert in DATEN.items()}
    status, _, koerper = erstelle(felder, daten=False)
    assert status == 200
    assert "keine Aenderungen" in text(koerper)


@pytest.mark.parametrize(
    ("felder", "daten", "vorlage", "nennt"),
    [
        ({"anfrage": "Miete netto: viel"}, True, True, "miete_netto"),
        ({"mietbeginn": "2026-02-30"}, True, True, "mietbeginn"),
        ({}, True, False, "vorlage"),
        ({}, False, True, "kaution"),
    ],
)
def test_fehler_sind_400_mit_klartext_ohne_download(felder, daten, vorlage, nennt):
    status, _, koerper = erstelle(felder, vorlage=vorlage, daten=daten)
    assert status == 400
    assert nennt in text(koerper)
    assert "/download/" not in koerper.decode("utf-8")


def test_vorlage_ohne_docx_und_kaputtes_json_sind_400():
    assert erstelle(vorlage_bytes=b"kein zip")[0] == 400
    kopf = {"Content-Type": f"multipart/form-data; boundary={GRENZE}"}
    koerper = multipart({}, {"vorlage": ("v.docx", docx_bytes()), "daten": ("d.json", b"{kaputt")})
    assert antwort("POST", "/erstellen", kopf, koerper)[0] == 400
    assert antwort("POST", "/erstellen", {"Content-Type": "text/plain"}, b"x")[0] == 400


def test_eingaben_werden_in_der_antwort_maskiert():
    status, _, koerper = erstelle({"mieter_name": "<script>alert(1)</script>"})
    assert status == 200
    assert "<script>" not in koerper.decode("utf-8")
    status, _, koerper = erstelle({"anfrage": "Kaution: <b>x</b>"})
    assert status == 400
    assert "<b>" not in koerper.decode("utf-8")


def test_download_mit_unbekanntem_oder_ungueltigem_token_ist_404():
    assert antwort("GET", "/download/" + "0" * 32, {}, b"")[0] == 404
    for pfad in (
        "/download/",
        "/download/../x",
        "/download/XYZ",
        "/download/" + "a" * 100,
    ):
        assert antwort("GET", pfad, {}, b"")[0] == 404


def test_zu_grosse_anfrage_ist_413():
    kopf = {"Content-Type": f"multipart/form-data; boundary={GRENZE}"}
    assert antwort("POST", "/erstellen", kopf, b"x" * (6 * 1024 * 1024))[0] == 413


def test_server_bindet_nur_an_loopback():
    for host in ("0.0.0.0", "", "192.168.1.5", "example.org"):
        with pytest.raises(ValueError):
            starte(host=host, port=0)
    server = starte(port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        with urllib.request.urlopen(url, timeout=10) as r:
            assert r.status == 200
            assert "<form" in r.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()


def test_aufruf_selbsttest_und_fehler(capsys):
    assert main(["--selbsttest"]) == 0
    assert "Selbsttest OK" in capsys.readouterr().out
    assert main(["--unbekannt"]) == 2
    assert main(["--port", "abc"]) == 2
