"""Reine HTML-Erzeugung fuer Google-Anmeldung und Drive-Auswahl."""

from __future__ import annotations

from html import escape
from urllib.parse import quote

from projekt.gdrive import passt
from projekt.gdrivenav import GETEILT, WURZEL, suche_in

SEITEN = {"vertrag": "/mietvertrag", "protokoll": "/protokoll"}
ZUSTAENDE = ("keine_datei", "getrennt", "laeuft", "abgebrochen", "verbunden")


def _text(wert: object, feld: str) -> str:
    if wert is None:
        return ""
    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss als Text uebergeben werden")
    return wert


def _maskiert(wert: object) -> str:
    return escape(_text(wert, "wert"), quote=True)


def _art(art: object) -> str:
    if not isinstance(art, str) or art not in SEITEN:
        raise ValueError(f"Feld 'art' muss 'vertrag' oder 'protokoll' sein: {art}")
    return art


def _link(ziel: str, bezeichnung: str) -> str:
    return f'<a href="{_maskiert(ziel)}">{_maskiert(bezeichnung)}</a>'


def _versteckt(name: str, wert: str) -> str:
    return f'<input type="hidden" name="{name}" value="{_maskiert(wert)}">'


def _auswahl_link(art: str, ordner_id: str) -> str:
    return f"/google/auswahl?art={quote(art, safe='')}&ordner={quote(ordner_id, safe='')}"


def _anmeldeformular(art: str) -> str:
    return (
        '<form method="post" action="/google/anmelden">'
        + _versteckt("art", art)
        + '<button type="submit">Bei Google anmelden</button></form>'
    )


def google_block(art: str, zustand: str, konto: str = "", meldung: str = "") -> str:
    """Erzeugt den maskierten Google-Block an der Vorlagenwahl.

    Die Anmeldung wird nur als Formular angeboten und nie automatisch
    gestartet. ``art`` waehlt Mietvertrag oder Uebergabeprotokoll, ``zustand``
    den sichtbaren Anmeldezustand. Eine nicht leere ``meldung`` erscheint in
    jedem Zustand als Hinweis.
    """

    art = _art(art)
    if not isinstance(zustand, str) or zustand not in ZUSTAENDE:
        raise ValueError(f"Feld 'zustand' ist unbekannt: {zustand}")
    konto = _text(konto, "konto")
    meldung = _text(meldung, "meldung")

    teile = ['<div class="google">']
    if meldung:
        teile.append(f'<p class="hinweis">{_maskiert(meldung)}</p>')

    if zustand in ("getrennt", "abgebrochen"):
        if zustand == "abgebrochen":
            teile.append('<p class="hinweis">Anmeldung abgebrochen - erneut versuchen</p>')
        teile.append(_anmeldeformular(art))
    elif zustand == "laeuft":
        teile.append(
            "<p>Anmeldung im Browser laeuft. Bitte dort zustimmen und danach "
            + _link(SEITEN[art], "Seite neu laden")
            + "</p>"
        )
    elif zustand == "verbunden":
        teile.append(f"<p>Verbunden als {_maskiert(konto)}</p>")
        teile.append(
            "<p>"
            + _link(
                f"/google/auswahl?art={quote(art, safe='')}",
                "Vorlage in Google Drive aussuchen",
            )
            + "</p>"
        )
        teile.append(
            '<form method="post" action="/google/abmelden">'
            + _versteckt("art", art)
            + '<button type="submit">Abmelden</button></form>'
        )

    teile.append("</div>")
    return "".join(teile)


def _pfad_pruefen(pfad: object) -> list[dict]:
    if not isinstance(pfad, list) or not pfad:
        raise ValueError("Feld 'pfad' muss eine nicht leere Liste sein")
    geprueft: list[dict] = []
    for nummer, eintrag in enumerate(pfad, start=1):
        if not isinstance(eintrag, dict):
            raise ValueError(f"Feld 'pfad': Eintrag {nummer} ist kein dict")
        kennung = eintrag.get("id")
        name = eintrag.get("name")
        if not isinstance(kennung, str) or not kennung.strip():
            raise ValueError(f"Feld 'pfad': Eintrag {nummer} hat keine id")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Feld 'pfad': Eintrag {nummer} hat keinen Namen")
        geprueft.append({"id": kennung, "name": name})
    return geprueft


def _eintraege_pruefen(eintraege: object, feld: str) -> list[dict]:
    if not isinstance(eintraege, list):
        raise ValueError(f"Feld '{feld}' muss eine Liste sein")
    geprueft: list[dict] = []
    for nummer, eintrag in enumerate(eintraege, start=1):
        if not isinstance(eintrag, dict):
            raise ValueError(f"Feld '{feld}': Eintrag {nummer} ist kein dict")
        kennung = eintrag.get("id")
        name = eintrag.get("name")
        if not isinstance(kennung, str) or not kennung.strip():
            raise ValueError(f"Feld '{feld}': Eintrag {nummer} hat keine id")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Feld '{feld}': Eintrag {nummer} hat keinen Namen")
        geprueft.append(eintrag)
    return geprueft


def _krumen(art: str, pfad: list[dict]) -> str:
    teile: list[str] = []
    for eintrag in pfad[:-1]:
        teile.append(_link(_auswahl_link(art, eintrag["id"]), eintrag["name"]))
    teile.append(f"<strong>{_maskiert(pfad[-1]['name'])}</strong>")
    return '<p class="krumen">' + " &raquo; ".join(teile) + "</p>"


def _suchformular(art: str, ordner_id: str, suche: str, alle: bool) -> str:
    geprueft = " checked" if alle else ""
    return (
        '<form method="get" action="/google/auswahl">'
        + _versteckt("art", art)
        + _versteckt("ordner", ordner_id)
        + '<label>Name <input type="text" name="q" value="'
        + _maskiert(suche)
        + '"></label> '
        + '<label><input type="checkbox" name="alle" value="1"'
        + geprueft
        + "> Alle Dateien anzeigen</label> "
        + '<button type="submit">Suchen</button></form>'
    )


def _dateiformular(art: str, datei: dict) -> str:
    return (
        '<form method="post" action="/google/waehlen">'
        + _versteckt("art", art)
        + _versteckt("id", datei["id"])
        + f"<span>{_maskiert(datei['name'])}</span> "
        + '<button type="submit">Waehlen</button></form>'
    )


def formular_auswahl(
    art: str,
    pfad: list[dict],
    ordner: list[dict],
    dateien: list[dict],
    suche: str = "",
    alle: bool = False,
    meldung: str = "",
) -> str:
    """Erzeugt die maskierte Seite zum Navigieren durch Google Drive.

    ``pfad`` enthaelt die geoeffneten Ordner; der letzte Eintrag ist der
    aktuelle Ordner. ``ordner`` und ``dateien`` werden als Links beziehungsweise
    Auswahlformulare dargestellt. Ohne ``alle`` erscheinen nur Dateinamen, die
    zu Vertrag oder Protokoll passen. ``suche`` filtert zusaetzlich nach einem
    Textstueck im Namen.
    """

    art = _art(art)
    pfad = _pfad_pruefen(pfad)
    ordner = _eintraege_pruefen(ordner, "ordner")
    dateien = _eintraege_pruefen(dateien, "dateien")
    suche = _text(suche, "suche")
    meldung = _text(meldung, "meldung")
    if not isinstance(alle, bool):
        raise ValueError("Feld 'alle' muss ein Wahrheitswert sein")

    aktuell = pfad[-1]
    sichtbar = suche_in(dateien, suche)
    if not alle:
        sichtbar = [datei for datei in sichtbar if passt(datei["name"])]

    teile = [
        "<h1>Vorlage in Google Drive aussuchen</h1>",
        '<p class="google-nav">',
        _link(_auswahl_link(art, WURZEL), "Meine Ablage"),
        " ",
        _link(_auswahl_link(art, GETEILT), "Mit mir geteilt"),
        " ",
        _link(SEITEN[art], "Zurueck zum Formular"),
        "</p>",
        _krumen(art, pfad),
    ]
    if meldung:
        teile.append(f'<p class="hinweis">{_maskiert(meldung)}</p>')
    teile.append(_suchformular(art, aktuell["id"], suche, alle))

    if ordner:
        teile.append("<ul>")
        for eintrag in ordner:
            teile.append(
                "<li>"
                + _link(_auswahl_link(art, eintrag["id"]), f"Ordner: {eintrag['name']}")
                + "</li>"
            )
        teile.append("</ul>")

    if sichtbar:
        teile.append("<ul>")
        for datei in sichtbar:
            teile.append("<li>" + _dateiformular(art, datei) + "</li>")
        teile.append("</ul>")
    elif suche.strip():
        teile.append(
            '<p class="hinweis">Keine Dateien mit "' + _maskiert(suche.strip()) + '" gefunden.</p>'
        )
    elif dateien and not alle:
        teile.append(
            '<p class="hinweis">Nur Dateien mit Vertrag oder Protokoll im Namen werden '
            "angezeigt.</p>"
        )
    else:
        teile.append('<p class="hinweis">Keine Dateien in diesem Ordner.</p>')

    return "".join(teile)
