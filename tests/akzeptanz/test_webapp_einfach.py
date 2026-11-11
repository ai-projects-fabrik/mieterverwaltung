"""Akzeptanztest (spec-first) fuer projekt.webapp_einfach (Ziel `mv-webapp-einfach`)."""

import html
import importlib.util
import inspect
import io
import json
import zipfile
from urllib.parse import urlencode

import pytest

if importlib.util.find_spec("projekt.webapp_einfach") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.webapp_einfach import antwort  # noqa: E402

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


def seite(ergebnis):
    return html.unescape(ergebnis[2].decode("utf-8"))


def post(kontext, pfad, felder):
    return antwort("POST", pfad, FORM, urlencode(felder).encode("utf-8"), kontext)


@pytest.fixture
def kontext(tmp_path):
    """Einstellungen im alten Format (muessen weiter lesbar sein) mit einem Objekt."""
    for name in ("vl", "vd", "al", "ad"):
        (tmp_path / name).mkdir()
    for name in ("MV-zu-pdf", "MV-pdf", "MV-erledigt"):
        (tmp_path / "drive" / name).mkdir(parents=True)
    (tmp_path / "vl" / "mietvertrag.docx").write_bytes(docx_bytes(VERTRAG))
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
    return {"einstellungen_datei": datei, "home": str(tmp_path / "home")}


def test_wurzel_leitet_auf_mietvertrag_und_methoden_werden_geprueft(kontext):
    assert antwort("GET", "/", {}, b"", kontext)[:2] == (302, {"Location": "/mietvertrag"})
    assert antwort("POST", "/", FORM, b"", kontext)[0] == 405
    assert antwort("PUT", "/objekte", {}, b"", kontext)[0] == 405
    assert antwort("GET", "/gibt-es-nicht", {}, b"", kontext)[0] == 404
    assert antwort("GET", "/settings?x=1", {}, b"", kontext)[0] == 200


def test_alle_vier_seiten_laden_mit_navigation(kontext):
    for pfad in ("/mietvertrag", "/protokoll", "/objekte", "/settings"):
        status, kopf, koerper = antwort("GET", pfad, {}, b"", kontext)
        assert status == 200 and kopf["Content-Type"].startswith("text/html")
        text = koerper.decode("utf-8")
        assert all(
            f'href="/{t}"' in text for t in ("mietvertrag", "protokoll", "objekte", "settings")
        )


def test_settings_zeigt_nur_zwei_felder_auch_fuer_alte_einstellungen(kontext, tmp_path):
    text = seite(antwort("GET", "/settings", {}, b"", kontext))
    assert text.count("<input") == 2
    assert 'value="' + str(tmp_path / "drive") + '"' in text
    assert 'value="' + str(tmp_path) + '"' in text
    assert "objekte_datei" not in text and "vorlagen_lokal" not in text


def test_ohne_einstellungsdatei_gelten_die_standardordner(tmp_path):
    ctx = {
        "einstellungen_datei": tmp_path / "gibt-es-nicht.json",
        "home": str(tmp_path),
        "drive_kandidaten": [str(tmp_path / "meinlaufwerk")],
    }
    (tmp_path / "meinlaufwerk").mkdir()
    text = seite(antwort("GET", "/settings", {}, b"", ctx))
    assert str(tmp_path / "meinlaufwerk") in text
    assert str(tmp_path / "Documents" / "Mietverwaltung") in text
    assert not (tmp_path / "Documents").exists()
    assert not ctx["einstellungen_datei"].exists()
    assert antwort("GET", "/mietvertrag", {}, b"", ctx)[0] == 200


def test_settings_speichern_legt_unterordner_an(tmp_path):
    drive, lokal = tmp_path / "drive", tmp_path / "lokal"
    drive.mkdir()
    ctx = {"einstellungen_datei": tmp_path / "e.json", "home": str(tmp_path)}
    status, _, _ = post(
        ctx, "/settings", {"drive_ordner": str(drive), "lokaler_ordner": str(lokal)}
    )
    assert status == 200
    gespeichert = json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))
    assert gespeichert["drive_wurzel"] == str(drive)
    assert gespeichert["objekte_datei"] == str(lokal / "objekte.json")
    for ordner in (
        lokal / "Vorlagen",
        lokal / "Ausgabe",
        drive / "Mietverwaltung" / "Vorlagen",
        drive / "Mietverwaltung" / "Ausgabe",
        drive / "MV-zu-pdf",
    ):
        assert ordner.is_dir()


def test_settings_ohne_drive_speichert_trotzdem_mit_hinweis(tmp_path):
    ctx = {"einstellungen_datei": tmp_path / "e.json", "home": str(tmp_path)}
    felder = {"drive_ordner": str(tmp_path / "fehlt"), "lokaler_ordner": str(tmp_path / "lokal")}
    status, _, koerper = post(ctx, "/settings", felder)
    assert status == 200 and "Google-Drive-Ordner" in seite((status, {}, koerper))
    assert (tmp_path / "e.json").exists()


def test_settings_fehler_geben_400_ohne_speichern(tmp_path):
    ctx = {"einstellungen_datei": tmp_path / "e.json", "home": str(tmp_path)}
    status, _, koerper = post(ctx, "/settings", {"drive_ordner": "", "lokaler_ordner": "x"})
    assert status == 400 and "Google-Drive-Ordner" in seite((status, {}, koerper))
    assert not (tmp_path / "e.json").exists()


def test_objekte_speichern_vergibt_ids_und_entfernt_leere_zeilen(kontext, tmp_path):
    felder = {
        "zeile_0_id": "weg-1",
        "zeile_0_bezeichnung": "Musterweg 1a",
        "zeile_0_miete_netto": "1300",
        "zeile_1_bezeichnung": "Seeblick 5",
        "zeile_1_kaution": "CHF 4000",
        "zeile_2_bezeichnung": "",
    }
    status, _, koerper = post(kontext, "/objekte", felder)
    assert status == 200 and "Gespeichert" in seite((status, {}, koerper))
    gespeichert = json.loads((tmp_path / "objekte.json").read_text(encoding="utf-8"))
    assert [o["id"] for o in gespeichert] == ["seeblick-5", "weg-1"]
    assert gespeichert[1]["bezeichnung"] == "Musterweg 1a"
    assert gespeichert[1]["miete_netto"] == "1'300.00"
    post(kontext, "/objekte", {"zeile_0_id": "weg-1", "zeile_0_bezeichnung": ""})
    assert json.loads((tmp_path / "objekte.json").read_text(encoding="utf-8")) == []


def test_objekte_fehler_geben_400_und_lassen_die_datei_unveraendert(kontext, tmp_path):
    vorher = (tmp_path / "objekte.json").read_bytes()
    status, _, koerper = post(
        kontext, "/objekte", {"zeile_0_bezeichnung": "Neu", "zeile_0_miete_netto": "viel"}
    )
    text = seite((status, {}, koerper))
    assert status == 400 and "Miete netto (CHF)" in text and "viel" in text
    assert (tmp_path / "objekte.json").read_bytes() == vorher


def test_mietvertrag_vorbelegt_und_ohne_betragsfragen(kontext):
    text = seite(antwort("GET", "/mietvertrag", {}, b"", kontext))
    assert '<option value="weg-1" selected>' in text
    assert '<option value="lokal:mietvertrag.docx" selected>' in text
    assert '<option value="docx+pdf" selected>' in text
    assert '<option value="drive" selected>' in text
    for gestrichen in ("miete_netto", "nebenkosten", "kaution", 'name="objekt"'):
        assert gestrichen not in text


def test_mietvertrag_erstellen_fuellt_betraege_aus_dem_objekt_und_merkt_die_auswahl(
    kontext, tmp_path
):
    felder = {
        "objekt_id": "weg-1",
        "vorlage": "lokal:mietvertrag.docx",
        "mieter_name": "Erika Muster",
        "mietbeginn": "1.2.2027",
        "format": "docx",
        "ziel": "lokal",
    }
    status, _, koerper = post(kontext, "/mietvertrag", felder)
    text = seite((status, {}, koerper))
    assert status == 200 and "vertrag-erika-muster.docx" in text
    ausgabe = tmp_path / "al" / "vertrag-erika-muster.docx"
    with zipfile.ZipFile(ausgabe) as z:
        inhalt = z.read("word/document.xml").decode("utf-8")
    for erwartet in ("Musterweg 1, 8000 Zuerich", "Erika Muster", "01.02.2027", "1&apos;200.00"):
        assert erwartet.replace("&apos;", "'") in inhalt
    gemerkt = json.loads((tmp_path / "letzte_auswahl.json").read_text(encoding="utf-8"))
    assert gemerkt == {
        "objekt_id": "weg-1",
        "vertrag_vorlage": "lokal:mietvertrag.docx",
        "format": "docx",
        "ziel": "lokal",
    }
    neu = seite(antwort("GET", "/mietvertrag", {}, b"", kontext))
    assert '<option value="docx" selected>' in neu and '<option value="lokal" selected>' in neu


def test_mietvertrag_fehler_geben_400_mit_ausgefuelltem_formular_und_merken_nichts(
    kontext, tmp_path
):
    felder = {
        "objekt_id": "weg-1",
        "vorlage": "lokal:mietvertrag.docx",
        "mieter_name": "Erika <Muster>",
        "mietbeginn": "kein datum",
        "format": "docx",
        "ziel": "lokal",
    }
    status, _, koerper = post(kontext, "/mietvertrag", felder)
    text = seite((status, {}, koerper))
    assert status == 400 and "mietbeginn" in text and "Erika <Muster>" in text
    assert list((tmp_path / "al").iterdir()) == []
    assert not (tmp_path / "letzte_auswahl.json").exists()


def test_protokoll_erstellen_ohne_vorlage_gibt_400(kontext):
    felder = {
        "objekt_id": "weg-1",
        "mieter_name": "E",
        "uebergabedatum": "1.2.2027",
        "art": "Einzug",
    }
    assert post(kontext, "/protokoll", felder)[0] == 400


def test_fehlerhafte_anfragen_geben_4xx_nie_5xx(kontext):
    assert antwort("POST", "/objekte", {}, b"a=b", kontext)[0] == 400
    assert antwort("POST", "/objekte", FORM, b"\xff\xfe", kontext)[0] == 400
    assert antwort("POST", "/objekte", FORM, b"x" * (1024 * 1024 + 1), kontext)[0] == 413
    assert antwort("GET", "/mietvertrag", {}, b"", {})[0] == 400
    assert antwort(5, "/", {}, b"", kontext)[0] == 400


# --- Ziel `mv-webapp-werte`: Ergebnisseite mit allen Werten, klare Fehler fuer Aenderungstext ---


def _werte_umgesetzt():
    import projekt.auftraege
    from projekt.seiten import ergebnis

    return hasattr(projekt.auftraege, "HERKUNFT") and (
        "werte" in inspect.signature(ergebnis).parameters
    )


ERGEBNIS_WERTE = pytest.mark.skipif(
    not _werte_umgesetzt(), reason="Eingesetzte Werte noch nicht umgesetzt"
)

PROTOKOLL = ["{{art}}: {{mieter_name}} in {{objekt}} am {{uebergabedatum}}"]


def vertrag_felder(**zusatz):
    return {
        "objekt_id": "weg-1",
        "vorlage": "lokal:mietvertrag.docx",
        "mieter_name": "Erika Muster",
        "mietbeginn": "1.2.2027",
        "format": "docx",
        "ziel": "lokal",
        **zusatz,
    }


@ERGEBNIS_WERTE
def test_ergebnisseite_zeigt_alle_werte_mit_herkunft(kontext):
    felder = vertrag_felder(anfrage="Kaution: 4000", miete_netto="1300")
    status, _, koerper = post(kontext, "/mietvertrag", felder)
    text = seite((status, {}, koerper))
    assert status == 200
    for zeile in (
        "Name des Mieters: Erika Muster (aus Formular)",
        "Objekt: Musterweg 1, 8000 Zuerich (aus Objekt)",
        "Mietbeginn: 01.02.2027 (aus Formular)",
        "Nebenkosten: 200.00 (aus Objekt)",
        "Kaution: 4'000.00 (aus Änderungen)",
    ):
        assert zeile in text
    assert "keine Aenderungen" not in text


@ERGEBNIS_WERTE
def test_unverstandener_aenderungstext_gibt_400_mit_zeile_und_schreibt_nichts(kontext, tmp_path):
    felder = vertrag_felder(anfrage="Kaution: 4000\nBitte die Miete erhoehen")
    status, _, koerper = post(kontext, "/mietvertrag", felder)
    text = seite((status, {}, koerper))
    assert status == 400
    assert "Bitte die Miete erhoehen" in text and "Feld: Wert" in text
    assert "Erika Muster" in text  # Formular bleibt ausgefuellt
    assert list((tmp_path / "al").iterdir()) == []
    assert not (tmp_path / "letzte_auswahl.json").exists()


@ERGEBNIS_WERTE
def test_protokoll_ergebnisseite_zeigt_werte(kontext, tmp_path):
    (tmp_path / "vl" / "uebergabe.docx").write_bytes(docx_bytes(PROTOKOLL))
    felder = {
        "objekt_id": "weg-1",
        "vorlage": "lokal:uebergabe.docx",
        "mieter_name": "Erika Muster",
        "uebergabedatum": "1.2.2027",
        "art": "einzug",
        "format": "docx",
        "ziel": "lokal",
    }
    status, _, koerper = post(kontext, "/protokoll", felder)
    text = seite((status, {}, koerper))
    assert status == 200
    assert "Name des Mieters: Erika Muster (aus Formular)" in text
    assert "Objekt: Musterweg 1, 8000 Zuerich (aus Objekt)" in text
    assert "Dateien angelegt" in text
