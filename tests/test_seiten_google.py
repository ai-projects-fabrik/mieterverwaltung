"""Tests fuer die HTML-Seiten des Google-Zugriffs ohne Netzwerk oder Dateien."""

from html.parser import HTMLParser

import pytest

from projekt.seiten_google import SEITEN, ZUSTAENDE, formular_auswahl, google_block


class Seite(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.formulare, self.knoepfe, self.text = [], [], [], []
        self._form = None
        self._link = None
        self._knopf = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attribute = dict(attrs)
        if tag == "a":
            self._link = {"href": attribute.get("href"), "text": ""}
            self.links.append(self._link)
        elif tag == "form":
            self._form = {
                "methode": attribute.get("method"),
                "aktion": attribute.get("action"),
                "felder": {},
            }
            self.formulare.append(self._form)
        elif tag == "input" and self._form is not None:
            self._form["felder"][attribute.get("name")] = {
                "typ": attribute.get("type"),
                "wert": attribute.get("value"),
                **attribute,
            }
        elif tag == "button":
            self._knopf = True
            self.knoepfe.append({"text": "", "form": self._form})

    def handle_endtag(self, tag):
        if tag == "a":
            self._link = None
        elif tag == "form":
            self._form = None
        elif tag == "button":
            self._knopf = False

    def handle_data(self, data):
        self.text.append(data)
        if self._link is not None:
            self._link["text"] += data
        if self._knopf:
            self.knoepfe[-1]["text"] += data

    def alles(self):
        return "".join(self.text)


PFAD = [{"id": "root", "name": "Meine Ablage"}, {"id": "F1", "name": "Vertraege <2026>"}]
ORDNER = [{"id": "F2", "name": "Alt & Neu"}]
DATEIEN = [
    {"id": "d1", "name": "Feltenbummler Vertrag", "mime": "m"},
    {"id": "d2", "name": "Rechnung Strom", "mime": "m"},
    {"id": "d3", "name": "August26-Uebergabeprotokoll", "mime": "m"},
]


def test_konstanten_sind_fest():
    assert SEITEN == {"vertrag": "/mietvertrag", "protokoll": "/protokoll"}
    assert ZUSTAENDE == ("keine_datei", "getrennt", "laeuft", "abgebrochen", "verbunden")


@pytest.mark.parametrize("zustand", ["getrennt", "abgebrochen"])
def test_anmeldezustaende_zeigen_nur_das_anmeldeformular(zustand):
    seite = Seite(google_block("protokoll", zustand))
    assert [knopf["text"] for knopf in seite.knoepfe] == ["Bei Google anmelden"]
    form = seite.knoepfe[0]["form"]
    assert (form["methode"], form["aktion"]) == ("post", "/google/anmelden")
    assert form["felder"]["art"]["wert"] == "protokoll"
    assert seite.links == []
    if zustand == "abgebrochen":
        assert "Anmeldung abgebrochen - erneut versuchen" in seite.alles()


def test_laeuft_und_keine_datei_starten_keine_anmeldung():
    laeuft = Seite(google_block("vertrag", "laeuft"))
    assert [link["href"] for link in laeuft.links] == ["/mietvertrag"]
    assert laeuft.knoepfe == []
    assert "Anmeldung im Browser laeuft" in laeuft.alles()

    fehlt = Seite(google_block("protokoll", "keine_datei", meldung="Datei <x> fehlt"))
    assert fehlt.knoepfe == [] and fehlt.links == []
    assert "Datei <x> fehlt" in fehlt.alles()


def test_verbunden_maskiert_konto_und_zeigt_auswahl_und_abmelden():
    html = google_block("protokoll", "verbunden", konto="a<b>@mail.ch", meldung="Hinweis & so")
    seite = Seite(html)
    assert "Verbunden als a<b>@mail.ch" in seite.alles()
    assert "Hinweis & so" in seite.alles()
    assert "a<b>" not in html and "Hinweis & so" not in html
    assert "a&lt;b&gt;@mail.ch" in html and "Hinweis &amp; so" in html
    assert [(link["href"], link["text"]) for link in seite.links] == [
        ("/google/auswahl?art=protokoll", "Vorlage in Google Drive aussuchen")
    ]
    assert [knopf["text"] for knopf in seite.knoepfe] == ["Abmelden"]
    assert seite.knoepfe[0]["form"]["aktion"] == "/google/abmelden"
    assert seite.knoepfe[0]["form"]["felder"]["art"]["wert"] == "protokoll"


@pytest.mark.parametrize("art", ["", "brief", None, 5])
def test_google_block_prueft_art(art):
    with pytest.raises(ValueError, match="art"):
        google_block(art, "getrennt")


@pytest.mark.parametrize("zustand", ["", "kaputt", None, 5])
def test_google_block_prueft_zustand(zustand):
    with pytest.raises(ValueError, match="zustand"):
        google_block("vertrag", zustand)


def test_google_block_prueft_texte():
    with pytest.raises(ValueError, match="konto"):
        google_block("vertrag", "verbunden", konto=5)
    with pytest.raises(ValueError, match="meldung"):
        google_block("vertrag", "getrennt", meldung=[])


def test_auswahl_zeigt_navigation_krumen_ordner_und_dateien():
    seite = Seite(formular_auswahl("vertrag", PFAD, ORDNER, DATEIEN))
    assert [link["text"] for link in seite.links[:6]] == [
        "Meine Ablage",
        "Mit mir geteilt",
        "Zurueck zum Formular",
        "Meine Ablage",
        "Ordner: Alt & Neu",
    ]
    assert seite.links[0]["href"] == "/google/auswahl?art=vertrag&ordner=root"
    assert seite.links[1]["href"] == "/google/auswahl?art=vertrag&ordner=geteilt"
    assert seite.links[4]["href"] == "/google/auswahl?art=vertrag&ordner=F2"
    assert "Vertraege <2026>" in seite.alles()

    waehlen = [knopf for knopf in seite.knoepfe if knopf["text"] == "Waehlen"]
    assert [knopf["form"]["felder"]["id"]["wert"] for knopf in waehlen] == ["d1", "d3"]
    assert all(knopf["form"]["aktion"] == "/google/waehlen" for knopf in waehlen)


def test_auswahl_suchformular_und_filter():
    seite = Seite(formular_auswahl("protokoll", PFAD, [], DATEIEN, suche="strom", alle=True))
    suche = [form for form in seite.formulare if form["methode"] == "get"][0]
    assert suche["aktion"] == "/google/auswahl"
    assert suche["felder"]["art"]["wert"] == "protokoll"
    assert suche["felder"]["ordner"]["wert"] == "F1"
    assert suche["felder"]["q"]["wert"] == "strom"
    assert "checked" in suche["felder"]["alle"]
    ids = [
        knopf["form"]["felder"]["id"]["wert"]
        for knopf in seite.knoepfe
        if knopf["text"] == "Waehlen"
    ]
    assert ids == ["d2"]

    ohne_alle = Seite(formular_auswahl("vertrag", PFAD, [], DATEIEN))
    assert [
        knopf["form"]["felder"]["id"]["wert"]
        for knopf in ohne_alle.knoepfe
        if knopf["text"] == "Waehlen"
    ] == ["d1", "d3"]
    assert "checked" not in ohne_alle.formulare[0]["felder"]["alle"]


def test_auswahl_leere_zustaende_und_maskierung():
    leer = Seite(formular_auswahl("vertrag", PFAD, [], []))
    assert "Keine Dateien in diesem Ordner" in leer.alles()

    nur_andere = Seite(formular_auswahl("vertrag", PFAD, [], [DATEIEN[1]]))
    assert "Vertrag oder Protokoll" in nur_andere.alles()

    nichts = Seite(formular_auswahl("vertrag", PFAD, [], DATEIEN, suche="  fehlt <x>  "))
    assert "Keine Dateien mit" in nichts.alles() and "fehlt <x>" in nichts.alles()
    assert "fehlt &lt;x&gt;" in formular_auswahl("vertrag", PFAD, [], [], suche="fehlt <x>")

    hostil = formular_auswahl(
        "vertrag",
        PFAD,
        ORDNER,
        [{"id": "x", "name": "<b>Vertrag</b>"}],
        meldung="<u>Hinweis</u>",
    )
    assert "<b>" not in hostil and "<u>" not in hostil
    assert "&lt;b&gt;Vertrag&lt;/b&gt;" in hostil
    assert "&lt;u&gt;Hinweis&lt;/u&gt;" in hostil

    eingabe = formular_auswahl("vertrag", PFAD, [], [], suche='"><i>')
    assert "<i>" not in eingabe
    assert 'value="&quot;&gt;&lt;i&gt;"' in eingabe


@pytest.mark.parametrize("pfad", [[], None, ["x"], [{"id": "root"}]])
def test_auswahl_prueft_pfad(pfad):
    with pytest.raises(ValueError, match="pfad"):
        formular_auswahl("vertrag", pfad, [], [])


@pytest.mark.parametrize(("feld", "wert"), [("ordner", None), ("dateien", ())])
def test_auswahl_prueft_listen(feld, wert):
    argumente = {"ordner": [], "dateien": []}
    argumente[feld] = wert
    with pytest.raises(ValueError, match=feld):
        formular_auswahl("vertrag", PFAD, argumente["ordner"], argumente["dateien"])


def test_auswahl_prueft_eintraege_suche_und_alle():
    with pytest.raises(ValueError, match="ordner"):
        formular_auswahl("vertrag", PFAD, ["x"], [])
    with pytest.raises(ValueError, match="dateien"):
        formular_auswahl("vertrag", PFAD, [], [{"name": "ohne id"}])
    with pytest.raises(ValueError, match="suche"):
        formular_auswahl("vertrag", PFAD, [], [], suche=5)
    with pytest.raises(ValueError, match="alle"):
        formular_auswahl("vertrag", PFAD, [], [], alle="ja")
    with pytest.raises(ValueError, match="art"):
        formular_auswahl("brief", PFAD, [], [])
