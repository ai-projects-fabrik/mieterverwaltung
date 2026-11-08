"""Tests fuer Routing und Formularverarbeitung in projekt.webapp."""

import html
import io
import json
import zipfile
from urllib.parse import urlencode

import pytest

from projekt.webapp import antwort

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
VERTRAG = [
    "Mietvertrag fuer {{objekt}}",
    "Mieter: {{mieter_name}}, Beginn {{mietbeginn}}",
    "Netto {{miete_netto}} plus NK {{nebenkosten}}, Kaution {{kaution}}",
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


@pytest.fixture
def umgebung(tmp_path):
    for name in ("vl", "vd", "al", "ad"):
        (tmp_path / name).mkdir()
    for name in ("MV-zu-pdf", "MV-pdf", "MV-erledigt"):
        (tmp_path / "drive" / name).mkdir(parents=True)
    (tmp_path / "vl" / "vertrag.docx").write_bytes(docx_bytes(VERTRAG))
    (tmp_path / "vd" / "drive.docx").write_bytes(docx_bytes(VERTRAG))
    objekte = [
        {
            "id": "weg-1",
            "bezeichnung": "Musterweg 1, 8000 Zuerich",
            "miete_netto": "1'200.00",
            "nebenkosten": "200.00",
            "kaution": "3'600.00",
        }
    ]
    objekte_datei = tmp_path / "objekte.json"
    objekte_datei.write_text(json.dumps(objekte), encoding="utf-8")
    einstellungen = {
        "objekte_datei": str(objekte_datei),
        "vorlagen_lokal": str(tmp_path / "vl"),
        "vorlagen_drive": str(tmp_path / "vd"),
        "ausgabe_lokal": str(tmp_path / "al"),
        "ausgabe_drive": str(tmp_path / "ad"),
        "drive_wurzel": str(tmp_path / "drive"),
    }
    datei = tmp_path / "einstellungen.json"
    datei.write_text(json.dumps(einstellungen), encoding="utf-8")
    return {"einstellungen_datei": datei, "objekte_datei": objekte_datei}


def post(umgebung, pfad, felder, kopf=None, koerper=None):
    if koerper is None:
        koerper = urlencode(felder).encode("utf-8")
    return antwort("POST", pfad, FORM if kopf is None else kopf, koerper, umgebung)


def vertragsform(**extra):
    return {
        "objekt_id": "weg-1",
        "vorlage": "lokal:vertrag.docx",
        "format": "docx",
        "ziel": "lokal",
        "mieter_name": "Anna Muster",
        "mietbeginn": "2026-01-01",
        **extra,
    }


def dateien(pfad):
    return sorted(eintrag.name for eintrag in pfad.iterdir())


def test_routing_content_type_und_falsche_methoden(umgebung):
    for pfad in ("/", "/?ansicht=1"):
        status, kopf, koerper = antwort("GET", pfad, {}, b"", umgebung)
        assert status == 302
        assert {name.lower(): wert for name, wert in kopf.items()}["location"] == "/mietvertrag"
        assert koerper == b""

    for pfad in ("/mietvertrag", "/protokoll", "/settings"):
        status, kopf, koerper = antwort("GET", pfad, {}, b"", umgebung)
        assert status == 200
        assert kopf["Content-Type"] == "text/html; charset=utf-8"
        assert b"<!doctype html>" in koerper
        assert b"<form" in koerper

    assert antwort("GET", "/gibt-es-nicht", {}, b"", umgebung)[0] == 404
    assert antwort("GET", "/download/abc", {}, b"", umgebung)[0] == 404
    assert post(umgebung, "/", {})[0] == 405
    assert antwort("PUT", "/settings", {}, b"", umgebung)[0] == 405
    assert antwort("DELETE", "/protokoll", {}, b"", umgebung)[0] == 405


def test_formular_nimmt_ersten_wert_und_utf8(umgebung):
    koerper = urlencode(
        [
            ("objekt_id", "weg-1"),
            ("vorlage", "lokal:vertrag.docx"),
            ("format", "docx"),
            ("ziel", "lokal"),
            ("mieter_name", "Jörg Beispiel"),
            ("mieter_name", "Ignoriert"),
            ("mietbeginn", "2026-01-01"),
        ]
    ).encode("utf-8")
    status, _, _ = antwort("POST", "/mietvertrag", FORM, koerper, umgebung)
    assert status == 200
    assert dateien(umgebung["einstellungen_datei"].parent / "al") == ["vertrag-joerg-beispiel.docx"]

    assert post(umgebung, "/mietvertrag", {}, {"Content-Type": "text/plain"})[0] == 400
    assert post(umgebung, "/mietvertrag", {}, koerper=b"mieter_name=\xff")[0] == 400
    assert antwort("POST", "/mietvertrag", FORM, None, umgebung)[0] == 400
    assert antwort("POST", "/mietvertrag", FORM, b"x" * (1024 * 1024 + 1), umgebung)[0] == 413


def test_get_vertraegt_leere_und_ungueltige_einstellungen(tmp_path):
    datei = tmp_path / "einstellungen.json"
    for inhalt in ("", "{kaputt", json.dumps({"vorlagen_lokal": "fehlt"})):
        datei.write_text(inhalt, encoding="utf-8")
        kontext = {"einstellungen_datei": datei}
        for pfad in ("/mietvertrag", "/protokoll", "/settings"):
            status, _, koerper = antwort("GET", pfad, {}, b"", kontext)
            assert status == 200
            assert b"<form" in koerper
        assert datei.read_text(encoding="utf-8") == inhalt


def test_nicht_konfiguriert_erklaert_settings_tab(tmp_path):
    kontext = {"einstellungen_datei": tmp_path / "leer.json"}
    status, _, koerper = post(kontext, "/mietvertrag", vertragsform())
    text = html.unescape(koerper.decode("utf-8"))
    assert status == 400
    assert "Settings" in text
    assert "vorlagen_lokal" in text
    assert "<form" in text


def test_fehler_halten_eingaben_und_maskieren_sie(umgebung, tmp_path):
    felder = vertragsform(anfrage="Kaution: <b>viel</b>", mieter_name="<script>x</script>")
    status, _, koerper = post(umgebung, "/mietvertrag", felder)
    text = koerper.decode("utf-8")
    entschluesselt = html.unescape(text)
    assert status == 400
    assert "kaution" in entschluesselt
    assert "<script>" not in text
    assert "<b>" not in text
    assert dateien(tmp_path / "al") == []


def test_settings_ersetzt_werte_und_entfernt_leere(umgebung, tmp_path):
    status, _, koerper = post(
        umgebung,
        "/settings",
        {"ausgabe_lokal": str(tmp_path / "ad"), "vorlagen_drive": ""},
    )
    assert status == 200
    assert "Gespeichert" in html.unescape(koerper.decode("utf-8"))
    gespeichert = json.loads(umgebung["einstellungen_datei"].read_text(encoding="utf-8"))
    assert gespeichert == {"ausgabe_lokal": str(tmp_path / "ad")}


def test_settings_prueft_neues_objekt_vor_dem_schreiben(umgebung, tmp_path):
    settings_vorher = umgebung["einstellungen_datei"].read_bytes()
    objekte_vorher = umgebung["objekte_datei"].read_bytes()
    basis = {
        "objekte_datei": str(umgebung["objekte_datei"]),
        "ausgabe_lokal": str(tmp_path / "al"),
    }
    for extra, nennt in [
        ({"neu_id": "neu-1"}, "bezeichnung"),
        ({"neu_id": "Ungültig!", "neu_bezeichnung": "X"}, "id"),
        ({"neu_id": "neu-1", "neu_bezeichnung": "X", "neu_kaution": "viel"}, "kaution"),
    ]:
        status, _, koerper = post(umgebung, "/settings", {**basis, **extra})
        assert status == 400
        assert nennt in html.unescape(koerper.decode("utf-8"))
        assert umgebung["einstellungen_datei"].read_bytes() == settings_vorher
        assert umgebung["objekte_datei"].read_bytes() == objekte_vorher


def test_settings_legt_objekt_an_und_ersetzt_gleiche_id(umgebung, tmp_path):
    basis = {
        "objekte_datei": str(umgebung["objekte_datei"]),
        "ausgabe_lokal": str(tmp_path / "al"),
    }
    status, _, _ = post(
        umgebung,
        "/settings",
        {**basis, "neu_id": "weg-1", "neu_bezeichnung": "Neuer Weg", "neu_miete_netto": "990"},
    )
    assert status == 200
    objekte = json.loads(umgebung["objekte_datei"].read_text(encoding="utf-8"))
    assert objekte == [
        {
            "id": "weg-1",
            "bezeichnung": "Neuer Weg",
            "miete_netto": "990.00",
        }
    ]


def test_settings_entfernen_braucht_objekte_datei(umgebung):
    settings_vorher = umgebung["einstellungen_datei"].read_bytes()
    objekte_vorher = umgebung["objekte_datei"].read_bytes()
    status, _, koerper = post(umgebung, "/settings", {"objekte_datei": "", "entfernen": "weg-1"})
    assert status == 400
    assert "objekte_datei" in html.unescape(koerper.decode("utf-8"))
    assert umgebung["einstellungen_datei"].read_bytes() == settings_vorher
    assert umgebung["objekte_datei"].read_bytes() == objekte_vorher


def test_settings_entfernt_objekt(umgebung, tmp_path):
    status, _, _ = post(
        umgebung,
        "/settings",
        {
            "objekte_datei": str(umgebung["objekte_datei"]),
            "ausgabe_lokal": str(tmp_path / "al"),
            "entfernen": "weg-1",
        },
    )
    assert status == 200
    assert json.loads(umgebung["objekte_datei"].read_text(encoding="utf-8")) == []


def test_settings_schreibfehler_rollt_objekte_zurueck(umgebung, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("kein Ordner", encoding="utf-8")
    kontext = {"einstellungen_datei": blocker / "einstellungen.json"}
    objekte_vorher = umgebung["objekte_datei"].read_bytes()

    status, _, koerper = post(
        kontext,
        "/settings",
        {
            "objekte_datei": str(umgebung["objekte_datei"]),
            "ausgabe_lokal": str(tmp_path / "al"),
            "neu_id": "neu-1",
            "neu_bezeichnung": "Neues Objekt",
        },
    )
    assert status == 400
    assert "Ordner" in html.unescape(koerper.decode("utf-8"))
    assert umgebung["objekte_datei"].read_bytes() == objekte_vorher


@pytest.mark.parametrize(
    ("methode", "pfad", "kopf", "koerper", "kontext"),
    [
        (None, "/", {}, b"", None),
        ("GET", None, {}, b"", None),
        ("GET", "/mietvertrag", {}, b"", None),
        ("POST", "/mietvertrag", {}, b"", None),
    ],
)
def test_ungueltige_aufrufe_werden_zu_status_400(methode, pfad, kopf, koerper, kontext, tmp_path):
    if kontext is None:
        kontext = {"einstellungen_datei": tmp_path / "fehlt.json"}
    status, _, koerper = antwort(methode, pfad, kopf, koerper, kontext)
    assert status in (200, 400)
    assert status != 500
