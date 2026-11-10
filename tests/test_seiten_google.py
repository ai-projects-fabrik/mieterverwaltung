"""Tests fuer die Google-Seiten mit synthetischen Daten ohne Netzwerk."""

from html.parser import HTMLParser

import pytest

from projekt.seiten_google import SEITEN, ZUSTAENDE, formular_auswahl, google_block

PFAD = [{"id": "root", "name": "Meine Ablage"}, {"id": "F1", "name": "Vertraege <2026>"}]
ORDNER = [{"id": "F2", "name": "Alt & Neu"}]
DATEIEN = [
    {"id": "d1", "name": "Feltenbummler Vertrag", "mime": "m", "eigene": False},
    {"id": "d2", "name": "Rechnung Strom", "mime": "m", "eigene": True},
    {"id": "d3", "name": "August26-Uebergabeprotokoll", "mime": "m", "eigene": False},
]


class Seite(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.formulare = []
        self.knoepfe = []
        self.text = []
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


def test_konstanten_sind_fest():
    assert SEITEN == {"vertrag": "/mietvertrag", "protokoll": "/protokoll"}
    assert ZUSTAENDE == ("keine_datei", "getrennt", "laeuft", "abgebrochen", "verbunden")


def test_block_getrennt_und_abgebrochen_bieten_die_anmeldung_an():
    getrennt = Seite(google_block("vertrag", "getrennt"))
    assert getrennt.links == []
    assert [knopf["text"] for knopf in getrennt.knoepfe] == ["Bei Google anmelden"]
    form = getrennt.knoepfe[0]["form"]
    assert (form["methode"], form["aktion"]) == ("post", "/google/anmelden")
    assert form["felder"]["art"]["wert"] == "vertrag"

    abgebrochen = Seite(google_block("protokoll", "abgebrochen"))
    assert "Anmeldung abgebrochen - erneut versuchen" in abgebrochen.alles()
    assert [knopf["text"] for knopf in abgebrochen.knoepfe] == ["Bei Google anmelden"]
    assert abgebrochen.knoepfe[0]["form"]["felder"]["art"]["wert"] == "protokoll"


def test_block_laeuft_verlinkt_nur_die_formularseite():
    seite = Seite(google_block("protokoll", "laeuft"))
    assert "Anmeldung im Browser laeuft. Bitte dort zustimmen und danach" in seite.alles()
    assert [(link["href"], link["text"]) for link in seite.links] == [
        ("/protokoll", "Seite neu laden")
    ]
    assert seite.knoepfe == []


def test_block_verbunden_zeigt_konto_auswahl_und_abmelden():
    seite = Seite(google_block("vertrag", "verbunden", konto="a@b.ch"))
    assert "Verbunden als a@b.ch" in seite.alles()
    assert [(link["href"], link["text"]) for link in seite.links] == [
        ("/google/auswahl?art=vertrag", "Vorlage in Google Drive aussuchen")
    ]
    assert [knopf["text"] for knopf in seite.knoepfe] == ["Abmelden"]
    assert seite.knoepfe[0]["form"]["aktion"] == "/google/abmelden"
    assert seite.knoepfe[0]["form"]["felder"]["art"]["wert"] == "vertrag"


def test_block_keine_datei_hat_nur_die_meldung():
    seite = Seite(google_block("vertrag", "keine_datei", meldung="Datei fehlt"))
    assert "Datei fehlt" in seite.alles()
    assert seite.knoepfe == []


def test_block_maskiert_konto_und_meldung():
    html = google_block(
        "vertrag",
        "verbunden",
        konto="a<b>@mail.ch",
        meldung="Fehler & <script>",
    )
    assert "<b>" not in html
    assert "<script>" not in html
    seite = Seite(html)
    assert "Verbunden als a<b>@mail.ch" in seite.alles()
    assert "Fehler & <script>" in seite.alles()


@pytest.mark.parametrize("art", ["brief", "", None, 5])
def test_block_prueft_die_art(art):
    with pytest.raises(ValueError, match="art"):
        google_block(art, "getrennt")


@pytest.mark.parametrize("zustand", ["kaputt", "", None, 5])
def test_block_prueft_den_zustand(zustand):
    with pytest.raises(ValueError, match="zustand"):
        google_block("vertrag", zustand)


def test_block_prueft_konto_und_meldung():
    with pytest.raises(ValueError, match="konto"):
        google_block("vertrag", "getrennt", konto=None)
    with pytest.raises(ValueError, match="meldung"):
        google_block("vertrag", "getrennt", meldung=5)


def test_auswahl_navigation_krumen_und_unterordner():
    html = formular_auswahl("vertrag", PFAD, ORDNER, DATEIEN)
    seite = Seite(html)
    assert [(link["text"], link["href"]) for link in seite.links[:3]] == [
        ("Meine Ablage", "/google/auswahl?art=vertrag&ordner=root"),
        ("Mit mir geteilt", "/google/auswahl?art=vertrag&ordner=geteilt"),
        ("Zurueck zum Formular", "/mietvertrag"),
    ]
    assert ("Ordner: Alt & Neu", "/google/auswahl?art=vertrag&ordner=F2") in [
        (link["text"], link["href"]) for link in seite.links
    ]
    assert "<strong>Vertraege &lt;2026&gt;</strong>" in html


def test_auswahl_formular_hat_suche_ordner_und_alle_schalter():
    seite = Seite(formular_auswahl("vertrag", PFAD, [], DATEIEN))
    form = [eintrag for eintrag in seite.formulare if eintrag["methode"] == "get"][0]
    assert form["aktion"] == "/google/auswahl"
    assert form["felder"]["art"]["wert"] == "vertrag"
    assert form["felder"]["ordner"]["wert"] == "F1"
    assert form["felder"]["q"]["wert"] == ""
    assert "checked" not in form["felder"]["alle"]
    assert [knopf["text"] for knopf in seite.knoepfe if knopf["text"] == "Suchen"] == ["Suchen"]

    alle = Seite(formular_auswahl("protokoll", PFAD, [], DATEIEN, suche="a b", alle=True))
    form = [eintrag for eintrag in alle.formulare if eintrag["methode"] == "get"][0]
    assert form["felder"]["q"]["wert"] == "a b"
    assert "checked" in form["felder"]["alle"]
    assert form["felder"]["ordner"]["wert"] == "F1"


def test_auswahl_filtert_standardmaessig_auf_vertrag_und_protokoll():
    seite = Seite(formular_auswahl("vertrag", PFAD, [], DATEIEN))
    ids = [
        knopf["form"]["felder"]["id"]["wert"]
        for knopf in seite.knoepfe
        if knopf["text"] == "Waehlen"
    ]
    assert ids == ["d1", "d3"]
    for knopf in seite.knoepfe:
        if knopf["text"] == "Waehlen":
            assert knopf["form"]["aktion"] == "/google/waehlen"
            assert knopf["form"]["methode"] == "post"
            assert knopf["form"]["felder"]["art"]["wert"] == "vertrag"

    alle = Seite(formular_auswahl("protokoll", PFAD, [], DATEIEN, alle=True))
    ids = [
        knopf["form"]["felder"]["id"]["wert"]
        for knopf in alle.knoepfe
        if knopf["text"] == "Waehlen"
    ]
    assert ids == ["d1", "d2", "d3"]


def test_auswahl_suche_wird_vor_dem_stichwortfilter_angewendet():
    seite = Seite(formular_auswahl("vertrag", PFAD, [], DATEIEN, suche="strom", alle=True))
    ids = [
        knopf["form"]["felder"]["id"]["wert"]
        for knopf in seite.knoepfe
        if knopf["text"] == "Waehlen"
    ]
    assert ids == ["d2"]

    ohne_alle = Seite(formular_auswahl("vertrag", PFAD, [], DATEIEN, suche="strom"))
    assert "Keine Dateien mit" in ohne_alle.alles()
    assert "strom" in ohne_alle.alles()


def test_auswahl_leere_zustaende():
    assert (
        "Keine Dateien in diesem Ordner" in Seite(formular_auswahl("vertrag", PFAD, [], [])).alles()
    )
    nur_andere = Seite(formular_auswahl("vertrag", PFAD, [], [DATEIEN[1]]))
    assert "Vertrag oder Protokoll" in nur_andere.alles()
    assert "Alle Dateien anzeigen" in nur_andere.alles()


def test_auswahl_maskiert_alle_ausgaben():
    html = formular_auswahl(
        "vertrag",
        PFAD,
        ORDNER,
        [{"id": "x", "name": "<b>Vertrag</b>"}],
        meldung="<u>",
    )
    assert "<b>" not in html
    assert "<u>" not in html
    assert "&lt;b&gt;Vertrag&lt;/b&gt;" in html

    hostil = formular_auswahl("vertrag", PFAD, [], [], suche='"><i>')
    assert "<i>" not in hostil
    form = Seite(hostil).formulare[-1]
    assert form["felder"]["q"]["wert"] == '"><i>'


@pytest.mark.parametrize("art", ["brief", "", None, 5])
def test_auswahl_prueft_die_art(art):
    with pytest.raises(ValueError, match="art"):
        formular_auswahl(art, PFAD, [], [])


@pytest.mark.parametrize("pfad", [[], None, ("root",), ["x"], [{"id": "root"}], [{"name": "x"}]])
def test_auswahl_prueft_den_pfad(pfad):
    with pytest.raises(ValueError, match="pfad"):
        formular_auswahl("vertrag", pfad, [], [])


@pytest.mark.parametrize("ordner", [None, (), "x"])
def test_auswahl_prueft_die_unterordner(ordner):
    with pytest.raises(ValueError, match="ordner"):
        formular_auswahl("vertrag", PFAD, ordner, [])


@pytest.mark.parametrize("dateien", [None, (), "x"])
def test_auswahl_prueft_die_dateien(dateien):
    with pytest.raises(ValueError, match="dateien"):
        formular_auswahl("vertrag", PFAD, [], dateien)


@pytest.mark.parametrize("suche", [None, 5, b"x"])
def test_auswahl_prueft_die_suche(suche):
    with pytest.raises(ValueError, match="suche"):
        formular_auswahl("vertrag", PFAD, [], [], suche=suche)


@pytest.mark.parametrize("alle", ["ja", 1, None])
def test_auswahl_prueft_alle(alle):
    with pytest.raises(ValueError, match="alle"):
        formular_auswahl("vertrag", PFAD, [], [], alle=alle)


def test_auswahl_prueft_die_meldung():
    with pytest.raises(ValueError, match="meldung"):
        formular_auswahl("vertrag", PFAD, [], [], meldung=5)
