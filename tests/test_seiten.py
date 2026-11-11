"""Tests fuer die reine HTML-Erzeugung in projekt.seiten."""

from html.parser import HTMLParser

import pytest

from projekt.seiten import (
    TABS,
    ergebnis,
    formular_mietvertrag,
    formular_protokoll,
    formular_settings,
    rahmen,
)


class Seite(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.felder = {}
        self.selects = {}
        self.gruppen = {}
        self.knoepfe = []
        self.links = []
        self.aktuell = []
        self.texte = []
        self._select = None
        self._gruppe = None
        self._option = None
        self._textarea = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        werte = dict(attrs)
        self.tags.append(tag)
        if tag == "a":
            self.links.append(werte)
            if werte.get("aria-current") == "page":
                self.aktuell.append(werte.get("href"))
        elif tag == "input":
            self.felder[werte.get("name")] = werte.get("value", "")
        elif tag == "textarea":
            self._textarea = werte.get("name")
            self.felder[self._textarea] = ""
        elif tag == "select":
            self._select = werte.get("name")
            self.selects[self._select] = []
        elif tag == "optgroup":
            self._gruppe = werte.get("label")
            self.gruppen[self._gruppe] = []
        elif tag == "option":
            self._option = [werte.get("value", ""), "", "selected" in werte]
            self.selects[self._select].append(self._option)
            if self._gruppe:
                self.gruppen[self._gruppe].append(self._option)
        elif tag == "button":
            self.knoepfe.append(werte)

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None
            self._gruppe = None
        elif tag == "optgroup":
            self._gruppe = None
        elif tag == "option":
            self._option = None
        elif tag == "textarea":
            self._textarea = None

    def handle_data(self, data):
        self.texte.append(data)
        if self._option is not None:
            self._option[1] += data
        if self._textarea:
            self.felder[self._textarea] += data


OBJEKTE = [
    {"id": "a", "bezeichnung": "Haus <A>"},
    {"id": "b", "bezeichnung": "Haus B"},
]
VORLAGEN = {"lokal": ["vertrag.docx"], "drive": ["drive & co.docx"]}


def test_tabs_sind_fest_und_rahmen_markiert_den_aktiven_tab():
    assert TABS == (
        ("mietvertrag", "Mietvertrag"),
        ("protokoll", "Übergabeprotokoll"),
        ("settings", "Settings"),
    )
    html = rahmen("mietvertrag", "<p id='roh'>{{unmaskiert}}</p>")
    seite = Seite(html)
    assert [link["href"] for link in seite.links] == [
        "/mietvertrag",
        "/protokoll",
        "/settings",
    ]
    assert seite.aktuell == ["/mietvertrag"]
    assert "<p id='roh'>{{unmaskiert}}</p>" in html


@pytest.mark.parametrize("aktiv", ["", "unbekannt", None])
def test_rahmen_lehnt_unbekannten_aktiven_tab_ab(aktiv):
    with pytest.raises(ValueError, match="aktiv"):
        rahmen(aktiv, "")


def test_mietvertrag_maskiert_werte_und_waehlt_vor():
    html = formular_mietvertrag(
        OBJEKTE,
        VORLAGEN,
        werte={
            "objekt_id": "b",
            "vorlage": "drive:drive & co.docx",
            "format": "pdf",
            "ziel": "drive",
            "mieter_name": 'Anna "<b>"',
            "anfrage": "Kaution: <i>1</i>",
        },
        meldung="Fehler: <script>x</script>",
    )
    assert "<b>" not in html
    assert "<script>" not in html
    assert "<i>" not in html
    assert "<A>" not in html
    seite = Seite(html)
    assert seite.felder["mieter_name"] == 'Anna "<b>"'
    assert seite.felder["anfrage"] == "Kaution: <i>1</i>"
    assert [wert for wert, _, gewaehlt in seite.selects["format"] if gewaehlt] == ["pdf"]
    assert [wert for wert, _, gewaehlt in seite.selects["ziel"] if gewaehlt] == ["drive"]
    assert [wert for wert, _, gewaehlt in seite.selects["objekt_id"] if gewaehlt] == ["b"]
    assert [wert for wert, _, gewaehlt in seite.selects["vorlage"] if gewaehlt] == [
        "drive:drive & co.docx"
    ]


def test_mietvertrag_hat_alle_felder_und_standardwerte():
    seite = Seite(formular_mietvertrag([], {"lokal": [], "drive": []}))
    assert {"mieter_name", "objekt", "mietbeginn", "miete_netto", "nebenkosten", "kaution"} <= set(
        seite.felder
    )
    assert "anfrage" in seite.felder
    assert [wert for wert, _, gewaehlt in seite.selects["format"] if gewaehlt] == ["docx"]
    assert [wert for wert, _, gewaehlt in seite.selects["ziel"] if gewaehlt] == ["lokal"]
    assert seite.selects["vorlage"] == []


def test_protokoll_hat_art_bemerkungen_und_alle_werte():
    seite = Seite(
        formular_protokoll(
            OBJEKTE,
            VORLAGEN,
            werte={"art": "Auszug", "bemerkungen": "Kratzer <im> Flur", "objekt_id": "a"},
        )
    )
    assert [wert for wert, _, _ in seite.selects["art"]] == ["Einzug", "Auszug"]
    assert [wert for wert, _, gewaehlt in seite.selects["art"] if gewaehlt] == ["Auszug"]
    assert seite.felder["bemerkungen"] == "Kratzer <im> Flur"
    assert "anfrage" not in seite.felder
    for feld in (
        "mieter_name",
        "objekt",
        "uebergabedatum",
        "zaehler_strom",
        "zaehler_wasser",
        "schluessel_anzahl",
    ):
        assert feld in seite.felder


def test_ungueltige_auswahlwerte_fallen_auf_standards_zurueck():
    seite = Seite(
        formular_mietvertrag(
            OBJEKTE,
            VORLAGEN,
            werte={"format": "rtf", "ziel": "sonstwo", "art": "Besichtigung"},
        )
    )
    assert [wert for wert, _, gewaehlt in seite.selects["format"] if gewaehlt] == ["docx"]
    assert [wert for wert, _, gewaehlt in seite.selects["ziel"] if gewaehlt] == ["lokal"]
    protokoll = Seite(formular_protokoll(OBJEKTE, VORLAGEN, werte={"art": "Besichtigung"}))
    assert [wert for wert, _, gewaehlt in protokoll.selects["art"] if gewaehlt] == ["Einzug"]


def test_settings_maskiert_und_zeigt_objektaktionen():
    html = formular_settings(
        {"objekte_datei": "C:/M/<objekte>.json", "ausgabe_lokal": "C:/M/&aus"},
        OBJEKTE,
        meldung="Gespeichert <ok>",
    )
    assert "<objekte>" not in html
    assert "&aus" not in html
    assert "<ok>" not in html
    seite = Seite(html)
    assert seite.felder["objekte_datei"] == "C:/M/<objekte>.json"
    assert seite.felder["ausgabe_lokal"] == "C:/M/&aus"
    for feld in (
        "vorlagen_lokal",
        "vorlagen_drive",
        "ausgabe_drive",
        "drive_wurzel",
        "neu_id",
        "neu_bezeichnung",
        "neu_miete_netto",
        "neu_nebenkosten",
        "neu_kaution",
    ):
        assert seite.felder[feld] == ""
    assert [knopf["value"] for knopf in seite.knoepfe if knopf.get("name") == "entfernen"] == [
        "a",
        "b",
    ]
    assert "Gespeichert <ok>" in "".join(seite.texte)


def test_ergebnis_maskiert_und_listet_nur_vorhandene_dateien():
    html = ergebnis("Vertrag <fertig>", "alt -> <neu>", ["a.docx", "b <2>.pdf"])
    seite = Seite(html)
    assert "<fertig>" not in html
    assert "<neu>" not in html
    assert seite.tags.count("li") == 2
    assert "b <2>.pdf" in "".join(seite.texte)
    assert "pre" in seite.tags

    leer = Seite(ergebnis("Titel", "Text", []))
    assert "li" not in leer.tags
    assert "ul" not in leer.tags
    assert "hinweis" not in "".join(leer.texte)


def test_ergebnis_hinweis_ist_optional_und_maskiert():
    ohne = ergebnis("T", "b", [])
    assert "Google Drive" not in ohne
    with_hinweis = ergebnis("T", "b", [], hinweis="PDF <bald> in Google Drive")
    assert "<bald>" not in with_hinweis
    assert "PDF <bald> in Google Drive" in "".join(Seite(with_hinweis).texte)


def test_ergebnis_zeigt_werte_mit_anzeigename_und_quelle_maskiert():
    werte = [
        {"feld": "mieter_name", "wert": "Anna <Muster>", "herkunft": "formular"},
        {"feld": "miete_netto", "wert": "1'800.00", "herkunft": "objekt"},
        {"feld": "kaution", "wert": "4'000.00", "herkunft": "anfrage"},
        {"feld": "unbekannt_x", "wert": "7 & 8", "herkunft": "formular"},
    ]
    html = ergebnis("Titel", "bericht", ["a.docx"], werte=werte)
    assert '<ul class="werte">' in html
    assert "<Muster>" not in html
    assert "7 & 8" not in html
    seite = Seite(html)
    assert [zeile for zeile in seite.texte if "(aus " in zeile] == [
        "Name des Mieters: Anna <Muster> (aus Formular)",
        "Miete: 1'800.00 (aus Objekt)",
        "Kaution: 4'000.00 (aus Änderungen)",
        "unbekannt_x: 7 & 8 (aus Formular)",
    ]
    assert seite.tags.count("li") == 5


def test_ergebnis_zeigt_deutsche_protokollnamen():
    werte = [
        {"feld": "uebergabedatum", "wert": "01.02.2026", "herkunft": "formular"},
        {"feld": "zaehler_strom", "wert": "1234.5", "herkunft": "formular"},
        {"feld": "schluessel_anzahl", "wert": "3", "herkunft": "formular"},
        {"feld": "unbekannt_x", "wert": "7", "herkunft": "objekt"},
    ]
    texte = Seite(ergebnis("T", "", [], werte=werte)).texte
    assert [zeile for zeile in texte if "(aus " in zeile] == [
        "Übergabedatum: 01.02.2026 (aus Formular)",
        "Zählerstand Strom: 1234.5 (aus Formular)",
        "Anzahl Schlüssel: 3 (aus Formular)",
        "unbekannt_x: 7 (aus Objekt)",
    ]


def test_ergebnis_laesst_leeren_bericht_nur_mit_werten_weg():
    ohne_bericht = Seite(ergebnis("T", "", [], werte=[]))
    assert "pre" not in ohne_bericht.tags
    assert "li" not in ohne_bericht.tags

    mit_bericht = Seite(ergebnis("T", "x", [], werte=[]))
    assert "pre" in mit_bericht.tags

    ohne_werte = Seite(ergebnis("T", "", []))
    assert "pre" in ohne_werte.tags
