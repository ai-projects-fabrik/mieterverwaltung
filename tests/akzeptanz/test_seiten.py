"""Akzeptanztest (spec-first) fuer projekt.seiten (Ziel `mv-seiten`)."""

import importlib.util
from html.parser import HTMLParser

import pytest

if importlib.util.find_spec("projekt.seiten") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.felder import FELDER  # noqa: E402
from projekt.seiten import (  # noqa: E402
    TABS,
    ergebnis,
    formular_mietvertrag,
    formular_protokoll,
    formular_settings,
    rahmen,
)

OBJEKTE = [
    {"id": "a", "bezeichnung": "Haus <A>", "miete_netto": "1'000.00"},
    {"id": "b", "bezeichnung": "Haus B"},
]
VORLAGEN = {"lokal": ["vertrag.docx"], "drive": ["drive & co.docx"]}
VERTRAG_FELDER = ["mieter_name", "objekt", "mietbeginn", "miete_netto", "nebenkosten", "kaution"]
if "wohnraumnutzer_name" in FELDER:  # Ziel `mv-wohnraumnutzer`
    VERTRAG_FELDER.insert(1, "wohnraumnutzer_name")
if "mietende" in FELDER:  # Ziel `mv-feld-mietende`
    VERTRAG_FELDER.insert(VERTRAG_FELDER.index("mietbeginn") + 1, "mietende")
PROTOKOLL_FELDER = [
    "mieter_name",
    "objekt",
    "uebergabedatum",
    "zaehler_strom",
    "zaehler_wasser",
    "schluessel_anzahl",
]
EINSTELLUNGEN = {"objekte_datei": "C:/M/objekte.json", "ausgabe_lokal": "C:/M/<aus>"}


class Seite(HTMLParser):
    """Sammelt die Teile einer Seite, die der Test pruefen will."""

    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.felder = {}
        self.selects = {}
        self.gruppen = {}
        self.texte = []
        self._select = None
        self._option = None
        self._gruppe = None
        self._textarea = None
        self.formulare = []
        self.links = []
        self.aktuell = []
        self.knoepfe = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if tag == "form":
            self.formulare.append(a)
        elif tag == "a":
            self.links.append(a)
            if a.get("aria-current") == "page":
                self.aktuell.append(a.get("href"))
        elif tag == "input":
            self.felder[a.get("name")] = a.get("value", "")
        elif tag == "textarea":
            self._textarea = a.get("name")
            self.felder[self._textarea] = ""
        elif tag == "button":
            self.knoepfe.append(a)
        elif tag == "select":
            self._select = a.get("name")
            self.selects[self._select] = []
        elif tag == "optgroup":
            self._gruppe = a.get("label")
            self.gruppen[self._gruppe] = []
        elif tag == "option":
            self._option = [a.get("value", ""), "", "selected" in a]
            self.selects[self._select].append(self._option)
            if self._gruppe:
                self.gruppen[self._gruppe].append(self._option)

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = self._gruppe = None
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


def werte(seite, name):
    return [(v, t) for v, t, _ in seite.selects[name]]


def test_tabs_und_rahmen():
    assert TABS == (
        ("mietvertrag", "Mietvertrag"),
        ("protokoll", "Übergabeprotokoll"),
        ("settings", "Settings"),
    )
    html = rahmen("protokoll", "<p id='inhalt'>Hallo</p>")
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'charset="utf-8"' in html.lower()
    assert "<p id='inhalt'>Hallo</p>" in html
    seite = Seite(html)
    assert [a["href"] for a in seite.links] == ["/mietvertrag", "/protokoll", "/settings"]
    assert seite.aktuell == ["/protokoll"]
    assert "Übergabeprotokoll" in "".join(seite.texte)
    with pytest.raises(ValueError, match="aktiv"):
        rahmen("gibt-es-nicht", "")


@pytest.mark.parametrize(
    ("funktion", "aktion", "felder"),
    [
        (formular_mietvertrag, "/mietvertrag", VERTRAG_FELDER),
        (formular_protokoll, "/protokoll", PROTOKOLL_FELDER),
    ],
)
def test_formulare_tabellenform_und_dropdowns(funktion, aktion, felder):
    seite = Seite(funktion(OBJEKTE, VORLAGEN))
    assert seite.formulare == [{"method": "post", "action": aktion}]
    assert "table" in seite.tags
    assert seite.tags.count("tr") >= len(felder) + 4
    assert "th" in seite.tags
    for name in felder:
        assert name in seite.felder
    assert werte(seite, "objekt_id") == [("", ""), ("a", "Haus <A>"), ("b", "Haus B")]
    assert werte(seite, "format") == [("docx", "docx"), ("pdf", "pdf"), ("docx+pdf", "docx+pdf")]
    assert seite.selects["format"][0][2] is True
    assert [v for v, _ in werte(seite, "ziel")] == ["lokal", "drive"]
    assert [v for v, _ in werte(seite, "vorlage")] == [
        "lokal:vertrag.docx",
        "drive:drive & co.docx",
    ]
    assert [t for _, t, _ in seite.gruppen["Festplatte"]] == ["vertrag.docx"]
    assert [t for _, t, _ in seite.gruppen["Google Drive"]] == ["drive & co.docx"]
    assert any(k.get("type", "submit") == "submit" for k in seite.knoepfe)


def test_mietvertrag_hat_anfragefeld_protokoll_hat_art():
    assert "anfrage" in Seite(formular_mietvertrag([], {"lokal": [], "drive": []})).felder
    seite = Seite(formular_protokoll([], {"lokal": [], "drive": []}))
    assert werte(seite, "art") == [("Einzug", "Einzug"), ("Auszug", "Auszug")]
    assert "bemerkungen" in seite.felder
    assert werte(seite, "objekt_id") == [("", "")]
    assert seite.selects["vorlage"] == []


def test_werte_und_meldung_sind_maskiert_und_vorbelegt():
    html = formular_mietvertrag(
        OBJEKTE,
        VORLAGEN,
        werte={"mieter_name": 'Anna "<b>"', "anfrage": "Kaution: <i>1</i>", "format": "pdf"},
        meldung="Fehler: <script>x</script>",
    )
    assert "<b>" not in html
    assert "<script>" not in html
    assert "<i>" not in html
    assert "<A>" not in html
    seite = Seite(html)
    assert seite.felder["mieter_name"] == 'Anna "<b>"'
    assert seite.felder["anfrage"] == "Kaution: <i>1</i>"
    assert "Fehler: <script>x</script>" in "".join(seite.texte)
    assert [v for v, _, gewaehlt in seite.selects["format"] if gewaehlt] == ["pdf"]


def test_settings_seite():
    seite = Seite(formular_settings(EINSTELLUNGEN, OBJEKTE, meldung="Gespeichert"))
    assert seite.formulare == [{"method": "post", "action": "/settings"}]
    assert "table" in seite.tags
    assert seite.felder["objekte_datei"] == "C:/M/objekte.json"
    assert seite.felder["ausgabe_lokal"] == "C:/M/<aus>"
    for name in ("vorlagen_lokal", "vorlagen_drive", "ausgabe_drive", "drive_wurzel"):
        assert seite.felder[name] == ""
    for name in ("neu_id", "neu_bezeichnung", "neu_miete_netto", "neu_nebenkosten", "neu_kaution"):
        assert name in seite.felder
    entfernen = [k for k in seite.knoepfe if k.get("name") == "entfernen"]
    assert [k["value"] for k in entfernen] == ["a", "b"]
    text = "".join(seite.texte)
    assert "Haus <A>" in text
    assert "Gespeichert" in text
    assert "<A>" not in formular_settings(EINSTELLUNGEN, OBJEKTE)
    assert "<aus>" not in formular_settings(EINSTELLUNGEN, OBJEKTE)


def test_ergebnisseite():
    html = ergebnis("Vertrag <fertig>", "mieter_name: A -> <B>", ["v-1.docx", "v <2>.pdf"])
    assert "<B>" not in html
    assert "<fertig>" not in html
    seite = Seite(html)
    text = "".join(seite.texte)
    assert "Vertrag <fertig>" in text
    assert "mieter_name: A -> <B>" in text
    assert seite.tags.count("li") == 2
    assert "v <2>.pdf" in text
    assert "pre" in seite.tags
    assert "li" not in Seite(ergebnis("x", "y", [])).tags


def test_ergebnisseite_mit_hinweis():
    html = ergebnis("T", "b", [], hinweis="PDF wird in Google Drive erzeugt <bald>")
    assert "<bald>" not in html
    seite = Seite(html)
    assert "PDF wird in Google Drive erzeugt <bald>" in "".join(seite.texte)
    assert "Google Drive" not in "".join(Seite(ergebnis("T", "b", [])).texte)
    assert "Google Drive" not in "".join(Seite(ergebnis("T", "b", [], hinweis="")).texte)
