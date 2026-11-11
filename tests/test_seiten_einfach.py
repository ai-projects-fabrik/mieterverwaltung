"""Tests fuer die vereinfachten HTML-Seiten."""

from html.parser import HTMLParser

import pytest

from projekt.seiten_einfach import (
    TABS_EINFACH,
    formular_objekttabelle,
    formular_ordner,
    formular_uebergabe,
    formular_vertrag,
    rahmen_einfach,
)

OBJEKTE = [
    {"id": "a", "bezeichnung": "Haus <A>"},
    {"id": "b", "bezeichnung": "Haus B"},
]
VORLAGEN = {"lokal": ["Allgemein.docx"], "drive": ["Protokoll & Co.docx"]}


class Formular(HTMLParser):
    def __init__(self):
        super().__init__()
        self.felder = []
        self.optionen = {}
        self.texte = []
        self.formulare = []
        self._select = None

    def handle_starttag(self, tag, attrs):
        attribute = dict(attrs)
        if tag == "form":
            self.formulare.append((attribute.get("method"), attribute.get("action")))
        if tag in ("input", "select", "textarea") and attribute.get("name"):
            self.felder.append((tag, attribute["name"], attribute))
        if tag == "select":
            self._select = attribute.get("name")
            self.optionen[self._select] = []
        if tag == "option" and self._select:
            self.optionen[self._select].append((attribute.get("value"), "selected" in attribute))

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None

    def handle_data(self, data):
        if data.strip():
            self.texte.append(data.strip())


def lese(html: str) -> Formular:
    formular = Formular()
    formular.feed(html)
    formular.close()
    return formular


def namen(formular: Formular) -> list[str]:
    return [name for _, name, _ in formular.felder]


def test_tabs_und_rahmen():
    assert TABS_EINFACH == (
        ("mietvertrag", "Mietvertrag"),
        ("protokoll", "Übergabeprotokoll"),
        ("objekte", "Objekte"),
        ("settings", "Einstellungen"),
    )
    seite = rahmen_einfach("settings", "<p>Inhalt</p>")
    assert seite.startswith('<!doctype html><html lang="de">')
    assert '<meta charset="utf-8">' in seite
    assert "<p>Inhalt</p>" in seite
    assert seite.count('aria-current="page"') == 1
    assert 'href="/settings" aria-current="page"' in seite
    for tab, _ in TABS_EINFACH:
        assert f'href="/{tab}"' in seite


@pytest.mark.parametrize("aktiv", ["", "unbekannt", None, 5])
def test_rahmen_lehnt_unbekannten_tab_ab(aktiv):
    with pytest.raises(ValueError, match="aktiv"):
        rahmen_einfach(aktiv, "")


def test_ordnerformular_maskiert_und_zeigt_hinweis():
    html = formular_ordner('G:\\My "Drive"', "C:\\Mietverwaltung", "Gespeichert <b>")
    formular = lese(html)
    assert namen(formular) == ["drive_ordner", "lokaler_ordner"]
    assert formular.formulare == [("post", "/settings")]
    werte = {name: attribute.get("value") for _, name, attribute in formular.felder}
    assert werte == {
        "drive_ordner": 'G:\\My "Drive"',
        "lokaler_ordner": "C:\\Mietverwaltung",
    }
    sichtbar = " ".join(formular.texte)
    assert "Google-Drive-Ordner" in sichtbar
    assert "Lokaler Ordner" in sichtbar
    assert "Unterordner" in sichtbar
    assert "Gespeichert <b>" in sichtbar
    assert "&lt;b&gt;" in html and "<b>" not in html


def test_objekttabelle_hat_versteckte_ids_und_zwei_leere_zeilen():
    html = formular_objekttabelle([{"id": "a", "bezeichnung": "Haus <A>", "kaution": "3'000.00"}])
    formular = lese(html)
    assert formular.formulare == [("post", "/objekte")]
    for nummer in (0, 1, 2):
        for feld in ("id", "bezeichnung", "miete_netto", "nebenkosten", "kaution"):
            assert f"zeile_{nummer}_{feld}" in namen(formular)
    assert "zeile_3_bezeichnung" not in namen(formular)
    assert "neu_id" not in namen(formular)

    werte = {name: attribute.get("value") for _, name, attribute in formular.felder}
    assert werte["zeile_0_id"] == "a"
    assert werte["zeile_0_bezeichnung"] == "Haus <A>"
    assert werte["zeile_0_kaution"] == "3'000.00"
    assert werte["zeile_1_id"] == "" and werte["zeile_2_bezeichnung"] == ""

    sichtbar = " ".join(formular.texte)
    for kopf in ("Bezeichnung", "Miete netto (CHF)", "Nebenkosten (CHF)", "Kaution (CHF)"):
        assert kopf in sichtbar
    assert "entfernt das Objekt" in sichtbar


def test_objekttabelle_maskiert_alle_werte_und_meldung():
    html = formular_objekttabelle(
        [{"id": '"><script>', "bezeichnung": '"><script>x</script>'}],
        "Zeile 1: <fehler>",
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;fehler&gt;" in html


@pytest.mark.parametrize("zeilen", ["keine Liste", None, ({"id": "a"},)])
def test_objekttabelle_prueft_die_zeilenliste(zeilen):
    with pytest.raises(ValueError, match="zeilen"):
        formular_objekttabelle(zeilen)


def test_objekttabelle_prueft_jede_zeile():
    with pytest.raises(ValueError, match="zeilen"):
        formular_objekttabelle([{"bezeichnung": "A"}, "keine Zeile"])


def test_vertragsformular_hat_nur_die_noetigen_felder():
    formular = lese(formular_vertrag(OBJEKTE, VORLAGEN))
    assert namen(formular) == [
        "objekt_id",
        "vorlage",
        "mieter_name",
        "wohnraumnutzer_name",
        "mietbeginn",
        "anfrage",
        "format",
        "ziel",
    ]
    assert formular.formulare == [("post", "/mietvertrag")]
    assert [wert for wert, _ in formular.optionen["objekt_id"]] == ["a", "b"]
    assert [wert for wert, _ in formular.optionen["vorlage"]] == [
        "lokal:Allgemein.docx",
        "drive:Protokoll & Co.docx",
    ]
    assert [wert for wert, _ in formular.optionen["format"]] == ["docx+pdf", "docx", "pdf"]
    assert [wert for wert, _ in formular.optionen["ziel"]] == ["drive", "lokal"]
    assert [wert for wert, gewaehlt in formular.optionen["format"] if gewaehlt] == ["docx+pdf"]
    assert [wert for wert, gewaehlt in formular.optionen["ziel"] if gewaehlt] == ["drive"]
    for gestrichen in ("objekt", "miete_netto", "nebenkosten", "kaution"):
        assert gestrichen not in namen(formular)


def test_vertragsformular_belegt_vor_und_maskiert():
    html = formular_vertrag(
        OBJEKTE,
        VORLAGEN,
        {
            "objekt_id": "b",
            "vorlage": "drive:Protokoll & Co.docx",
            "format": "pdf",
            "ziel": "lokal",
            "mieter_name": "Erika <M>",
            "mietbeginn": "1.2.2027",
            "anfrage": "Kaution: <3000>",
        },
        "Fehler <script>",
    )
    formular = lese(html)
    gewaehlt = {
        name: [wert for wert, ausgewaehlt in optionen if ausgewaehlt]
        for name, optionen in formular.optionen.items()
    }
    assert gewaehlt == {
        "objekt_id": ["b"],
        "vorlage": ["drive:Protokoll & Co.docx"],
        "format": ["pdf"],
        "ziel": ["lokal"],
    }
    assert "Erika <M>" not in html and "Erika &lt;M&gt;" in html
    assert "<3000>" not in html and "Fehler <script>" not in html


def test_vertragsformular_faellt_bei_ungueltigen_auswahlen_zurueck():
    formular = lese(formular_vertrag(OBJEKTE, VORLAGEN, {"format": "rtf", "ziel": "weg"}))
    assert [wert for wert, gewaehlt in formular.optionen["format"] if gewaehlt] == ["docx+pdf"]
    assert [wert for wert, gewaehlt in formular.optionen["ziel"] if gewaehlt] == ["drive"]


def test_vertragsformular_ohne_objekte_zeigt_nur_meldung_und_hinweis():
    html = formular_vertrag([], VORLAGEN, None, "Achtung <1>")
    formular = lese(html)
    assert namen(formular) == []
    assert formular.formulare == []
    assert "Achtung &lt;1&gt;" in html
    assert "Objekte" in " ".join(formular.texte)


def test_vertragsformular_prueft_eingaben_und_leere_vorlagen():
    with pytest.raises(ValueError, match="objekte"):
        formular_vertrag("keine Liste", VORLAGEN)
    with pytest.raises(ValueError, match="werte"):
        formular_vertrag(OBJEKTE, VORLAGEN, [])
    with pytest.raises(ValueError, match="vorlagen"):
        formular_vertrag(OBJEKTE, [])
    with pytest.raises(ValueError, match="vorlagen.lokal"):
        formular_vertrag(OBJEKTE, {"lokal": "keine Liste"})

    formular = lese(formular_vertrag(OBJEKTE, {}))
    assert formular.optionen["vorlage"] == []


def test_uebergabeformular_hat_alle_felder_und_standard_art():
    formular = lese(formular_uebergabe(OBJEKTE, VORLAGEN))
    assert namen(formular) == [
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
    assert formular.formulare == [("post", "/protokoll")]
    assert [wert for wert, _ in formular.optionen["art"]] == ["Einzug", "Auszug"]
    assert [wert for wert, gewaehlt in formular.optionen["art"] if gewaehlt] == ["Einzug"]
    assert "objekt" not in namen(formular) and "anfrage" not in namen(formular)

    sichtbar = " ".join(formular.texte)
    for label in (
        "Übergabedatum",
        "Zählerstand Strom",
        "Zählerstand Wasser",
        "Anzahl Schlüssel",
        "Bemerkungen",
    ):
        assert label in sichtbar


def test_uebergabeformular_belegt_vor_und_faellt_bei_ungueltiger_art_zurueck():
    html = formular_uebergabe(
        OBJEKTE,
        VORLAGEN,
        {
            "art": "Auszug",
            "bemerkungen": "<i>Kratzer</i>",
            "zaehler_strom": "12.5",
        },
    )
    formular = lese(html)
    assert [wert for wert, gewaehlt in formular.optionen["art"] if gewaehlt] == ["Auszug"]
    werte = {name: attribute.get("value") for _, name, attribute in formular.felder}
    assert werte["zaehler_strom"] == "12.5"
    assert "&lt;i&gt;Kratzer&lt;/i&gt;" in html and "<i>" not in html

    kaputt = lese(formular_uebergabe(OBJEKTE, VORLAGEN, {"art": "Besichtigung"}))
    assert [wert for wert, gewaehlt in kaputt.optionen["art"] if gewaehlt] == ["Einzug"]


def test_uebergabeformular_ohne_objekte_zeigt_nur_hinweis():
    html = formular_uebergabe([], VORLAGEN, meldung="Fehler <x>")
    formular = lese(html)
    assert namen(formular) == []
    assert formular.formulare == []
    assert "Fehler &lt;x&gt;" in html
    assert "Objekte" in " ".join(formular.texte)


def test_vorlagen_hinweise_erscheinen_maskiert_und_leere_gruppen_entfallen():
    html = formular_vertrag(
        OBJEKTE, {"lokal": ["A.docx"], "drive": []}, None, "", ["Keine Vorlage in <G:/x> & Co"]
    )
    assert 'label="Festplatte"' in html and 'label="Google Drive"' not in html
    assert '<p class="hinweis">Keine Vorlage in &lt;G:/x&gt; &amp; Co</p>' in html
    assert "optgroup" not in formular_uebergabe(OBJEKTE, {}, None, "", ["x"])
    assert 'class="hinweis"' not in formular_vertrag(OBJEKTE, VORLAGEN)


def test_menue_ist_tab_leiste_mit_abstand_und_hervorhebung():
    seite = rahmen_einfach("protokoll", "")
    assert "<style>" in seite and "nav a{" in seite and "padding" in seite
    assert "nav a[aria-current]{" in seite
    assert seite.count('aria-current="page"') == 1


def test_google_gruppe_zeigt_dateinamen_mit_id_als_wert():
    vorlagen = {"google": [{"id": "g<1>", "name": "Mein Vertrag & Co"}, "kaputt"]}
    html = formular_vertrag(OBJEKTE, vorlagen, {"vorlage": "google:g<1>"})
    assert 'label="Google Docs / Drive (online)"' in html
    assert '<option value="google:g&lt;1&gt;" selected>Mein Vertrag &amp; Co</option>' in html
    assert "kaputt" not in html
