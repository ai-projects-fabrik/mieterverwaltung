"""HTML fuer Google-Anmeldung und Google-Drive-Auswahl ohne Netzwerk.

Die Funktionen erzeugen nur maskierte HTML-Fragmente. Den Transport und die
Anmeldung uebernehmen andere Module; hier findet kein Datei- oder Netzwerk-
zugriff statt.
"""

from __future__ import annotations

from html import escape

from projekt.gdrive import passt
from projekt.gdrivenav import GETEILT, WURZEL, suche_in

SEITEN: dict[str, str] = {"vertrag": "/mietvertrag", "protokoll": "/protokoll"}
ZUSTAENDE: tuple[str, ...] = (
    "keine_datei",
    "getrennt",
    "laeuft",
    "abgebrochen",
    "verbunden",
)

_AUSWAHL = "/google/auswahl"


def _maskiert(wert: object) -> str:
    return escape(str(wert))


def _text(wert: object, feld: str) -> str:
    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss als Text uebergeben werden")
    return wert


def _seite(art: object) -> str:
    if not isinstance(art, str) or art not in SEITEN:
        raise ValueError("Feld 'art' muss 'vertrag' oder 'protokoll' sein")
    return art


def _hinweis(text: str) -> str:
    return f'<p class="hinweis">{_maskiert(text)}</p>' if text else ""


def _versteckt(name: str, wert: str) -> str:
    return f'<input type="hidden" name="{name}" value="{_maskiert(wert)}">'


def _knopf(text: str) -> str:
    return f'<button type="submit">{_maskiert(text)}</button>'


def _link(text: str, ziel: str) -> str:
    return f'<a href="{_maskiert(ziel)}">{_maskiert(text)}</a>'


def _anmeldeformular(art: str) -> str:
    return (
        '<form method="post" action="/google/anmelden">'
        + _versteckt("art", art)
        + f"<p>{_knopf('Bei Google anmelden')}</p></form>"
    )


def google_block(
    art: str,
    zustand: str,
    konto: str = "",
    meldung: str = "",
) -> str:
    """Erzeugt den maskierten Google-Block fuer ein Formular.

    ``art`` ist ``vertrag`` oder ``protokoll``, ``zustand`` einer der Werte aus
    :data:`ZUSTAENDE`. Die Anmeldung startet nur ueber den Knopf im Block; bei
    ``laeuft`` gibt es nur einen Link zurueck zum Formular. ``konto`` und
    ``meldung`` erscheinen maskiert.
    """

    seite = _seite(art)
    if not isinstance(zustand, str) or zustand not in ZUSTAENDE:
        raise ValueError(f"Feld 'zustand' muss einer von {ZUSTAENDE} sein")
    konto = _text(konto, "konto")
    meldung = _text(meldung, "meldung")

    teile = [_hinweis(meldung)]
    if zustand in ("getrennt", "abgebrochen"):
        if zustand == "abgebrochen":
            teile.append('<p class="hinweis">Anmeldung abgebrochen - erneut versuchen</p>')
        teile.append(_anmeldeformular(seite))
    elif zustand == "laeuft":
        teile.append(
            "<p>Anmeldung im Browser laeuft. Bitte dort zustimmen und danach "
            f"{_link('Seite neu laden', SEITEN[seite])}.</p>"
        )
    elif zustand == "verbunden":
        teile.append(f"<p>Verbunden als {_maskiert(konto)}</p>")
        teile.append(
            "<p>"
            + _link(
                "Vorlage in Google Drive aussuchen",
                f"{_AUSWAHL}?art={seite}",
            )
            + "</p>"
        )
        teile.append(
            '<form method="post" action="/google/abmelden">'
            + _versteckt("art", seite)
            + f"<p>{_knopf('Abmelden')}</p></form>"
        )

    return '<div class="google">' + "".join(teile) + "</div>"


def _pfad(pfad: object) -> list[dict]:
    if not isinstance(pfad, list) or not pfad:
        raise ValueError("Feld 'pfad' muss eine nicht leere Liste geoeffneter Ordner sein")
    geprueft: list[dict] = []
    for nummer, eintrag in enumerate(pfad, start=1):
        if not isinstance(eintrag, dict):
            raise ValueError(f"Feld 'pfad': Ordner {nummer} ist kein dict")
        kennung = eintrag.get("id")
        name = eintrag.get("name")
        if not isinstance(kennung, str) or not kennung.strip():
            raise ValueError(f"Feld 'pfad': Ordner {nummer} hat keine gueltige id")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Feld 'pfad': Ordner {nummer} hat keinen gueltigen Namen")
        geprueft.append(eintrag)
    return geprueft


def _liste(wert: object, feld: str) -> list:
    if not isinstance(wert, list):
        raise ValueError(f"Feld '{feld}' muss eine Liste sein")
    return wert


def _krumen(art: str, pfad: list[dict]) -> str:
    teile: list[str] = []
    for nummer, eintrag in enumerate(pfad):
        name = eintrag["name"]
        if nummer == len(pfad) - 1:
            teile.append(f"<strong>{_maskiert(name)}</strong>")
        else:
            ziel = f"{_AUSWAHL}?art={art}&ordner={eintrag['id']}"
            teile.append(_link(name, ziel))
    return '<p class="pfad">' + " / ".join(teile) + "</p>"


def _unterordner(art: str, ordner: list) -> str:
    links: list[str] = []
    for eintrag in ordner:
        if not isinstance(eintrag, dict):
            continue
        kennung = eintrag.get("id")
        name = eintrag.get("name")
        if not isinstance(kennung, str) or not kennung.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        ziel = f"{_AUSWAHL}?art={art}&ordner={kennung}"
        links.append("<li>" + _link(f"Ordner: {name}", ziel) + "</li>")
    return "<ul>" + "".join(links) + "</ul>" if links else ""


def _suchformular(art: str, ordner_id: str, suche: str, alle: bool) -> str:
    geprueft = " checked" if alle else ""
    return (
        '<form method="get" action="/google/auswahl">'
        + _versteckt("art", art)
        + _versteckt("ordner", ordner_id)
        + '<p><label for="q">Suche</label> '
        + f'<input id="q" name="q" type="search" value="{_maskiert(suche)}"></p>'
        + '<p><label><input type="checkbox" name="alle" value="1"'
        + geprueft
        + "> Alle Dateien anzeigen</label></p>"
        + _knopf("Suchen")
        + "</form>"
    )


def _dateien(art: str, dateien: list, suche: str, alle: bool) -> tuple[str, int]:
    gefiltert = suche_in(dateien, suche)
    sichtbar: list[dict] = []
    for eintrag in gefiltert:
        if not isinstance(eintrag, dict):
            continue
        name = eintrag.get("name")
        if not isinstance(name, str):
            continue
        if alle or passt(name):
            sichtbar.append(eintrag)

    teile: list[str] = []
    for eintrag in sichtbar:
        teile.append(f"<p>{_maskiert(eintrag['name'])}</p>")
        kennung = eintrag.get("id")
        if isinstance(kennung, str) and kennung:
            teile.append(
                '<form method="post" action="/google/waehlen">'
                + _versteckt("art", art)
                + _versteckt("id", kennung)
                + f"<p>{_knopf('Waehlen')}</p></form>"
            )
    return "".join(teile), len(sichtbar)


def _leer(dateien: list, suche: str, alle: bool) -> str:
    if suche.strip():
        return f'<p class="hinweis">Keine Dateien mit "{_maskiert(suche)}" gefunden.</p>'
    if dateien and not alle:
        return (
            '<p class="hinweis">Keine passenden Dateien. Angezeigt werden nur Dateien mit '
            'Vertrag oder Protokoll im Namen. Mit "Alle Dateien anzeigen" erscheinen alle.</p>'
        )
    return '<p class="hinweis">Keine Dateien in diesem Ordner.</p>'


def formular_auswahl(
    art: str,
    pfad: list[dict],
    ordner: list[dict],
    dateien: list[dict],
    suche: str = "",
    alle: bool = False,
    meldung: str = "",
) -> str:
    """Erzeugt die maskierte Seite zum Navigieren in Google Drive.

    ``pfad`` ist die nicht leere Liste der geoeffneten Ordner; der letzte ist
    der aktuelle. ``ordner`` sind Unterordner, ``dateien`` die Eintraege im
    aktuellen Ordner. Ohne ``alle`` erscheinen nur Namen mit einem Stichwort
    aus :data:`projekt.gdrive.STICHWORTE`; ``suche`` filtert zusaetzlich nach
    einem Namensteil. Alle Werte werden HTML-maskiert ausgegeben.
    """

    seite = _seite(art)
    geprueft_pfad = _pfad(pfad)
    geprueft_ordner = _liste(ordner, "ordner")
    geprueft_dateien = _liste(dateien, "dateien")
    geprueft_suche = _text(suche, "suche")
    if not isinstance(alle, bool):
        raise ValueError("Feld 'alle' muss wahr oder falsch sein")
    geprueft_meldung = _text(meldung, "meldung")

    aktuell = geprueft_pfad[-1]
    teile = [
        _hinweis(geprueft_meldung),
        f"<h2>{_maskiert(aktuell['name'])}</h2>",
        "<nav>"
        + _link("Meine Ablage", f"{_AUSWAHL}?art={seite}&ordner={WURZEL}")
        + _link("Mit mir geteilt", f"{_AUSWAHL}?art={seite}&ordner={GETEILT}")
        + _link("Zurueck zum Formular", SEITEN[seite])
        + "</nav>",
        _krumen(seite, geprueft_pfad),
    ]

    unterordner = _unterordner(seite, geprueft_ordner)
    if unterordner:
        teile.append(unterordner)

    teile.append(_suchformular(seite, aktuell["id"], geprueft_suche, alle))

    inhalt, anzahl = _dateien(seite, geprueft_dateien, geprueft_suche, alle)
    if anzahl:
        teile.append(inhalt)
    else:
        teile.append(_leer(geprueft_dateien, geprueft_suche, alle))

    return "".join(teile)
