"""Akzeptanztest (spec-first) fuer projekt.seiten_einfach (Ziel `mv-seiten-einfach`)."""

import importlib.util
from html.parser import HTMLParser

import pytest

if importlib.util.find_spec("projekt.seiten_einfach") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.seiten_einfach import (  # noqa: E402
    TABS_EINFACH,
    formular_objekttabelle,
    formular_ordner,
    formular_uebergabe,
    formular_vertrag,
    rahmen_einfach,
)
from projekt.felder import FELDER  # noqa: E402

WOHNRAUMNUTZER = "wohnraumnutzer_name" in FELDER  # Ziel `mv-wohnraumnutzer`
MIETENDE = "mietende" in FELDER  # Ziel `mv-feld-mietende`

OBJEKTE = [
    {"id": "a", "bezeichnung": "Haus <A>", "miete_netto": "1'000.00"},
    {"id": "b", "bezeichnung": "Haus B"},
]
VORLAGEN = {"lokal": ["vertrag.docx"], "drive": ["drive & co.docx"]}
ROHE_NAMEN = (
    "objekte_datei",
    "vorlagen_lokal",
    "vorlagen_drive",
    "ausgabe_lokal",
    "ausgabe_drive",
    "drive_wurzel",
    "neu_id",
    "objekt_id",
    "miete_netto",
    "nebenkosten",
    "mieter_name",
    "zaehler_strom",
)


class Sammler(HTMLParser):
    def __init__(self):
        super().__init__()
        self.felder = []
        self.optionen = {}
        self.text = []
        self.formulare = []
        self._select = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.formulare.append((a.get("method"), a.get("action")))
        if tag in ("input", "select", "textarea") and a.get("name"):
            self.felder.append((tag, a["name"], a))
        if tag == "select":
            self._select = a.get("name")
            self.optionen[self._select] = []
        if tag == "option" and self._select:
            self.optionen[self._select].append((a.get("value"), "selected" in a))

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())


def lies(html):
    s = Sammler()
    s.feed(html)
    s.close()
    return s


def namen(s):
    return [n for _, n, _ in s.felder]


def test_tabs_und_rahmen():
    assert [t for t, _ in TABS_EINFACH] == ["mietvertrag", "protokoll", "objekte", "settings"]
    seite = rahmen_einfach("objekte", "<p>x</p>")
    assert seite.startswith("<!doctype html>") and "<p>x</p>" in seite
    assert seite.count('aria-current="page"') == 1
    assert 'href="/objekte" aria-current="page"' in seite
    for tab, _ in TABS_EINFACH:
        assert f'href="/{tab}"' in seite
    with pytest.raises(ValueError, match="aktiv"):
        rahmen_einfach("nix", "")


def test_ordnerformular_hat_genau_zwei_felder_mit_deutschen_namen():
    html = formular_ordner('G:\\My "Drive"', "C:\\Mietverwaltung", "Gespeichert <b>")
    s = lies(html)
    assert namen(s) == ["drive_ordner", "lokaler_ordner"]
    assert s.formulare == [("post", "/settings")]
    sichtbar = " ".join(s.text)
    assert "Google-Drive-Ordner" in sichtbar and "Lokaler Ordner" in sichtbar
    assert not any(n in sichtbar for n in ROHE_NAMEN)
    assert 'value="G:\\My &quot;Drive&quot;"' in html
    assert "Gespeichert &lt;b&gt;" in html and "<b>" not in html


def test_objekttabelle_zeigt_objekte_und_zwei_leere_zeilen():
    s = lies(
        formular_objekttabelle([{"id": "a", "bezeichnung": "Haus <A>", "kaution": "3'000.00"}])
    )
    sichtbar = " ".join(s.text)
    for kopf in ("Bezeichnung", "Miete netto (CHF)", "Nebenkosten (CHF)", "Kaution (CHF)"):
        assert kopf in sichtbar
    assert not any(n in sichtbar for n in ROHE_NAMEN)
    assert s.formulare == [("post", "/objekte")]
    for nr in (0, 1, 2):
        for feld in ("id", "bezeichnung", "miete_netto", "nebenkosten", "kaution"):
            assert f"zeile_{nr}_{feld}" in namen(s)
    assert "zeile_3_bezeichnung" not in namen(s)
    werte = {n: a.get("value") for _, n, a in s.felder}
    assert werte["zeile_0_id"] == "a" and werte["zeile_0_bezeichnung"] == "Haus <A>"
    assert werte["zeile_0_kaution"] == "3'000.00" and werte["zeile_1_bezeichnung"] == ""
    assert "neu_id" not in namen(s)


def test_objekttabelle_maskiert_und_zeigt_meldung():
    html = formular_objekttabelle([{"bezeichnung": '"><script>x</script>'}], "Zeile 1: <fehler>")
    assert "<script>" not in html and "&lt;fehler&gt;" in html


def test_vertragsformular_fragt_nur_das_noetige():
    s = lies(formular_vertrag(OBJEKTE, VORLAGEN))
    erwartet = [
        "objekt_id",
        "vorlage",
        "mieter_name",
        "wohnraumnutzer_name",
        "mietbeginn",
        "mietende",
        "anfrage",
        "format",
        "ziel",
    ]
    if not WOHNRAUMNUTZER:
        erwartet.remove("wohnraumnutzer_name")
    if not MIETENDE:
        erwartet.remove("mietende")
    assert namen(s) == erwartet
    assert s.formulare == [("post", "/mietvertrag")]
    for gestrichen in ("miete_netto", "nebenkosten", "kaution", "objekt"):
        assert gestrichen not in namen(s)
    assert [w for w, _ in s.optionen["objekt_id"]] == ["a", "b"]
    assert [w for w, _ in s.optionen["vorlage"]] == ["lokal:vertrag.docx", "drive:drive & co.docx"]
    assert [w for w, _ in s.optionen["format"]] == ["docx+pdf", "docx", "pdf"]
    assert [w for w, _ in s.optionen["ziel"]] == ["drive", "lokal"]
    sichtbar = " ".join(s.text)
    for label in ("Objekt", "Vorlage", "Mietbeginn", "Dateiformat", "Speichern in", "Google Drive"):
        assert label in sichtbar
    assert not any(n in sichtbar for n in ROHE_NAMEN)


def test_vertragsformular_belegt_vor_und_faellt_bei_ungueltigem_auf_standard_zurueck():
    werte = {
        "objekt_id": "b",
        "vorlage": "drive:drive & co.docx",
        "format": "pdf",
        "ziel": "lokal",
        "mieter_name": "Erika <M>",
        "mietbeginn": "1.2.2027",
        "anfrage": "kaution: 3000",
    }
    html = formular_vertrag(OBJEKTE, VORLAGEN, werte)
    s = lies(html)
    gewaehlt = {n: [w for w, sel in o if sel] for n, o in s.optionen.items()}
    assert gewaehlt == {
        "objekt_id": ["b"],
        "vorlage": ["drive:drive & co.docx"],
        "format": ["pdf"],
        "ziel": ["lokal"],
    }
    assert "Erika &lt;M&gt;" in html and "Erika <M>" not in html
    assert "kaution: 3000" in html
    kaputt = lies(formular_vertrag(OBJEKTE, VORLAGEN, {"format": "xls", "ziel": "x"}))
    gewaehlt = {n: [w for w, sel in o if sel] for n, o in kaputt.optionen.items()}
    assert gewaehlt["format"] == ["docx+pdf"] and gewaehlt["ziel"] == ["drive"]


def test_ohne_objekte_gibt_es_nur_einen_hinweis_und_ohne_vorlagen_leere_gruppen():
    s = lies(formular_vertrag([], VORLAGEN, None, "Achtung <1>"))
    assert namen(s) == [] and "Objekte" in " ".join(s.text)
    assert "Achtung &lt;1&gt;" in formular_vertrag([], VORLAGEN, None, "Achtung <1>")
    s = lies(formular_vertrag(OBJEKTE, {}))
    assert s.optionen["vorlage"] == []


def test_protokollformular():
    html = formular_uebergabe(OBJEKTE, VORLAGEN, {"art": "Auszug", "bemerkungen": "<i>"})
    s = lies(html)
    assert namen(s) == [
        "objekt_id",
        "vorlage",
        "mieter_name",
        "uebergabedatum",
        "art",
        "zaehler_strom",
        "zaehler_wasser",
        "schluessel_anzahl",
        "bemerkungen",
        "format",
        "ziel",
    ]
    assert s.formulare == [("post", "/protokoll")]
    assert [w for w, sel in s.optionen["art"] if sel] == ["Auszug"]
    assert "objekt" not in namen(s)
    assert "&lt;i&gt;" in html
    sichtbar = " ".join(s.text)
    for label in ("Übergabedatum", "Zählerstand Strom", "Anzahl Schlüssel", "Bemerkungen"):
        assert label in sichtbar
    assert not any(n in sichtbar for n in ROHE_NAMEN)
    standard = lies(formular_uebergabe(OBJEKTE, VORLAGEN, {"art": "x"}))
    assert [w for w, sel in standard.optionen["art"] if sel] == ["Einzug"]


@pytest.mark.skipif(not WOHNRAUMNUTZER, reason="Feld wohnraumnutzer_name noch nicht umgesetzt")
def test_wohnraumnutzer_nur_im_vertragsformular_mit_beschriftung_und_vorbelegung():
    html = formular_vertrag(OBJEKTE, VORLAGEN, {"wohnraumnutzer_name": "Karl <K>"})
    s = lies(html)
    assert "Name des Wohnraumnutzers" in " ".join(s.text)
    assert "wohnraumnutzer_name" not in " ".join(s.text)
    assert "Karl &lt;K&gt;" in html and "Karl <K>" not in html
    assert "wohnraumnutzer_name" not in namen(lies(formular_uebergabe(OBJEKTE, VORLAGEN)))


@pytest.mark.skipif(not MIETENDE, reason="Feld mietende noch nicht umgesetzt")
def test_mietende_nur_im_vertragsformular_mit_beschriftung_und_vorbelegung():
    html = formular_vertrag(OBJEKTE, VORLAGEN, {"mietende": "31.12.2027"})
    s = lies(html)
    assert "Mietende" in " ".join(s.text)
    assert "mietende" not in " ".join(s.text)
    assert "31.12.2027" in html
    assert "mietende" not in namen(lies(formular_uebergabe(OBJEKTE, VORLAGEN)))
