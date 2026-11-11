"""Reine HTML-Erzeugung fuer Mietvertrag, Uebergabeprotokoll und Settings."""

from __future__ import annotations

from html import escape

from projekt.einstellungen import EINSTELLUNGEN_FELDER
from projekt.felder import FELDER
from projekt.protokoll import PROTOKOLL_FELDER

TABS: tuple[tuple[str, str], ...] = (
    ("mietvertrag", "Mietvertrag"),
    ("protokoll", "Übergabeprotokoll"),
    ("settings", "Settings"),
)

_FORMATE = ("docx", "pdf", "docx+pdf")
_ZIELE = ("lokal", "drive")
_VORLAGEN_ORTE = (("lokal", "Festplatte"), ("drive", "Google Drive"))

_ANZEIGENAMEN = {
    "mieter_name": "Name des Mieters",
    "wohnraumnutzer_name": "Name des Wohnraumnutzers",
    "objekt": "Objekt",
    "mietbeginn": "Mietbeginn",
    "mietende": "Mietende",
    "miete_netto": "Miete",
    "nebenkosten": "Nebenkosten",
    "kaution": "Kaution",
    "uebergabedatum": "Übergabedatum",
    "art": "Art",
    "zaehler_strom": "Zählerstand Strom",
    "zaehler_wasser": "Zählerstand Wasser",
    "schluessel_anzahl": "Anzahl Schlüssel",
    "bemerkungen": "Bemerkungen",
}

_QUELLEN = {"formular": "Formular", "objekt": "Objekt", "anfrage": "Änderungen"}


def _text(wert: object) -> str:
    return "" if wert is None else str(wert)


def _maskiert(wert: object) -> str:
    return escape(_text(wert))


def _meldung(meldung: str) -> str:
    return f'<p class="meldung">{_maskiert(meldung)}</p>' if meldung else ""


def _eingabe(name: str, wert: object = "", typ: str = "text") -> str:
    return (
        f'<tr><th><label for="{name}">{name}</label></th><td>'
        f'<input id="{name}" name="{name}" type="{typ}" value="{_maskiert(wert)}">'
        "</td></tr>"
    )


def _textbereich(name: str, wert: object = "", zeilen: int = 4) -> str:
    return (
        f'<tr><th><label for="{name}">{name}</label></th><td>'
        f'<textarea id="{name}" name="{name}" rows="{zeilen}">{_maskiert(wert)}</textarea>'
        "</td></tr>"
    )


def _auswahl(
    name: str,
    optionen: tuple[tuple[str, str], ...],
    gewaehlt: object,
) -> str:
    auswahl = _text(gewaehlt)
    inhalt = "".join(
        f'<option value="{_maskiert(wert)}"'
        f"{' selected' if wert == auswahl else ''}>{_maskiert(text)}</option>"
        for wert, text in optionen
    )
    return (
        f'<tr><th><label for="{name}">{name}</label></th><td>'
        f'<select id="{name}" name="{name}">{inhalt}</select></td></tr>'
    )


def _objekt_auswahl(objekte: list[dict], gewaehlt: object) -> str:
    auswahl = _text(gewaehlt)
    optionen = ['<option value=""></option>']
    for objekt in objekte:
        objekt_id = _text(objekt.get("id", ""))
        bezeichnung = _text(objekt.get("bezeichnung", ""))
        optionen.append(
            f'<option value="{_maskiert(objekt_id)}"'
            f"{' selected' if objekt_id == auswahl else ''}>{_maskiert(bezeichnung)}</option>"
        )
    return (
        '<tr><th><label for="objekt_id">objekt_id</label></th><td>'
        '<select id="objekt_id" name="objekt_id">' + "".join(optionen) + "</select></td></tr>"
    )


def _vorlagen_auswahl(vorlagen: dict[str, list[str]], gewaehlt: object) -> str:
    auswahl = _text(gewaehlt)
    gruppen: list[str] = []
    for ort, label in _VORLAGEN_ORTE:
        optionen = []
        for name in vorlagen.get(ort, []):
            wert = f"{ort}:{_text(name)}"
            optionen.append(
                f'<option value="{_maskiert(wert)}"'
                f"{' selected' if wert == auswahl else ''}>{_maskiert(name)}</option>"
            )
        gruppen.append(f'<optgroup label="{label}">{"".join(optionen)}</optgroup>')
    return (
        '<tr><th><label for="vorlage">vorlage</label></th><td>'
        '<select id="vorlage" name="vorlage">' + "".join(gruppen) + "</select></td></tr>"
    )


def rahmen(aktiv: str, inhalt: str) -> str:
    """Setzt Inhalt unveraendert in das HTML5-Grundgeruest mit Tab-Navigation.

    ``aktiv`` muss einer der Schluessel aus :data:`TABS` sein; ein unbekannter
    Tab loest einen ValueError mit dem Begriff ``aktiv`` aus.
    """

    labels = dict(TABS)
    if not isinstance(aktiv, str) or aktiv not in labels:
        raise ValueError(f"aktiver Tab '{aktiv}' ist unbekannt")

    links = []
    for tab, label in TABS:
        aktuell = ' aria-current="page"' if tab == aktiv else ""
        links.append(f'<a href="/{tab}"{aktuell}>{escape(label)}</a>')
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        "<title>Mietverwaltung</title></head><body>"
        f"<nav>{''.join(links)}</nav><main>{inhalt}</main></body></html>"
    )


def formular_mietvertrag(
    objekte: list[dict],
    vorlagen: dict[str, list[str]],
    werte: dict[str, str] | None = None,
    meldung: str = "",
) -> str:
    """Erzeugt das maskierte Mietvertragsformular als HTML-Fragment.

    ``werte`` belegt Eingaben und Auswahlen vor; ``meldung`` erscheint davor.
    Objekt-, Vorlagen- und Feldwerte werden HTML-maskiert ausgegeben.
    """

    daten = {} if werte is None else werte
    return _mietvertrag_formular(objekte, vorlagen, daten, meldung)


def _mietvertrag_formular(
    objekte: list[dict],
    vorlagen: dict[str, list[str]],
    werte: dict[str, str],
    meldung: str,
) -> str:
    eingaben = [_eingabe(feld, werte.get(feld, "")) for feld in FELDER]
    eingaben.append(_textbereich("anfrage", werte.get("anfrage", ""), 8))
    format_wert = werte.get("format", "docx")
    if format_wert not in _FORMATE:
        format_wert = "docx"
    ziel_wert = werte.get("ziel", "lokal")
    if ziel_wert not in _ZIELE:
        ziel_wert = "lokal"
    return (
        _meldung(meldung)
        + '<form method="post" action="/mietvertrag"><table>'
        + _objekt_auswahl(objekte, werte.get("objekt_id", ""))
        + _vorlagen_auswahl(vorlagen, werte.get("vorlage", ""))
        + _auswahl("format", tuple((wert, wert) for wert in _FORMATE), format_wert)
        + _auswahl("ziel", tuple((wert, wert) for wert in _ZIELE), ziel_wert)
        + "".join(eingaben)
        + '<tr><td colspan="2"><button type="submit">Erstellen</button></td></tr>'
        "</table></form>"
    )


def formular_protokoll(
    objekte: list[dict],
    vorlagen: dict[str, list[str]],
    werte: dict[str, str] | None = None,
    meldung: str = "",
) -> str:
    """Erzeugt das maskierte Uebergabeprotokoll-Formular als HTML-Fragment.

    ``art`` ist eine Auswahl aus ``Einzug`` und ``Auszug``, ``bemerkungen``
    ein Textbereich. Alle anderen Protokollfelder werden als Eingaben gezeigt.
    """

    daten = {} if werte is None else werte
    art_wert = daten.get("art", "Einzug")
    if art_wert not in {"Einzug", "Auszug"}:
        art_wert = "Einzug"
    eingaben = []
    for feld in PROTOKOLL_FELDER:
        if feld == "art":
            eingaben.append(_auswahl("art", (("Einzug", "Einzug"), ("Auszug", "Auszug")), art_wert))
        elif feld == "bemerkungen":
            eingaben.append(_textbereich("bemerkungen", daten.get("bemerkungen", ""), 8))
        else:
            eingaben.append(_eingabe(feld, daten.get(feld, "")))
    format_wert = daten.get("format", "docx")
    if format_wert not in _FORMATE:
        format_wert = "docx"
    ziel_wert = daten.get("ziel", "lokal")
    if ziel_wert not in _ZIELE:
        ziel_wert = "lokal"
    return (
        _meldung(meldung)
        + '<form method="post" action="/protokoll"><table>'
        + _objekt_auswahl(objekte, daten.get("objekt_id", ""))
        + _vorlagen_auswahl(vorlagen, daten.get("vorlage", ""))
        + _auswahl("format", tuple((wert, wert) for wert in _FORMATE), format_wert)
        + _auswahl("ziel", tuple((wert, wert) for wert in _ZIELE), ziel_wert)
        + "".join(eingaben)
        + '<tr><td colspan="2"><button type="submit">Erstellen</button></td></tr>'
        "</table></form>"
    )


def _settings_eingabe(name: str, wert: object = "") -> str:
    return (
        f'<tr><th><label for="{name}">{name}</label></th><td>'
        f'<input id="{name}" name="{name}" type="text" value="{_maskiert(wert)}">'
        "</td></tr>"
    )


def formular_settings(
    einstellungen: dict[str, str],
    objekte: list[dict],
    meldung: str = "",
) -> str:
    """Erzeugt das maskierte Settings-Formular mit Einstellungen und Objekten."""

    eingaben = "".join(
        _settings_eingabe(feld, einstellungen.get(feld, "")) for feld in EINSTELLUNGEN_FELDER
    )
    objektzeilen = "".join(
        "<tr>"
        f"<td>{_maskiert(objekt.get('id', ''))}</td>"
        f"<td>{_maskiert(objekt.get('bezeichnung', ''))}</td>"
        f'<td><button type="submit" name="entfernen" value="{_maskiert(objekt.get("id", ""))}">'
        "Entfernen</button></td></tr>"
        for objekt in objekte
    )
    neu = "".join(
        _settings_eingabe(name)
        for name in (
            "neu_id",
            "neu_bezeichnung",
            "neu_miete_netto",
            "neu_nebenkosten",
            "neu_kaution",
        )
    )
    return (
        _meldung(meldung) + '<form method="post" action="/settings">'
        "<h2>Einstellungen</h2><table>" + eingaben + "</table><h2>Objekte</h2><table>"
        "<tr><th>id</th><th>Bezeichnung</th><th>Aktion</th></tr>"
        + objektzeilen
        + "</table><h2>Neues Objekt</h2><table>"
        + neu
        + '</table><button type="submit">Speichern</button></form>'
    )


def _werte_liste(werte: list[dict]) -> str:
    eintraege = []
    for eintrag in werte:
        feld = _text(eintrag.get("feld", ""))
        name = _ANZEIGENAMEN.get(feld, feld)
        herkunft = _text(eintrag.get("herkunft", ""))
        quelle = _QUELLEN.get(herkunft, herkunft)
        wert = _text(eintrag.get("wert", ""))
        eintraege.append(f"<li>{_maskiert(name)}: {_maskiert(wert)} (aus {_maskiert(quelle)})</li>")
    return '<ul class="werte">' + "".join(eintraege) + "</ul>"


def ergebnis(
    titel: str,
    text: str,
    dateien: list[str],
    hinweis: str = "",
    werte: list[dict] | None = None,
) -> str:
    """Erzeugt die maskierte Ergebnisseite mit Bericht, Werten, Dateien und Hinweis.

    ``werte`` enthaelt je Eintrag Feldname, Wert und Herkunft. Mit ``werte``
    erscheint eine Liste der eingesetzten Werte; ein leerer Bericht entfaellt
    dann. Ohne ``werte`` bleibt der Bericht wie bisher immer sichtbar.
    """

    dateiliste = ""
    if dateien:
        dateiliste = "<ul>" + "".join(f"<li>{_maskiert(datei)}</li>" for datei in dateien) + "</ul>"
    hinweistext = f'<p class="hinweis">{_maskiert(hinweis)}</p>' if hinweis else ""
    bericht = f"<pre>{_maskiert(text)}</pre>" if text or werte is None else ""
    werteliste = _werte_liste(werte) if werte is not None else ""
    return f"<h1>{_maskiert(titel)}</h1>{bericht}{werteliste}{dateiliste}{hinweistext}"
