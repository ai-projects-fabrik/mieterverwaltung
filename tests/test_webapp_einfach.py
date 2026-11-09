"""Tests fuer Routing und Formularverarbeitung in projekt.webapp_einfach."""

import html
import io
import json
import zipfile
from urllib.parse import urlencode

import pytest

import projekt.webapp_einfach as webapp_einfach
from projekt.webapp_einfach import antwort

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
HINWEIS = "PDF wird in Google Drive erzeugt und erscheint in wenigen Minuten in MV-pdf."
VERTRAG = [
    "Mietvertrag fuer {{objekt}}",
    "Mieter: {{mieter_name}}, Beginn {{mietbeginn}}",
    "Netto {{miete_netto}} plus NK {{nebenkosten}}, Kaution {{kaution}}",
]
PROTOKOLL = [
    "{{art}}: {{mieter_name}} in {{objekt}} am {{uebergabedatum}}",
    "Strom {{zaehler_strom}}, Wasser {{zaehler_wasser}}, Schluessel {{schluessel_anzahl}}",
    "Bemerkungen: {{bemerkungen}}",
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
    for absatz in absaetze:
        xml += f'<w:p><w:r><w:t xml:space="preserve">{absatz}</w:t></w:r></w:p>'
    xml += "</w:body></w:document>"
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as paket:
        paket.writestr("[Content_Types].xml", "<Types/>")
        paket.writestr("word/document.xml", xml)
    return puffer.getvalue()


def seite(ergebnis):
    return html.unescape(ergebnis[2].decode("utf-8"))


def post(kontext, pfad, felder, kopf=FORM):
    return antwort("POST", pfad, kopf, urlencode(felder).encode("utf-8"), kontext)


@pytest.fixture
def kontext(tmp_path):
    for name in ("vl", "vd", "al", "ad"):
        (tmp_path / name).mkdir()
    for name in ("MV-zu-pdf", "MV-pdf", "MV-erledigt"):
        (tmp_path / "drive" / name).mkdir(parents=True)
    (tmp_path / "vl" / "vertrag.docx").write_bytes(docx_bytes(VERTRAG))
    (tmp_path / "vl" / "uebergabe.docx").write_bytes(docx_bytes(PROTOKOLL))
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


def vertragsfelder(**extra):
    return {
        "objekt_id": "weg-1",
        "vorlage": "lokal:vertrag.docx",
        "mieter_name": "Erika Muster",
        "mietbeginn": "1.2.2027",
        "format": "docx",
        "ziel": "lokal",
        "anfrage": "",
        **extra,
    }


def test_einstellungen_datei_ist_pflicht(tmp_path):
    for kontext in (None, {}, {"einstellungen_datei": ""}, {"einstellungen_datei": 5}):
        status, kopf, koerper = antwort("GET", "/settings", {}, b"", kontext)
        assert status == 400
        assert kopf["Content-Type"].startswith("text/html")
        assert "einstellungen_datei" in html.unescape(koerper.decode("utf-8"))

    status, _, koerper = antwort("POST", "/objekte", FORM, b"", {"einstellungen_datei": 5})
    assert status == 400 and "einstellungen_datei" in seite((status, {}, koerper))


def test_ungueltige_methode_und_ungueltiger_pfad_typ_geben_400(tmp_path):
    kontext = {"einstellungen_datei": tmp_path / "fehlt.json", "home": str(tmp_path)}
    assert antwort(5, "/", {}, b"", kontext)[0] == 400
    assert antwort("GET", None, {}, b"", kontext)[0] == 400
    assert antwort("GET", "/gibt-es-nicht", {}, b"", kontext)[0] == 404
    assert antwort("POST", "/objekte", FORM, "kein bytes", kontext)[0] == 400


def test_fehlende_leere_und_kaputte_einstellungen_nutzen_standard_ohne_schreiben(tmp_path):
    drive = tmp_path / "meinlaufwerk"
    drive.mkdir()
    standard = tmp_path / "Documents" / "Mietverwaltung"

    for nummer, inhalt in enumerate((None, "", "{kaputt", "{}")):
        datei = tmp_path / f"e{nummer}.json"
        if inhalt is not None:
            datei.write_text(inhalt, encoding="utf-8")
        ctx = {
            "einstellungen_datei": datei,
            "home": str(tmp_path),
            "drive_kandidaten": [str(drive)],
        }
        status, _, koerper = antwort("GET", "/settings", {}, b"", ctx)
        text = seite((status, {}, koerper))
        assert status == 200 and str(drive) in text and str(standard) in text
        assert not standard.exists()
        if inhalt is None:
            assert not datei.exists()
        else:
            assert datei.read_text(encoding="utf-8") == inhalt


def test_get_seiten_lesen_objekte_und_vorlagen_bei_jeder_anfrage_neu(kontext, tmp_path):
    text = seite(antwort("GET", "/mietvertrag", {}, b"", kontext))
    assert 'value="weg-1"' in text and "lokal:vertrag.docx" in text

    objekte = [OBJEKT, {"id": "neu-1", "bezeichnung": "Neubau 2"}]
    (tmp_path / "objekte.json").write_text(json.dumps(objekte), encoding="utf-8")
    (tmp_path / "vl" / "zweitvertrag.docx").write_bytes(docx_bytes(VERTRAG))

    text = seite(antwort("GET", "/mietvertrag", {}, b"", kontext))
    assert 'value="neu-1"' in text and "lokal:zweitvertrag.docx" in text


def test_get_objekte_und_protokoll_ohne_objekte_zeigen_hinweise(tmp_path):
    ctx = {"einstellungen_datei": tmp_path / "fehlt.json", "home": str(tmp_path)}
    objekte = seite(antwort("GET", "/objekte", {}, b"", ctx))
    protokoll = seite(antwort("GET", "/protokoll", {}, b"", ctx))
    assert "zeile_0_bezeichnung" in objekte
    assert "Bitte zuerst unter" in protokoll and "Objekte" in protokoll


def test_settings_post_nimmt_charset_und_ersten_doppelten_wert(tmp_path):
    drive1, drive2, lokal = tmp_path / "drive1", tmp_path / "drive2", tmp_path / "lokal"
    drive1.mkdir()
    drive2.mkdir()
    ctx = {"einstellungen_datei": tmp_path / "e.json", "home": str(tmp_path)}
    koerper = urlencode(
        [
            ("drive_ordner", str(drive1)),
            ("drive_ordner", str(drive2)),
            ("lokaler_ordner", str(lokal)),
        ]
    ).encode("utf-8")
    kopf = {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}
    status, _, _ = antwort("POST", "/settings", kopf, koerper, ctx)
    assert status == 200
    gespeichert = json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))
    assert gespeichert["drive_wurzel"] == str(drive1)


def test_settings_ungueltiger_lokaler_ordner_speichert_nichts(tmp_path):
    drive = tmp_path / "drive"
    drive.mkdir()
    ctx = {"einstellungen_datei": tmp_path / "e.json", "home": str(tmp_path)}
    status, _, koerper = post(ctx, "/settings", {"drive_ordner": str(drive), "lokaler_ordner": ""})
    assert status == 400 and "Lokaler Ordner" in seite((status, {}, koerper))
    assert not (tmp_path / "e.json").exists()


def test_settings_schreibfehler_geben_400_mit_eingaben(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("kein Ordner", encoding="utf-8")
    drive, lokal = tmp_path / "drive", tmp_path / "lokal"
    drive.mkdir()
    ctx = {"einstellungen_datei": blocker / "e.json", "home": str(tmp_path)}
    status, _, koerper = post(
        ctx, "/settings", {"drive_ordner": str(drive), "lokaler_ordner": str(lokal)}
    )
    text = seite((status, {}, koerper))
    assert status == 400 and str(drive) in text and "Ordner" in text
    assert blocker.read_text(encoding="utf-8") == "kein Ordner"


def test_objekte_fehler_bei_fehlendem_ordner_bleibt_400(tmp_path):
    objekte_datei = tmp_path / "fehlt" / "objekte.json"
    datei = tmp_path / "e.json"
    datei.write_text(json.dumps({"objekte_datei": str(objekte_datei)}), encoding="utf-8")
    ctx = {"einstellungen_datei": datei, "home": str(tmp_path)}
    status, _, koerper = post(ctx, "/objekte", {"zeile_0_bezeichnung": "Neu"})
    text = seite((status, {}, koerper))
    assert status == 400 and "Ordner" in text and "Neu" in text
    assert not objekte_datei.exists() and not objekte_datei.parent.exists()


def test_mietvertrag_mit_pdf_auftrag_zeigt_dateien_und_hinweis(kontext, tmp_path):
    status, _, koerper = post(kontext, "/mietvertrag", vertragsfelder(format="docx+pdf"))
    text = seite((status, {}, koerper))
    assert status == 200 and "vertrag-erika-muster.docx" in text and HINWEIS in text
    assert (tmp_path / "al" / "vertrag-erika-muster.docx").is_file()
    assert (tmp_path / "drive" / "MV-zu-pdf" / "vertrag-erika-muster.docx").is_file()


def test_protokoll_erstellen_und_auswahl_merken(kontext, tmp_path):
    felder = {
        "objekt_id": "weg-1",
        "vorlage": "lokal:uebergabe.docx",
        "mieter_name": "Erika Muster",
        "uebergabedatum": "1.2.2027",
        "art": "Einzug",
        "zaehler_strom": "100",
        "zaehler_wasser": "20.5",
        "schluessel_anzahl": "3",
        "bemerkungen": "keine",
        "format": "docx",
        "ziel": "lokal",
    }
    status, _, koerper = post(kontext, "/protokoll", felder)
    text = seite((status, {}, koerper))
    assert status == 200 and "Dateien angelegt" in text
    assert "uebergabeprotokoll-erika-muster.docx" in text
    gemerkt = json.loads((tmp_path / "letzte_auswahl.json").read_text(encoding="utf-8"))
    assert gemerkt["protokoll_vorlage"] == "lokal:uebergabe.docx"


def test_fehler_beim_merken_wird_ignoriert(kontext, monkeypatch):
    def fehlschlag(*_args, **_kwargs):
        raise OSError("Testschreibfehler")

    monkeypatch.setattr(webapp_einfach, "speichere_auswahl", fehlschlag)
    status, _, koerper = post(kontext, "/mietvertrag", vertragsfelder())
    assert status == 200 and "vertrag-erika-muster.docx" in seite((status, {}, koerper))


def test_leerer_vorlagenordner_zeigt_hinweis_und_keine_leere_gruppe(kontext, tmp_path):
    for pfad in ("/mietvertrag", "/protokoll"):
        text = seite(antwort("GET", pfad, {}, b"", kontext))
        assert f"Keine Vorlage (.docx) gefunden in {tmp_path / 'vd'}" in text
        assert f"gefunden in {tmp_path / 'vl'}" not in text
        assert 'label="Festplatte"' in text and 'label="Google Drive"' not in text
        assert "Google-Docs-Dateien" not in text


def test_gdoc_im_vorlagenordner_zeigt_speichertipp(kontext, tmp_path):
    (tmp_path / "vd" / "Vertrag.gdoc").write_text("{}", encoding="utf-8")
    text = seite(antwort("GET", "/mietvertrag", {}, b"", kontext))
    assert "Google-Docs-Dateien bitte als .docx speichern" in text
    assert "Datei > Herunterladen > Microsoft Word" in text


def test_fehlender_vorlagenordner_zeigt_hinweis_mit_pfad(kontext, tmp_path):
    (tmp_path / "vd").rmdir()
    text = seite(antwort("GET", "/mietvertrag", {}, b"", kontext))
    assert f"Keine Vorlage (.docx) gefunden in {tmp_path / 'vd'}" in text


def test_fehlerseite_nach_fehlgeschlagenem_auftrag_zeigt_ebenfalls_den_hinweis(kontext, tmp_path):
    status, _, koerper = post(
        kontext, "/mietvertrag", {"vorlage": "lokal:fehlt.docx", "mieter_name": "A"}
    )
    assert status == 400
    assert "Keine Vorlage (.docx) gefunden in" in seite((status, {}, koerper))
