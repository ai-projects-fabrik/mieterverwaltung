"""Akzeptanztest (spec-first) fuer projekt.auftraege (Ziel `mv-auftraege`)."""

import importlib.util
import io
import json
import xml.etree.ElementTree as ET
import zipfile

import pytest

if importlib.util.find_spec("projekt.auftraege") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.auftraege import FORMATE, erstelle_protokoll, erstelle_vertrag, slug  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
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
ORDNER = ("vl", "vd", "al", "ad", "pe", "pa")


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
def kontext(tmp_path):
    ordner = {n: tmp_path / n for n in ORDNER}
    for pfad in ordner.values():
        pfad.mkdir()
    (ordner["vl"] / "vertrag.docx").write_bytes(docx_bytes(VERTRAG))
    (ordner["vd"] / "drive-vertrag.docx").write_bytes(docx_bytes(VERTRAG))
    (ordner["vl"] / "uebergabe.docx").write_bytes(docx_bytes(PROTOKOLL))
    objekte = [
        {
            "id": "weg-1",
            "bezeichnung": "Musterweg 1, 8000 Zuerich",
            "miete_netto": "1'200.00",
            "nebenkosten": "200.00",
            "kaution": "3'600.00",
        }
    ]
    (tmp_path / "objekte.json").write_text(json.dumps(objekte), encoding="utf-8")
    return {
        "einstellungen": {
            "objekte_datei": str(tmp_path / "objekte.json"),
            "vorlagen_lokal": str(ordner["vl"]),
            "vorlagen_drive": str(ordner["vd"]),
            "ausgabe_lokal": str(ordner["al"]),
            "ausgabe_drive": str(ordner["ad"]),
            "pdf_eingang": str(ordner["pe"]),
            "pdf_ausgabe": str(ordner["pa"]),
        },
        "ordner": ordner,
    }


def basis():
    return {
        "objekt_id": "weg-1",
        "vorlage": "lokal:vertrag.docx",
        "format": "docx",
        "ziel": "lokal",
        "mieter_name": "Bert Beispiel",
        "mietbeginn": "2026-01-01",
        "anfrage": "",
    }


def namen(kontext, ordner):
    return sorted(p.name for p in kontext["ordner"][ordner].iterdir())


def leer(kontext):
    return all(not namen(kontext, n) for n in ("al", "ad", "pe", "pa"))


def test_formate_und_slug():
    assert FORMATE == ("docx", "pdf", "docx+pdf")
    assert slug("Anna Müller-Meier") == "anna-mueller-meier"
    assert slug("../../Evil") == "evil"
    assert slug("Groß & Söhne AG") == "gross-soehne-ag"
    assert slug("") == "unbenannt"
    assert slug("***") == "unbenannt"


def test_vertrag_aus_objekt_und_formularfeldern(kontext):
    ergebnis = erstelle_vertrag(basis(), kontext)
    assert ergebnis["dateien"] == ["vertrag-bert-beispiel.docx"]
    assert ergebnis["pdf_auftrag"] is None
    assert ergebnis["hinweis"] == ""
    assert "keine Aenderungen" in ergebnis["bericht"]
    assert absaetze(kontext["ordner"]["al"] / "vertrag-bert-beispiel.docx") == [
        "Mietvertrag fuer Musterweg 1, 8000 Zuerich",
        "Mieter: Bert Beispiel, Beginn 01.01.2026",
        "Netto 1'200.00 plus NK 200.00, Kaution 3'600.00",
    ]
    assert namen(kontext, "ad") == namen(kontext, "pe") == namen(kontext, "pa") == []


def test_formularwerte_und_anfrage_ueberschreiben_schrittweise(kontext):
    form = {**basis(), "miete_netto": "1300", "anfrage": "Mieter name: Anna Muster\nKaution: 4000"}
    ergebnis = erstelle_vertrag(form, kontext)
    assert ergebnis["dateien"] == ["vertrag-anna-muster.docx"]
    assert "mieter_name: Bert Beispiel -> Anna Muster" in ergebnis["bericht"]
    assert "kaution: 3'600.00 -> 4'000.00" in ergebnis["bericht"]
    assert "miete_netto" not in ergebnis["bericht"]
    text = absaetze(kontext["ordner"]["al"] / "vertrag-anna-muster.docx")
    assert text[2] == "Netto 1'300.00 plus NK 200.00, Kaution 4'000.00"


def test_vorlage_und_ziel_drive(kontext):
    form = {**basis(), "vorlage": "drive:drive-vertrag.docx", "ziel": "drive"}
    ergebnis = erstelle_vertrag(form, kontext)
    assert ergebnis["dateien"] == ["vertrag-bert-beispiel.docx"]
    assert namen(kontext, "ad") == ["vertrag-bert-beispiel.docx"]
    assert namen(kontext, "al") == []


def test_pdf_geht_ueber_den_google_ordner_ohne_konverter(kontext):
    ergebnis = erstelle_vertrag({**basis(), "format": "pdf"}, kontext)
    assert ergebnis["dateien"] == []
    assert ergebnis["pdf_auftrag"] == "vertrag-bert-beispiel.docx"
    assert namen(kontext, "pe") == ["vertrag-bert-beispiel.docx"]
    assert namen(kontext, "al") == namen(kontext, "ad") == namen(kontext, "pa") == []
    assert "PDF wird in Google Drive erzeugt" in ergebnis["hinweis"]
    assert str(kontext["ordner"]["pa"]) in ergebnis["hinweis"]
    assert "nach wenigen Minuten" in ergebnis["hinweis"]
    inhalt = absaetze(kontext["ordner"]["pe"] / "vertrag-bert-beispiel.docx")
    assert inhalt[1] == "Mieter: Bert Beispiel, Beginn 01.01.2026"


def test_docx_und_pdf_schreibt_beides(kontext):
    form = {**basis(), "format": "docx+pdf", "ziel": "drive"}
    ergebnis = erstelle_vertrag(form, kontext)
    assert ergebnis["dateien"] == ["vertrag-bert-beispiel.docx"]
    assert ergebnis["pdf_auftrag"] == "vertrag-bert-beispiel.docx"
    assert namen(kontext, "ad") == ["vertrag-bert-beispiel.docx"]
    assert namen(kontext, "pe") == ["vertrag-bert-beispiel.docx"]
    assert "Google Drive" in ergebnis["hinweis"]
    assert namen(kontext, "al") == []


def test_vorhandene_dateien_werden_nie_ueberschrieben(kontext):
    erstelle_vertrag(basis(), kontext)
    zweites = erstelle_vertrag(basis(), kontext)
    assert zweites["dateien"] == ["vertrag-bert-beispiel-2.docx"]
    erstelle_vertrag({**basis(), "format": "pdf"}, kontext)
    zweites = erstelle_vertrag({**basis(), "format": "pdf"}, kontext)
    assert zweites["pdf_auftrag"] == "vertrag-bert-beispiel-2.docx"
    assert namen(kontext, "pe") == ["vertrag-bert-beispiel-2.docx", "vertrag-bert-beispiel.docx"]


@pytest.mark.parametrize(
    ("aenderung", "nennt"),
    [
        ({"objekt_id": "gibt-es-nicht"}, "objekt_id"),
        ({"vorlage": "lokal:../vertrag.docx"}, "vorlage"),
        ({"vorlage": "vertrag.docx"}, "vorlage"),
        ({"vorlage": "cloud:vertrag.docx"}, "vorlage"),
        ({"format": "odt"}, "format"),
        ({"ziel": "cloud"}, "ziel"),
        ({"anfrage": "Miete netto: viel"}, "miete_netto"),
        ({"mietbeginn": "2026-02-30"}, "mietbeginn"),
        ({"mieter_name": ""}, "mieter_name"),
    ],
)
def test_fehler_nennen_das_feld_und_schreiben_nichts(kontext, aenderung, nennt):
    with pytest.raises(ValueError, match=nennt):
        erstelle_vertrag({**basis(), **aenderung}, kontext)
    assert leer(kontext)


def test_fehlende_einstellungen(kontext):
    einst = kontext["einstellungen"]
    ohne = {**kontext, "einstellungen": {"objekte_datei": einst["objekte_datei"]}}
    with pytest.raises(ValueError, match="vorlagen_lokal"):
        erstelle_vertrag(basis(), ohne)
    ohne_pdf = {k: v for k, v in einst.items() if k != "pdf_eingang"}
    for fmt in ("pdf", "docx+pdf"):
        with pytest.raises(ValueError, match="pdf_eingang"):
            erstelle_vertrag({**basis(), "format": fmt}, {**kontext, "einstellungen": ohne_pdf})
    assert leer(kontext)
    assert erstelle_vertrag(basis(), {**kontext, "einstellungen": ohne_pdf})["dateien"]


def test_ohne_objekt_genuegen_formularfelder(kontext):
    form = {
        "vorlage": "lokal:vertrag.docx",
        "mieter_name": "Cora Test",
        "objekt": "Haus 9",
        "mietbeginn": "01.03.2026",
        "miete_netto": "900",
        "nebenkosten": "100",
        "kaution": "2700",
    }
    ergebnis = erstelle_vertrag(form, kontext)
    assert ergebnis["dateien"] == ["vertrag-cora-test.docx"]
    text = absaetze(kontext["ordner"]["al"] / "vertrag-cora-test.docx")
    assert text[0] == "Mietvertrag fuer Haus 9"
    with pytest.raises(ValueError, match="kaution"):
        erstelle_vertrag({**form, "kaution": ""}, kontext)


def protokoll_form():
    return {
        "objekt_id": "weg-1",
        "vorlage": "lokal:uebergabe.docx",
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


def test_protokoll_mit_objekt_aus_dem_dropdown(kontext):
    ergebnis = erstelle_protokoll(protokoll_form(), kontext)
    assert ergebnis == {
        "dateien": ["uebergabeprotokoll-anna-muster.docx"],
        "pdf_auftrag": None,
        "hinweis": "",
    }
    assert absaetze(kontext["ordner"]["al"] / "uebergabeprotokoll-anna-muster.docx") == [
        "Einzug: Anna Muster in Musterweg 1, 8000 Zuerich am 01.02.2026",
        "Strom 1234.5, Wasser 56, Schluessel 3",
        "Bemerkungen: keine",
    ]


def test_protokoll_pdf_und_fehler(kontext):
    ergebnis = erstelle_protokoll({**protokoll_form(), "format": "pdf"}, kontext)
    assert ergebnis["dateien"] == []
    assert ergebnis["pdf_auftrag"] == "uebergabeprotokoll-anna-muster.docx"
    assert namen(kontext, "pe") == ["uebergabeprotokoll-anna-muster.docx"]
    assert "Google Drive" in ergebnis["hinweis"]
    for aenderung, nennt in [
        ({"art": "Besichtigung"}, "art"),
        ({"zaehler_strom": "-1"}, "zaehler_strom"),
        ({"objekt_id": "x"}, "objekt_id"),
        ({"bemerkungen": "{{kaution}}"}, "bemerkungen"),
        ({"vorlage": "lokal:fehlt.docx"}, "vorlage"),
    ]:
        with pytest.raises(ValueError, match=nennt):
            erstelle_protokoll({**protokoll_form(), **aenderung}, kontext)
    assert namen(kontext, "al") == namen(kontext, "ad") == []
