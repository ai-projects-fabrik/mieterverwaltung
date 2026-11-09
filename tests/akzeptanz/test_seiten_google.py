"""Akzeptanztest (spec-first) fuer projekt.seiten_google (Ziel `mv-seiten-google`)."""

import importlib.util
from html.parser import HTMLParser

import pytest

if importlib.util.find_spec("projekt.seiten_google") is None:
    pytest.skip("Modul noch nicht umgesetzt", allow_module_level=True)

from projekt.seiten_google import ZUSTAENDE, formular_auswahl, google_block  # noqa: E402


class Seite(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.formulare, self.knoepfe, self.text = [], [], [], []
        self._form = None
        self._a = None
        self._knopf = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            self._a = {"href": a.get("href"), "text": ""}
            self.links.append(self._a)
        elif tag == "form":
            self._form = {"methode": a.get("method"), "aktion": a.get("action"), "felder": {}}
            self.formulare.append(self._form)
        elif tag == "input" and self._form is not None:
            self._form["felder"][a.get("name")] = {
                "typ": a.get("type"),
                "wert": a.get("value"),
                **a,
            }
        elif tag == "button":
            self._knopf = True
            self.knoepfe.append({"text": "", "form": self._form})

    def handle_endtag(self, tag):
        if tag == "a":
            self._a = None
        elif tag == "form":
            self._form = None
        elif tag == "button":
            self._knopf = False

    def handle_data(self, data):
        self.text.append(data)
        if self._a is not None:
            self._a["text"] += data
        if self._knopf:
            self.knoepfe[-1]["text"] += data

    def alles(self):
        return "".join(self.text)


PFAD = [{"id": "root", "name": "Meine Ablage"}, {"id": "F1", "name": "Vertraege <2026>"}]
ORDNER = [{"id": "F2", "name": "Alt & Neu"}]
DATEIEN = [
    {"id": "d1", "name": "Feltenbummler Vertrag", "mime": "m", "eigene": False},
    {"id": "d2", "name": "Rechnung Strom", "mime": "m", "eigene": True},
    {"id": "d3", "name": "August26-Uebergabeprotokoll", "mime": "m", "eigene": False},
]


def test_zustaende():
    assert ZUSTAENDE == ("keine_datei", "getrennt", "laeuft", "abgebrochen", "verbunden")


def test_block_getrennt_hat_anmeldeknopf():
    s = Seite(google_block("vertrag", "getrennt"))
    assert [k["text"] for k in s.knoepfe] == ["Bei Google anmelden"]
    form = s.knoepfe[0]["form"]
    assert form["methode"] == "post" and form["aktion"] == "/google/anmelden"
    assert form["felder"]["art"]["wert"] == "vertrag"
    assert s.links == []


def test_block_laeuft_abgebrochen_und_keine_datei():
    laeuft = Seite(google_block("protokoll", "laeuft"))
    assert "Anmeldung im Browser laeuft" in laeuft.alles()
    assert [link["href"] for link in laeuft.links] == ["/protokoll"] and laeuft.knoepfe == []
    abgebrochen = Seite(google_block("vertrag", "abgebrochen"))
    assert "Anmeldung abgebrochen - erneut versuchen" in abgebrochen.alles()
    assert [k["text"] for k in abgebrochen.knoepfe] == ["Bei Google anmelden"]
    fehlt = Seite(google_block("vertrag", "keine_datei", meldung="Datei <x> fehlt"))
    assert "Datei <x> fehlt" in fehlt.alles() and fehlt.knoepfe == []
    mit_meldung = Seite(google_block("vertrag", "getrennt", meldung="Fehler & so"))
    assert "Fehler & so" in mit_meldung.alles()
    assert [k["text"] for k in mit_meldung.knoepfe] == ["Bei Google anmelden"]


def test_block_verbunden_zeigt_konto_auswahl_und_abmelden():
    html = google_block("vertrag", "verbunden", konto="a<b>@mail.ch")
    s = Seite(html)
    assert "Verbunden als a<b>@mail.ch" in s.alles() and "a<b>" not in html
    assert [(link["href"], link["text"]) for link in s.links] == [
        ("/google/auswahl?art=vertrag", "Vorlage in Google Drive aussuchen")
    ]
    assert [k["text"] for k in s.knoepfe] == ["Abmelden"]
    assert s.knoepfe[0]["form"]["aktion"] == "/google/abmelden"
    assert s.knoepfe[0]["form"]["felder"]["art"]["wert"] == "vertrag"


def test_block_prueft_eingaben():
    with pytest.raises(ValueError, match="art"):
        google_block("brief", "getrennt")
    with pytest.raises(ValueError, match="zustand"):
        google_block("vertrag", "kaputt")


def test_auswahl_navigation_und_dateien():
    s = Seite(formular_auswahl("vertrag", PFAD, ORDNER, DATEIEN))
    hrefs = {link["text"]: link["href"] for link in s.links}
    assert hrefs["Meine Ablage"] == "/google/auswahl?art=vertrag&ordner=root"
    assert hrefs["Mit mir geteilt"] == "/google/auswahl?art=vertrag&ordner=geteilt"
    assert hrefs["Zurueck zum Formular"] == "/mietvertrag"
    assert hrefs["Ordner: Alt & Neu"] == "/google/auswahl?art=vertrag&ordner=F2"
    assert "Vertraege <2026>" in s.alles()
    waehlen = [k["form"] for k in s.knoepfe if k["text"] == "Waehlen"]
    assert [f["felder"]["id"]["wert"] for f in waehlen] == ["d1", "d3"]
    assert all(f["aktion"] == "/google/waehlen" and f["methode"] == "post" for f in waehlen)
    assert waehlen[0]["felder"]["art"]["wert"] == "vertrag"
    suche = [f for f in s.formulare if f["methode"] == "get"][0]
    assert suche["aktion"] == "/google/auswahl"
    assert suche["felder"]["ordner"]["wert"] == "F1" and suche["felder"]["q"]["wert"] == ""
    assert "checked" not in suche["felder"]["alle"]
    assert "Alle Dateien anzeigen" in s.alles()


def test_auswahl_alle_dateien_und_suche():
    s = Seite(formular_auswahl("protokoll", PFAD, [], DATEIEN, alle=True))
    ids = [k["form"]["felder"]["id"]["wert"] for k in s.knoepfe if k["text"] == "Waehlen"]
    assert ids == ["d1", "d2", "d3"]
    assert "checked" in [f for f in s.formulare if f["methode"] == "get"][0]["felder"]["alle"]
    assert Seite(formular_auswahl("protokoll", PFAD, [], DATEIEN)).links[2]["href"] == "/protokoll"
    s = Seite(formular_auswahl("vertrag", PFAD, [], DATEIEN, suche="strom", alle=True))
    ids = [k["form"]["felder"]["id"]["wert"] for k in s.knoepfe if k["text"] == "Waehlen"]
    assert ids == ["d2"]
    suche = [f for f in s.formulare if f["methode"] == "get"][0]
    assert suche["felder"]["q"]["wert"] == "strom"
    s = Seite(formular_auswahl("vertrag", PFAD, [], DATEIEN, suche="strom"))
    assert "Keine Dateien mit" in s.alles() and "strom" in s.alles()


def test_auswahl_leere_zustaende_und_maskierung():
    assert (
        "Keine Dateien in diesem Ordner" in Seite(formular_auswahl("vertrag", PFAD, [], [])).alles()
    )
    nur_andere = [DATEIEN[1]]
    s = Seite(formular_auswahl("vertrag", PFAD, [], nur_andere))
    assert "Vertrag oder Protokoll" in s.alles() and "Alle Dateien anzeigen" in s.alles()
    html = formular_auswahl(
        "vertrag", PFAD, ORDNER, [{"id": "x", "name": "<b>Vertrag</b>"}], meldung="<u>"
    )
    assert "<b>" not in html and "<u>" not in html
    assert "&lt;b&gt;Vertrag&lt;/b&gt;" in html
    hostil = formular_auswahl("vertrag", PFAD, [], [], suche='"><i>')
    assert "<i>" not in hostil
    assert Seite(hostil).formulare[-1]["felder"]["q"]["wert"] == '"><i>'


def test_auswahl_prueft_eingaben():
    with pytest.raises(ValueError, match="art"):
        formular_auswahl("brief", PFAD, [], [])
    for pfad in ([], None, ["x"]):
        with pytest.raises(ValueError, match="pfad"):
            formular_auswahl("vertrag", pfad, [], [])
    with pytest.raises(ValueError, match="ordner"):
        formular_auswahl("vertrag", PFAD, None, [])
    with pytest.raises(ValueError, match="suche"):
        formular_auswahl("vertrag", PFAD, [], [], suche=5)
