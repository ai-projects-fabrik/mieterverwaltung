"""Akzeptanztest (spec-first) fuer projekt.webapp (Ziel `mv-webapp`)."""

import html
import importlib.util
import io
import json
import zipfile
from urllib.parse import urlencode

import pytest

if importlib.util.find_spec("projekt.webapp") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.webapp import antwort  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
VERTRAG = [
    "Mietvertrag fuer {{objekt}}",
    "Mieter: {{mieter_name}}, Beginn {{mietbeginn}}",
    "Netto {{miete_netto}} plus NK {{nebenkosten}}, Kaution {{kaution}}",
]
OBJEKT = {
    "id": "weg-1",
    "bezeichnung": "Musterweg 1, 8000 Zuerich",
    "miete_netto": "1'200.00",
    "nebenkosten": "200.00",
    "kaution": "3'600.00",
}


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


@pytest.fixture
def kontext(tmp_path):
    for name in ("vl", "vd", "al", "ad"):
        (tmp_path / name).mkdir()
    for name in ("MV-zu-pdf", "MV-pdf", "MV-erledigt"):
        (tmp_path / "drive" / name).mkdir(parents=True)
    (tmp_path / "vl" / "vertrag.docx").write_bytes(docx_bytes(VERTRAG))
    (tmp_path / "vd" / "drive.docx").write_bytes(docx_bytes(VERTRAG))
    (tmp_path / "objekte.json").write_text(json.dumps([OBJEKT]), encoding="utf-8")
    einstellungen = {
        "objekte_datei": str(tmp_path / "objekte.json"),
        "vorlagen_lokal": str(tmp_path / "vl"),
        "vorlagen_drive": str(tmp_path / "vd"),
        "ausgabe_lokal": str(tmp_path / "al"),
        "ausgabe_drive": str(tmp_path / "ad"),
        "drive_wurzel": str(tmp_path / "drive"),
    }
    datei = tmp_path / "einstellungen.json"
    datei.write_text(json.dumps(einstellungen), encoding="utf-8")
    return {"einstellungen_datei": datei}


def post(kontext, pfad, felder):
    return antwort("POST", pfad, FORM, urlencode(felder).encode("utf-8"), kontext)


def seite(ergebnis):
    return html.unescape(ergebnis[2].decode("utf-8"))


def ausgabe(kontext, ort="al"):
    ordner = kontext["einstellungen_datei"].parent / ort
    return sorted(p.name for p in ordner.iterdir())


def pdf_eingang(kontext):
    return ausgabe(kontext, "drive/MV-zu-pdf")


def vertrag_form(**extra):
    felder = {
        "objekt_id": "weg-1",
        "vorlage": "lokal:vertrag.docx",
        "format": "docx",
        "ziel": "lokal",
        "mieter_name": "Bert Beispiel",
        "mietbeginn": "2026-01-01",
    }
    return {**felder, **extra}


def test_get_seiten(kontext):
    status, kopf, _ = antwort("GET", "/", {}, b"", kontext)
    assert status == 302
    assert {k.lower(): v for k, v in kopf.items()}["location"] == "/mietvertrag"
    for pfad in ("/mietvertrag", "/protokoll", "/settings"):
        status, kopf, body = antwort("GET", pfad, {}, b"", kontext)
        assert status == 200
        assert {k.lower(): v for k, v in kopf.items()}["content-type"].startswith("text/html")
        assert b"<form" in body
    text = seite(antwort("GET", "/mietvertrag", {}, b"", kontext))
    assert 'value="weg-1"' in text
    assert "Musterweg 1, 8000 Zuerich" in text
    assert 'value="lokal:vertrag.docx"' in text
    assert 'value="drive:drive.docx"' in text


def test_unbekannt_und_falsche_methode(kontext):
    assert antwort("GET", "/gibt-es-nicht", {}, b"", kontext)[0] == 404
    assert antwort("POST", "/", FORM, b"", kontext)[0] == 405
    assert antwort("DELETE", "/mietvertrag", {}, b"", kontext)[0] == 405
    assert antwort("GET", "/download/abc", {}, b"", kontext)[0] == 404


def test_vertrag_wird_im_gewaehlten_ordner_angelegt(kontext):
    status, _, body = post(kontext, "/mietvertrag", vertrag_form())
    assert status == 200
    assert ausgabe(kontext) == ["vertrag-bert-beispiel.docx"]
    assert ausgabe(kontext, "ad") == []
    assert "vertrag-bert-beispiel.docx" in html.unescape(body.decode("utf-8"))
    status, _, _ = post(kontext, "/mietvertrag", vertrag_form(ziel="drive"))
    assert status == 200
    assert ausgabe(kontext, "ad") == ["vertrag-bert-beispiel.docx"]


def test_anfrage_bericht_und_nie_ueberschreiben(kontext):
    felder = vertrag_form(anfrage="Mieter name: Anna Muster")
    ergebnis = post(kontext, "/mietvertrag", felder)
    assert ergebnis[0] == 200
    assert "mieter_name: Bert Beispiel -> Anna Muster" in seite(ergebnis)
    assert post(kontext, "/mietvertrag", felder)[0] == 200
    assert ausgabe(kontext) == ["vertrag-anna-muster-2.docx", "vertrag-anna-muster.docx"]


def test_fehler_geben_400_mit_formular_und_schreiben_nichts(kontext):
    for aenderung, nennt in [
        ({"anfrage": "Kaution: <b>viel</b>"}, "kaution"),
        ({"vorlage": "lokal:../x.docx"}, "vorlage"),
        ({"objekt_id": "x"}, "objekt_id"),
        ({"format": "odt"}, "format"),
    ]:
        status, _, body = post(kontext, "/mietvertrag", vertrag_form(**aenderung))
        text = body.decode("utf-8")
        assert status == 400
        assert nennt in html.unescape(text)
        assert "<form" in text
        assert "<b>" not in text
    assert ausgabe(kontext) == []


def test_pdf_geht_ueber_den_google_ordner_mit_hinweis(kontext):
    status, _, body = post(kontext, "/mietvertrag", vertrag_form(format="pdf"))
    text = html.unescape(body.decode("utf-8"))
    assert status == 200
    assert ausgabe(kontext) == []
    assert pdf_eingang(kontext) == ["vertrag-bert-beispiel.docx"]
    assert "PDF wird in Google Drive erzeugt und erscheint in wenigen Minuten in MV-pdf." in text
    status, _, body = post(kontext, "/mietvertrag", vertrag_form(format="docx+pdf"))
    assert status == 200
    assert ausgabe(kontext) == ["vertrag-bert-beispiel.docx"]
    assert pdf_eingang(kontext) == ["vertrag-bert-beispiel-2.docx", "vertrag-bert-beispiel.docx"]
    (kontext["einstellungen_datei"].parent / "drive" / "MV-zu-pdf").rename(
        kontext["einstellungen_datei"].parent / "drive" / "weg"
    )
    status, _, body = post(kontext, "/mietvertrag", vertrag_form(format="pdf"))
    assert status == 400
    assert "MV-zu-pdf" in html.unescape(body.decode("utf-8"))


def test_nicht_konfiguriert_verweist_auf_settings(tmp_path):
    datei = tmp_path / "leer.json"
    kontext = {"einstellungen_datei": datei}
    status, _, body = antwort("GET", "/mietvertrag", {}, b"", kontext)
    assert status == 200
    assert b"<form" in body
    status, _, body = post(kontext, "/mietvertrag", vertrag_form())
    assert status == 400
    assert "Settings" in body.decode("utf-8") or "vorlagen_lokal" in body.decode("utf-8")


def test_protokoll(kontext):
    (kontext["einstellungen_datei"].parent / "vl" / "uebergabe.docx").write_bytes(
        docx_bytes(["{{art}} {{mieter_name}} {{objekt}} {{uebergabedatum}}"])
    )
    felder = {
        "objekt_id": "weg-1",
        "vorlage": "lokal:uebergabe.docx",
        "format": "docx",
        "ziel": "lokal",
        "mieter_name": "Anna Muster",
        "uebergabedatum": "2026-02-01",
        "art": "Einzug",
    }
    status, _, body = post(kontext, "/protokoll", felder)
    assert status == 200
    assert "uebergabeprotokoll-anna-muster.docx" in html.unescape(body.decode("utf-8"))
    assert ausgabe(kontext) == ["uebergabeprotokoll-anna-muster.docx"]
    assert post(kontext, "/protokoll", {**felder, "art": "Besuch"})[0] == 400
    assert ausgabe(kontext) == ["uebergabeprotokoll-anna-muster.docx"]


def test_settings_speichern_objekt_anlegen_und_entfernen(kontext, tmp_path):
    datei = kontext["einstellungen_datei"]
    felder = {
        "objekte_datei": str(tmp_path / "objekte.json"),
        "vorlagen_lokal": str(tmp_path / "vl"),
        "vorlagen_drive": "",
        "ausgabe_lokal": str(tmp_path / "al"),
        "ausgabe_drive": str(tmp_path / "ad"),
        "neu_id": "haus-2",
        "neu_bezeichnung": "Haus 2",
        "neu_miete_netto": "950",
    }
    status, _, body = post(kontext, "/settings", felder)
    assert status == 200
    gespeichert = json.loads(datei.read_text(encoding="utf-8"))
    assert "vorlagen_drive" not in gespeichert
    assert gespeichert["ausgabe_lokal"] == str(tmp_path / "al")
    objekte = json.loads((tmp_path / "objekte.json").read_text(encoding="utf-8"))
    assert [o["id"] for o in objekte] == ["haus-2", "weg-1"]
    assert objekte[0]["miete_netto"] == "950.00"
    assert "Haus 2" in html.unescape(body.decode("utf-8"))
    status, _, _ = post(
        kontext,
        "/settings",
        {
            **felder,
            "neu_id": "",
            "neu_bezeichnung": "",
            "neu_miete_netto": "",
            "entfernen": "weg-1",
        },
    )
    assert status == 200
    objekte = json.loads((tmp_path / "objekte.json").read_text(encoding="utf-8"))
    assert [o["id"] for o in objekte] == ["haus-2"]


def test_settings_fehler_aendern_nichts(kontext, tmp_path):
    datei = kontext["einstellungen_datei"]
    vorher = datei.read_text(encoding="utf-8")
    objekte_vorher = (tmp_path / "objekte.json").read_text(encoding="utf-8")
    felder = {
        "objekte_datei": str(tmp_path / "objekte.json"),
        "neu_id": "x",
        "neu_bezeichnung": "X",
    }
    for extra, nennt in [
        ({"neu_miete_netto": "viel"}, "miete_netto"),
        ({"neu_id": "Ungültig!"}, "id"),
    ]:
        status, _, body = post(kontext, "/settings", {**felder, **extra})
        assert status == 400
        assert nennt in html.unescape(body.decode("utf-8"))
    status, _, _ = post(kontext, "/settings", {"ausgabe_lokal": "a\x00b"})
    assert status == 400
    assert datei.read_text(encoding="utf-8") == vorher
    assert (tmp_path / "objekte.json").read_text(encoding="utf-8") == objekte_vorher


def test_eingabegrenzen_und_maskierung(kontext):
    gross = b"mieter_name=" + b"x" * (1024 * 1024 + 1)
    assert antwort("POST", "/mietvertrag", FORM, gross, kontext)[0] == 413
    assert antwort("POST", "/mietvertrag", {"Content-Type": "text/plain"}, b"x", kontext)[0] == 400
    status, _, body = post(kontext, "/mietvertrag", vertrag_form(mieter_name="<script>x</script>"))
    assert status == 200
    assert b"<script>" not in body
    status, _, _ = post(kontext, "/mietvertrag", vertrag_form(mieter_name="../../Evil"))
    assert status == 200
    assert "vertrag-evil.docx" in ausgabe(kontext)
