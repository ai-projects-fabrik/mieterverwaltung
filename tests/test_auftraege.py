"""Tests fuer projekt.auftraege mit synthetischen Vorlagen und Daten."""

import io
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile

import pytest

import projekt.auftraege as auftraege
from projekt.auftraege import (
    FORMATE,
    HERKUNFT,
    erstelle_protokoll,
    erstelle_vertrag,
    protokoll_werte,
    slug,
)
from projekt.protokoll import PROTOKOLL_FELDER

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
VERTRAG = [
    "{{objekt}}",
    "{{mieter_name}}",
    "{{mietbeginn}}",
    "{{miete_netto}}",
    "{{nebenkosten}}",
    "{{kaution}}",
]
PROTOKOLL = [
    "{{art}}",
    "{{mieter_name}}",
    "{{objekt}}",
    "{{uebergabedatum}}",
    "{{zaehler_strom}}",
    "{{zaehler_wasser}}",
    "{{schluessel_anzahl}}",
    "{{bemerkungen}}",
]


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


def absaetze(pfad):
    with zipfile.ZipFile(pfad) as paket:
        wurzel = ET.fromstring(paket.read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(f"{{{W}}}t")) for p in wurzel.iter(f"{{{W}}}p")]


@pytest.fixture
def umgebung(tmp_path):
    ordner = {name: tmp_path / name for name in ("vl", "vd", "al", "ad")}
    for pfad in ordner.values():
        pfad.mkdir()
    drive = tmp_path / "drive"
    ordner["pe"] = drive / "MV-zu-pdf"
    for pfad in (drive, ordner["pe"]):
        pfad.mkdir()

    (ordner["vl"] / "vertrag.docx").write_bytes(docx_bytes(VERTRAG))
    (ordner["vl"] / "protokoll.docx").write_bytes(docx_bytes(PROTOKOLL))
    (ordner["vd"] / "drive-vertrag.docx").write_bytes(docx_bytes(VERTRAG))
    objekte = [
        {
            "id": "weg-1",
            "bezeichnung": "Musterweg 1",
            "miete_netto": "1'200.00",
            "nebenkosten": "200.00",
            "kaution": "3'600.00",
        }
    ]
    objekte_datei = tmp_path / "objekte.json"
    objekte_datei.write_text(json.dumps(objekte), encoding="utf-8")
    return {
        "einstellungen": {
            "objekte_datei": str(objekte_datei),
            "vorlagen_lokal": str(ordner["vl"]),
            "vorlagen_drive": str(ordner["vd"]),
            "ausgabe_lokal": str(ordner["al"]),
            "ausgabe_drive": str(ordner["ad"]),
            "drive_wurzel": str(drive),
        },
        "ordner": ordner,
    }


def vertragsform():
    return {
        "objekt_id": "weg-1",
        "vorlage": "lokal:vertrag.docx",
        "format": "docx",
        "ziel": "lokal",
        "mieter_name": "Anna Muster",
        "mietbeginn": "2026-01-01",
        "anfrage": "",
    }


def protokollform():
    return {
        "objekt_id": "weg-1",
        "vorlage": "lokal:protokoll.docx",
        "format": "docx",
        "ziel": "lokal",
        "mieter_name": "Anna Muster",
        "uebergabedatum": "2026-02-01",
        "art": "einzug",
        "zaehler_strom": "1234.50",
        "zaehler_wasser": "56",
        "schluessel_anzahl": "3",
        "bemerkungen": "keine",
    }


def namen(umgebung, schluessel):
    pfad = umgebung["ordner"][schluessel]
    return sorted(eintrag.name for eintrag in pfad.iterdir()) if pfad.is_dir() else []


def keine_dateien(umgebung):
    return all(not namen(umgebung, schluessel) for schluessel in ("al", "ad", "pe"))


def test_formate_und_slug():
    assert FORMATE == ("docx", "pdf", "docx+pdf")
    assert slug("Anna Müller-Meier") == "anna-mueller-meier"
    assert slug("GROSS & SÖHNE") == "gross-soehne"
    assert slug("ÄÖÜ") == "aeoeue"
    assert slug("  --A__B--  ") == "a-b"
    assert slug("***") == "unbenannt"
    assert slug("") == "unbenannt"
    with pytest.raises(ValueError, match="text"):
        slug(None)


def test_vertrag_nutzt_standardwerte_und_objektbestand(umgebung):
    form = vertragsform()
    del form["format"]
    del form["ziel"]
    ergebnis = erstelle_vertrag(form, umgebung)

    assert ergebnis["dateien"] == ["vertrag-anna-muster.docx"]
    assert ergebnis["pdf_auftrag"] is None
    assert ergebnis["hinweis"] == ""
    assert ergebnis["bericht"] == "keine Aenderungen"
    assert namen(umgebung, "al") == ["vertrag-anna-muster.docx"]
    assert absaetze(umgebung["ordner"]["al"] / "vertrag-anna-muster.docx") == [
        "Musterweg 1",
        "Anna Muster",
        "01.01.2026",
        "1'200.00",
        "200.00",
        "3'600.00",
    ]


def test_leere_und_weisse_formularwerte_lassen_bestand_stehen(umgebung):
    for leer in ("", "   "):
        ergebnis = erstelle_vertrag(
            {**vertragsform(), "miete_netto": leer, "nebenkosten": leer}, umgebung
        )
        text = absaetze(umgebung["ordner"]["al"] / ergebnis["dateien"][0])
        assert text[3:5] == ["1'200.00", "200.00"]


def test_ohne_objekt_genuegen_formularwerte(umgebung):
    einstellungen = dict(umgebung["einstellungen"])
    del einstellungen["objekte_datei"]
    form = {
        "vorlage": "lokal:vertrag.docx",
        "mieter_name": "Cora Test",
        "objekt": "Haus 9",
        "mietbeginn": "01.03.2026",
        "miete_netto": "900",
        "nebenkosten": "100",
        "kaution": "2700",
    }
    ergebnis = erstelle_vertrag(form, {"einstellungen": einstellungen})
    assert ergebnis["dateien"] == ["vertrag-cora-test.docx"]


def test_fehlender_platzhalter_nennt_feld_und_schreibt_nichts(umgebung):
    form = {
        "vorlage": "lokal:vertrag.docx",
        "mieter_name": "Cora Test",
        "objekt": "Haus 9",
        "mietbeginn": "01.03.2026",
        "miete_netto": "900",
        "nebenkosten": "100",
    }
    with pytest.raises(ValueError, match="kaution"):
        erstelle_vertrag(form, umgebung)
    assert keine_dateien(umgebung)


def test_anfrage_ueberschreibt_nur_genannte_felder(umgebung):
    form = {**vertragsform(), "anfrage": "Mieter name: Bert Beispiel\nKaution: 4000"}
    ergebnis = erstelle_vertrag(form, umgebung)

    assert ergebnis["dateien"] == ["vertrag-bert-beispiel.docx"]
    assert "mieter_name: Anna Muster -> Bert Beispiel" in ergebnis["bericht"]
    assert "kaution: 3'600.00 -> 4'000.00" in ergebnis["bericht"]
    assert "mietbeginn" not in ergebnis["bericht"]


def test_herkunft_der_vertragswerte_folgt_formular_objekt_und_anfrage(umgebung):
    form = {
        **vertragsform(),
        "miete_netto": "1300",
        "anfrage": "Mieter name: Bert Beispiel\nKaution: 3600",
    }
    ergebnis = erstelle_vertrag(form, umgebung)

    assert HERKUNFT == ("formular", "objekt", "anfrage")
    assert ergebnis["werte"] == [
        {"feld": "mieter_name", "wert": "Bert Beispiel", "herkunft": "anfrage"},
        {"feld": "objekt", "wert": "Musterweg 1", "herkunft": "objekt"},
        {"feld": "mietbeginn", "wert": "01.01.2026", "herkunft": "formular"},
        {"feld": "miete_netto", "wert": "1'300.00", "herkunft": "formular"},
        {"feld": "nebenkosten", "wert": "200.00", "herkunft": "objekt"},
        {"feld": "kaution", "wert": "3'600.00", "herkunft": "anfrage"},
    ]


def test_vertragswerte_enthalten_nur_gesetzte_felder_in_feldreihenfolge(umgebung):
    (umgebung["ordner"]["vl"] / "nur-name.docx").write_bytes(docx_bytes(["{{mieter_name}}"]))
    ergebnis = erstelle_vertrag(
        {"vorlage": "lokal:nur-name.docx", "mieter_name": "Cora Test"}, umgebung
    )
    assert ergebnis["werte"] == [
        {"feld": "mieter_name", "wert": "Cora Test", "herkunft": "formular"}
    ]


@pytest.mark.parametrize(
    "zeile",
    [
        "Bitte die Miete erhoehen",
        "Hinweis: bis Freitag",
        "Miete netto 1300",
    ],
)
def test_unverstandene_anfragezeile_nennt_zeile_und_schreibt_nichts(umgebung, zeile):
    with pytest.raises(ValueError) as fehler:
        erstelle_vertrag({**vertragsform(), "anfrage": f"Kaution: 4000\n{zeile}"}, umgebung)

    meldung = str(fehler.value)
    assert zeile in meldung
    assert "Feld: Wert" in meldung
    assert "anfrage" in meldung.casefold()
    assert keine_dateien(umgebung)


def test_zitierte_und_leere_anfragezeilen_bleiben_erlaubt(umgebung):
    form = {
        **vertragsform(),
        "anfrage": "\r\n  > Hinweis: nicht auswerten\r\nMIETE NETTO: 1300\r\n",
    }
    ergebnis = erstelle_vertrag(form, umgebung)
    werte = {eintrag["feld"]: eintrag for eintrag in ergebnis["werte"]}
    assert werte["miete_netto"] == {
        "feld": "miete_netto",
        "wert": "1'300.00",
        "herkunft": "anfrage",
    }


def test_protokoll_werte_haben_feldreihenfolge_und_herkunft(umgebung):
    werte = protokoll_werte(protokollform(), umgebung)
    assert [eintrag["feld"] for eintrag in werte] == list(PROTOKOLL_FELDER)
    assert werte == [
        {"feld": "mieter_name", "wert": "Anna Muster", "herkunft": "formular"},
        {"feld": "objekt", "wert": "Musterweg 1", "herkunft": "objekt"},
        {"feld": "uebergabedatum", "wert": "01.02.2026", "herkunft": "formular"},
        {"feld": "art", "wert": "Einzug", "herkunft": "formular"},
        {"feld": "zaehler_strom", "wert": "1234.5", "herkunft": "formular"},
        {"feld": "zaehler_wasser", "wert": "56", "herkunft": "formular"},
        {"feld": "schluessel_anzahl", "wert": "3", "herkunft": "formular"},
        {"feld": "bemerkungen", "wert": "keine", "herkunft": "formular"},
    ]
    assert "werte" not in erstelle_protokoll(protokollform(), umgebung)


def test_protokoll_werte_nutzt_formularobjekt_und_meldet_fehler(umgebung):
    werte = protokoll_werte({**protokollform(), "objekt": "Formularweg 2"}, umgebung)
    objekt = next(eintrag for eintrag in werte if eintrag["feld"] == "objekt")
    assert objekt == {
        "feld": "objekt",
        "wert": "Formularweg 2",
        "herkunft": "formular",
    }
    with pytest.raises(ValueError, match="art"):
        protokoll_werte({**protokollform(), "art": "Besichtigung"}, umgebung)


def test_vorlage_ohne_platzhalter_ist_fehler_und_schreibt_nichts(umgebung):
    leer = docx_bytes(["Ganze Vorlage ohne Platzhalter"])
    for ort in ("vl", "vd"):
        (umgebung["ordner"][ort] / "leer.docx").write_bytes(leer)
    for auswahl in ("lokal:leer.docx", "drive:leer.docx"):
        with pytest.raises(ValueError, match="Vorlage enthaelt keine Platzhalter"):
            erstelle_vertrag({**vertragsform(), "vorlage": auswahl}, umgebung)
        with pytest.raises(ValueError, match="Vorlage enthaelt keine Platzhalter"):
            erstelle_protokoll({**protokollform(), "vorlage": auswahl}, umgebung)
    with pytest.raises(ValueError, match="Vorlage enthaelt keine Platzhalter"):
        erstelle_vertrag(
            {**vertragsform(), "vorlage": "google:abc"},
            {**umgebung, "vorlage_bytes": leer},
        )
    assert keine_dateien(umgebung)


def test_pdf_und_docx_pdf_schreiben_csv_und_hinweis(umgebung):
    ergebnis = erstelle_vertrag({**vertragsform(), "format": "pdf"}, umgebung)
    assert ergebnis["dateien"] == []
    assert ergebnis["pdf_auftrag"] == "vertrag-anna-muster.docx"
    assert ergebnis["hinweis"].startswith("PDF wird in Google Drive erzeugt")
    assert namen(umgebung, "pe") == ["vertrag-anna-muster.docx"]
    assert namen(umgebung, "al") == []

    ergebnis = erstelle_vertrag({**vertragsform(), "format": "docx+pdf"}, umgebung)
    assert ergebnis["dateien"] == ["vertrag-anna-muster.docx"]
    assert ergebnis["pdf_auftrag"] == "vertrag-anna-muster-2.docx"


def test_reines_pdf_braucht_keinen_ausgabeordner(umgebung):
    umgebung["ordner"]["al"].rmdir()
    ergebnis = erstelle_vertrag({**vertragsform(), "format": "pdf"}, umgebung)
    assert ergebnis["pdf_auftrag"] == "vertrag-anna-muster.docx"


@pytest.mark.parametrize(
    ("aenderung", "erwartet"),
    [
        ({"objekt_id": "fehlt"}, "objekt_id"),
        ({"vorlage": "vertrag.docx"}, "vorlage"),
        ({"vorlage": "cloud:vertrag.docx"}, "vorlage"),
        ({"vorlage": "lokal:"}, "vorlage"),
        ({"vorlage": "lokal:../vertrag.docx"}, "vorlage"),
        ({"format": "odt"}, "format"),
        ({"ziel": "cloud"}, "ziel"),
        ({"anfrage": "Miete netto: viel"}, "miete_netto"),
        ({"mieter_name": 5}, "mieter_name"),
    ],
)
def test_vertragsfehler_nennen_feld_und_schreiben_nichts(umgebung, aenderung, erwartet):
    with pytest.raises(ValueError, match=erwartet):
        erstelle_vertrag({**vertragsform(), **aenderung}, umgebung)
    assert keine_dateien(umgebung)


def test_falsche_typen_und_kontexte_werden_abgelehnt(umgebung):
    with pytest.raises(ValueError, match="form"):
        erstelle_vertrag([], umgebung)
    with pytest.raises(ValueError, match="einstellungen"):
        erstelle_vertrag(vertragsform(), {})
    for feld in ("objekt_id", "vorlage", "format", "ziel", "anfrage"):
        with pytest.raises(ValueError, match=feld):
            erstelle_vertrag({**vertragsform(), feld: 1}, umgebung)


def test_fehlende_objekteinstellung_und_unbekanntes_objekt(umgebung):
    einstellungen = dict(umgebung["einstellungen"])
    del einstellungen["objekte_datei"]
    with pytest.raises(ValueError, match="objekte_datei"):
        erstelle_vertrag(vertragsform(), {"einstellungen": einstellungen})
    assert keine_dateien(umgebung)


def test_fehlende_ordner_nennen_schluessel_und_schreiben_nichts(umgebung):
    shutil.rmtree(umgebung["ordner"]["vl"])
    with pytest.raises(ValueError, match="vorlagen_lokal"):
        erstelle_vertrag(vertragsform(), umgebung)
    assert keine_dateien(umgebung)


def test_fehlender_ausgabeordner_nennt_schluessel(umgebung):
    umgebung["ordner"]["al"].rmdir()
    with pytest.raises(ValueError, match="ausgabe_lokal"):
        erstelle_vertrag(vertragsform(), umgebung)
    assert keine_dateien(umgebung)


def test_fehlender_pdf_ordner_nennt_mv_zu_pdf_und_schreibt_nichts(umgebung):
    umgebung["ordner"]["pe"].rmdir()
    with pytest.raises(ValueError, match="MV-zu-pdf"):
        erstelle_vertrag({**vertragsform(), "format": "docx+pdf"}, umgebung)
    assert namen(umgebung, "al") == namen(umgebung, "ad") == []


def test_ungueltige_vorlage_nennt_vorlage(umgebung):
    (umgebung["ordner"]["vl"] / "vertrag.docx").write_bytes(b"kein zip")
    with pytest.raises(ValueError, match="vorlage"):
        erstelle_vertrag(vertragsform(), umgebung)
    assert keine_dateien(umgebung)


def test_schreibfehler_rollt_bereits_angelegte_datei_zurueck(umgebung, monkeypatch):
    echt = auftraege.schreibe_ausgabe
    aufrufe = []

    def scheitert_beim_zweiten(ordner_pfad, name, daten):
        aufrufe.append(name)
        if len(aufrufe) == 2:
            raise ValueError("Schreiben fehlgeschlagen")
        return echt(ordner_pfad, name, daten)

    monkeypatch.setattr(auftraege, "schreibe_ausgabe", scheitert_beim_zweiten)
    with pytest.raises(ValueError, match="Schreiben fehlgeschlagen"):
        erstelle_vertrag({**vertragsform(), "format": "docx+pdf"}, umgebung)
    assert namen(umgebung, "al") == namen(umgebung, "pe") == []


def test_protokoll_hat_nur_die_drei_ergebnissschluessel(umgebung):
    ergebnis = erstelle_protokoll(protokollform(), umgebung)
    assert set(ergebnis) == {"dateien", "pdf_auftrag", "hinweis"}
    assert ergebnis["dateien"] == ["uebergabeprotokoll-anna-muster.docx"]
    assert absaetze(umgebung["ordner"]["al"] / ergebnis["dateien"][0]) == [
        "Einzug",
        "Anna Muster",
        "Musterweg 1",
        "01.02.2026",
        "1234.5",
        "56",
        "3",
        "keine",
    ]


def test_protokoll_nutzt_objekt_nur_fuer_objekt(umgebung):
    form = {**protokollform(), "objekt_id": "weg-1", "objekt": "Formularweg 2"}
    ergebnis = erstelle_protokoll(form, umgebung)
    assert absaetze(umgebung["ordner"]["al"] / ergebnis["dateien"][0])[2] == "Formularweg 2"


@pytest.mark.parametrize(
    ("aenderung", "erwartet"),
    [
        ({"art": "Besichtigung"}, "art"),
        ({"zaehler_strom": "-1"}, "zaehler_strom"),
        ({"uebergabedatum": "2026-02-30"}, "uebergabedatum"),
        ({"bemerkungen": "{{kaution}}"}, "bemerkungen"),
        ({"mieter_name": 5}, "mieter_name"),
        ({"vorlage": "lokal:fehlt.docx"}, "vorlage"),
    ],
)
def test_protokollfehler_nennen_feld_und_schreiben_nichts(umgebung, aenderung, erwartet):
    with pytest.raises(ValueError, match=erwartet):
        erstelle_protokoll({**protokollform(), **aenderung}, umgebung)
    assert keine_dateien(umgebung)


def test_protokoll_pdf_und_platzhalterfehler(umgebung):
    ergebnis = erstelle_protokoll({**protokollform(), "format": "pdf"}, umgebung)
    assert ergebnis["dateien"] == []
    assert ergebnis["pdf_auftrag"] == "uebergabeprotokoll-anna-muster.docx"
    assert namen(umgebung, "pe") == ["uebergabeprotokoll-anna-muster.docx"]

    form = {**protokollform(), "bemerkungen": ""}
    form["vorlage"] = "lokal:protokoll.docx"
    with pytest.raises(ValueError, match="bemerkungen"):
        erstelle_protokoll(form, umgebung)
    assert namen(umgebung, "al") == []


def test_google_vorlage_kommt_aus_dem_kontext_und_nichts_wird_lokal_gelesen(umgebung):
    form = vertragsform()
    form["vorlage"] = "google:abc123"
    kontext = {**umgebung, "vorlage_bytes": docx_bytes(VERTRAG)}
    ergebnis = erstelle_vertrag(form, kontext)
    assert ergebnis["dateien"] == ["vertrag-anna-muster.docx"]
    assert absaetze(umgebung["ordner"]["al"] / "vertrag-anna-muster.docx")[1] == "Anna Muster"

    form = protokollform()
    form["vorlage"] = "google:abc123"
    kontext = {**umgebung, "vorlage_bytes": docx_bytes(PROTOKOLL)}
    assert erstelle_protokoll(form, kontext)["dateien"] == ["uebergabeprotokoll-anna-muster.docx"]


def test_google_vorlage_ohne_geladene_bytes_ist_ein_fehler_und_schreibt_nichts(umgebung):
    form = vertragsform()
    form["vorlage"] = "google:abc123"
    for kontext in (
        umgebung,
        {**umgebung, "vorlage_bytes": b""},
        {**umgebung, "vorlage_bytes": "x"},
    ):
        with pytest.raises(ValueError, match="vorlage"):
            erstelle_vertrag(form, kontext)
    assert keine_dateien(umgebung)


def docx_mit_kopfzeile(absaetze, kopf):
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>'
    for absatz in absaetze:
        xml += f'<w:p><w:r><w:t xml:space="preserve">{absatz}</w:t></w:r></w:p>'
    xml += "</w:body></w:document>"
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as paket:
        paket.writestr("[Content_Types].xml", "<Types/>")
        paket.writestr("word/document.xml", xml)
        paket.writestr(
            "word/header1.xml",
            f'<w:hdr xmlns:w="{W}"><w:p><w:r><w:t>{kopf}</w:t></w:r></w:p></w:hdr>',
        )
    return puffer.getvalue()


def kopftext(pfad):
    with zipfile.ZipFile(pfad) as paket:
        wurzel = ET.fromstring(paket.read("word/header1.xml"))
    return "".join(t.text or "" for t in wurzel.iter(f"{{{W}}}t"))


def test_kopfzeile_wird_gefuellt(umgebung):
    vorlage = docx_mit_kopfzeile(VERTRAG, "Vertrag mit {{mieter_name}}")
    (umgebung["ordner"]["vl"] / "kopf.docx").write_bytes(vorlage)
    ergebnis = erstelle_vertrag(
        {**vertragsform(), "vorlage": "lokal:kopf.docx", "mieter_name": "Anna Muster"},
        umgebung,
    )
    ziel = umgebung["ordner"]["al"] / ergebnis["dateien"][0]
    assert absaetze(ziel)[1] == "Anna Muster"
    assert kopftext(ziel) == "Vertrag mit Anna Muster"


@pytest.mark.parametrize(
    ("absaetze", "kopf", "stelle"),
    [
        ([*VERTRAG, "Nutzer {{Mieter_Name}}"], "Kopf", "Text: {{Mieter_Name}}"),
        (VERTRAG, "Kopf {{Name des Mieters}}", "Kopfzeile: {{Name des Mieters}}"),
    ],
)
def test_nicht_ersetzte_platzhalter_nennen_stelle_und_schreiben_nichts(
    umgebung, absaetze, kopf, stelle
):
    (umgebung["ordner"]["vl"] / "kaputt.docx").write_bytes(docx_mit_kopfzeile(absaetze, kopf))
    with pytest.raises(ValueError, match="vorlage") as fehler:
        erstelle_vertrag({**vertragsform(), "vorlage": "lokal:kaputt.docx"}, umgebung)
    assert "Nicht ersetzte Platzhalter" in str(fehler.value)
    assert stelle in str(fehler.value)
    assert keine_dateien(umgebung)


def test_nicht_ersetzte_platzhalter_im_protokoll_schreiben_nichts(umgebung):
    vorlage = docx_mit_kopfzeile(PROTOKOLL, "Kopf {{Name des Mieters}}")
    (umgebung["ordner"]["vl"] / "kopf-protokoll.docx").write_bytes(vorlage)
    with pytest.raises(ValueError, match="Kopfzeile: \\{\\{Name des Mieters\\}\\}"):
        erstelle_protokoll({**protokollform(), "vorlage": "lokal:kopf-protokoll.docx"}, umgebung)
    assert keine_dateien(umgebung)
