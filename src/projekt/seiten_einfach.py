"""Reine HTML-Erzeugung fuer die vereinfachte Oberflaeche."""

from __future__ import annotations

from html import escape

from projekt.objekttabelle import SPALTEN

TABS_EINFACH: tuple[tuple[str, str], ...] = (
    ("mietvertrag", "Mietvertrag"),
    ("protokoll", "Übergabeprotokoll"),
    ("objekte", "Objekte"),
    ("settings", "Einstellungen"),
)

_STIL = (
    "nav{border-bottom:1px solid #ccc;margin-bottom:1em}"
    "nav a{display:inline-block;margin:0 .25em -1px 0;padding:.5em 1.2em;border:1px solid #ccc;"
    "border-radius:.4em .4em 0 0;background:#f3f3f3;color:#333;text-decoration:none}"
    "nav a[aria-current]{background:#fff;border-bottom:1px solid #fff;font-weight:bold}"
    ".hinweis{color:#8a4b00;margin:.3em 0}"
)
_VORLAGEN_ORTE = (
    ("lokal", "Festplatte"),
    ("drive", "Google Drive"),
    ("google", "Google Docs / Drive (online)"),
)
_FORMATE = (("docx+pdf", "Word + PDF"), ("docx", "Word"), ("pdf", "PDF"))
_ZIELE = (("drive", "Google Drive"), ("lokal", "Lokaler Ordner"))
_ARTEN = (("Einzug", "Einzug"), ("Auszug", "Auszug"))


def _text(wert: object) -> str:
    return "" if wert is None else str(wert)


def _maskiert(wert: object) -> str:
    return escape(_text(wert))


def _meldung(meldung: object) -> str:
    return f'<p class="meldung">{_maskiert(meldung)}</p>' if meldung else ""


def _zeile(name: str, beschriftung: str, inhalt: str) -> str:
    return (
        f'<tr><th><label for="{name}">{_maskiert(beschriftung)}</label></th><td>{inhalt}</td></tr>'
    )


def _eingabe(name: str, beschriftung: str, wert: object = "") -> str:
    return _zeile(
        name,
        beschriftung,
        f'<input id="{name}" name="{name}" type="text" value="{_maskiert(wert)}">',
    )


def _textbereich(name: str, beschriftung: str, wert: object = "", zeilen: int = 4) -> str:
    return _zeile(
        name,
        beschriftung,
        f'<textarea id="{name}" name="{name}" rows="{zeilen}">{_maskiert(wert)}</textarea>',
    )


def _option(wert: object, beschriftung: object, gewaehlt: str) -> str:
    wert_text = _text(wert)
    ausgewaehlt = " selected" if wert_text == gewaehlt else ""
    return f'<option value="{_maskiert(wert_text)}"{ausgewaehlt}>{_maskiert(beschriftung)}</option>'


def _auswahl(
    name: str,
    beschriftung: str,
    optionen: tuple[tuple[object, object], ...] | list[tuple[object, object]],
    gewaehlt: object,
) -> str:
    auswahl = _text(gewaehlt)
    inhalt = "".join(_option(wert, text, auswahl) for wert, text in optionen)
    return _zeile(
        name,
        beschriftung,
        f'<select id="{name}" name="{name}">{inhalt}</select>',
    )


def _werte(werte: dict[str, str] | None) -> dict[str, str]:
    if werte is None:
        return {}
    if not isinstance(werte, dict):
        raise ValueError("Feld 'werte' muss ein dict sein")
    return werte


def _listenwert(wert: object, feld: str) -> list:
    if not isinstance(wert, list):
        raise ValueError(f"Feld '{feld}' muss eine Liste sein")
    return wert


def _vorlagen_auswahl(
    vorlagen: dict[str, list[str]], gewaehlt: object, hinweise: list[str] | None = None
) -> str:
    if not isinstance(vorlagen, dict):
        raise ValueError("Feld 'vorlagen' muss ein dict sein")

    auswahl = _text(gewaehlt)
    gruppen = []
    for ort, beschriftung in _VORLAGEN_ORTE:
        namen = _listenwert(vorlagen.get(ort, []), f"vorlagen.{ort}")
        if not namen:
            continue
        if ort == "google":
            optionen = "".join(
                _option(f"google:{datei.get('id', '')}", datei.get("name", ""), auswahl)
                for datei in namen
                if isinstance(datei, dict)
            )
        else:
            optionen = "".join(_option(f"{ort}:{name}", name, auswahl) for name in namen)
        gruppen.append(f'<optgroup label="{_maskiert(beschriftung)}">{optionen}</optgroup>')
    meldungen = "".join(f'<p class="hinweis">{_maskiert(text)}</p>' for text in hinweise or [])
    return _zeile(
        "vorlage",
        "Vorlage",
        '<select id="vorlage" name="vorlage">' + "".join(gruppen) + "</select>" + meldungen,
    )


def _objekt_auswahl(objekte: list[dict], gewaehlt: object) -> str:
    optionen: list[tuple[object, object]] = []
    for nummer, objekt in enumerate(objekte, start=1):
        if not isinstance(objekt, dict):
            raise ValueError(f"Feld 'objekte': Eintrag {nummer} ist kein dict")
        optionen.append((objekt.get("id", ""), objekt.get("bezeichnung", "")))
    return _auswahl("objekt_id", "Objekt", optionen, gewaehlt)


def _wahl(werte: dict[str, str], feld: str, standard: str, erlaubt: set[str]) -> str:
    wert = _text(werte.get(feld, standard))
    return wert if wert in erlaubt else standard


def _ohne_objekte(meldung: object) -> str:
    return (
        _meldung(meldung) + '<p class="hinweis">Bitte zuerst unter <a href="/objekte">Objekte</a> '
        "ein Objekt anlegen.</p>"
    )


def rahmen_einfach(aktiv: str, inhalt: str) -> str:
    """Setzt Inhalt in ein vollstaendiges HTML5-Dokument mit Tab-Navigation.

    ``aktiv`` muss ein Schluessel aus :data:`TABS_EINFACH` sein. Der aktive
    Link traegt genau einmal ``aria-current="page"``. Bei einem unbekannten
    Tab entsteht ein ValueError mit dem Feldnamen ``aktiv``.
    """

    labels = dict(TABS_EINFACH)
    if not isinstance(aktiv, str) or aktiv not in labels:
        raise ValueError(f"Feld 'aktiv' ist unbekannt: {aktiv}")

    links = []
    for tab, beschriftung in TABS_EINFACH:
        aktuell = ' aria-current="page"' if tab == aktiv else ""
        links.append(f'<a href="/{tab}"{aktuell}>{escape(beschriftung)}</a>')
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        f"<title>Mietverwaltung</title><style>{_STIL}</style></head><body>"
        f"<nav>{''.join(links)}</nav><main>{inhalt}</main></body></html>"
    )


def formular_ordner(drive: str, lokal: str, meldung: str = "") -> str:
    """Erzeugt das maskierte Formular fuer die beiden Basisordner.

    ``drive`` und ``lokal`` belegen die Textfelder vor. ``meldung`` erscheint
    vor dem Formular. Die abgeleiteten Unterordner legt das Programm spaeter
    automatisch an.
    """

    return (
        _meldung(meldung)
        + '<form method="post" action="/settings"><table>'
        + _eingabe("drive_ordner", "Google-Drive-Ordner", drive)
        + _eingabe("lokaler_ordner", "Lokaler Ordner", lokal)
        + "</table><p>Die Unterordner werden automatisch angelegt.</p>"
        '<p><button type="submit">Speichern</button></p></form>'
    )


def formular_objekttabelle(zeilen: list[dict], meldung: str = "") -> str:
    """Erzeugt die maskierte Objekt-Tabelle mit zwei zusaetzlichen Leerzeilen.

    Je uebergebener Zeile und je einer der beiden Leerzeilen entstehen Felder
    ``zeile_<n>_<spalte>`` sowie eine versteckte id. Leeren aller sichtbaren
    Felder entfernt das Objekt beim Absenden.
    """

    daten = _listenwert(zeilen, "zeilen")
    alle_zeilen: list[dict] = []
    for nummer, zeile in enumerate(daten, start=1):
        if not isinstance(zeile, dict):
            raise ValueError(f"Feld 'zeilen': Zeile {nummer} ist kein dict")
        alle_zeilen.append(zeile)
    alle_zeilen.extend(({}, {}))

    kopf = "".join(f"<th>{_maskiert(beschriftung)}</th>" for _, beschriftung in SPALTEN)
    koerper = []
    for nummer, zeile in enumerate(alle_zeilen):
        zellen = []
        for index, (feldname, beschriftung) in enumerate(SPALTEN):
            feld = f"zeile_{nummer}_{feldname}"
            if index == 0:
                zellen.append(
                    f'<td><input type="hidden" name="zeile_{nummer}_id" '
                    f'value="{_maskiert(zeile.get("id", ""))}">'
                    f'<input id="{feld}" name="{feld}" type="text" '
                    f'aria-label="{_maskiert(beschriftung)}" '
                    f'value="{_maskiert(zeile.get(feldname, ""))}"></td>'
                )
            else:
                zellen.append(
                    f'<td><input id="{feld}" name="{feld}" type="text" '
                    f'aria-label="{_maskiert(beschriftung)}" '
                    f'value="{_maskiert(zeile.get(feldname, ""))}"></td>'
                )
        koerper.append(f"<tr>{''.join(zellen)}</tr>")

    return (
        _meldung(meldung)
        + '<form method="post" action="/objekte"><table><thead><tr>'
        + kopf
        + "</tr></thead><tbody>"
        + "".join(koerper)
        + "</tbody></table><p>Leeren aller Felder einer Zeile entfernt das Objekt.</p>"
        '<p><button type="submit">Speichern</button></p></form>'
    )


def _basisformular(
    post: str,
    objekte: list[dict],
    vorlagen: dict[str, list[str]],
    werte: dict[str, str] | None,
    meldung: str,
    hinweise: list[str] | None = None,
) -> tuple[str, dict[str, str], str, str] | None:
    daten = _werte(werte)
    if not isinstance(objekte, list):
        raise ValueError("Feld 'objekte' muss eine Liste sein")
    if not objekte:
        return None

    format_wert = _wahl(daten, "format", "docx+pdf", {wert for wert, _ in _FORMATE})
    ziel_wert = _wahl(daten, "ziel", "drive", {wert for wert, _ in _ZIELE})
    anfang = (
        _meldung(meldung)
        + f'<form method="post" action="/{post}"><table>'
        + _objekt_auswahl(objekte, daten.get("objekt_id", ""))
        + _vorlagen_auswahl(vorlagen, daten.get("vorlage", ""), hinweise)
        + _eingabe(
            "mieter_name",
            "Name der Mieterin / des Mieters",
            daten.get("mieter_name", ""),
        )
    )
    return anfang, daten, format_wert, ziel_wert


def _format_und_ziel(format_wert: str, ziel_wert: str) -> str:
    return _auswahl("format", "Dateiformat", _FORMATE, format_wert) + _auswahl(
        "ziel", "Speichern in", _ZIELE, ziel_wert
    )


def _formular_vertrag(
    objekte: list[dict],
    vorlagen: dict[str, list[str]],
    werte: dict[str, str] | None,
    meldung: str,
    hinweise: list[str] | None = None,
) -> str:
    basis = _basisformular("mietvertrag", objekte, vorlagen, werte, meldung, hinweise)
    if basis is None:
        return _ohne_objekte(meldung)

    anfang, daten, format_wert, ziel_wert = basis
    return (
        anfang
        + _eingabe("mietbeginn", "Mietbeginn", daten.get("mietbeginn", ""))
        + _textbereich("anfrage", "Änderungen (optional)", daten.get("anfrage", ""), 8)
        + _format_und_ziel(format_wert, ziel_wert)
        + '</table><p><button type="submit">Erstellen</button></p></form>'
    )


def formular_vertrag(
    objekte: list[dict],
    vorlagen: dict[str, list[str]],
    werte: dict[str, str] | None = None,
    meldung: str = "",
    vorlagen_hinweise: list[str] | None = None,
) -> str:
    """Erzeugt das maskierte Mietvertragsformular mit den noetigen Feldern.

    Betraege stammen aus dem gewaehlten Objekt und erscheinen deshalb nicht im
    Formular. ``werte`` belegt Eingaben und Auswahlen vor; ungültige Werte fuer
    Format und Ziel fallen auf ``docx+pdf`` und ``drive`` zurueck.
    ``vorlagen_hinweise`` erscheinen als Texte unter dem Vorlagen-Dropdown;
    leere Vorlagengruppen werden nicht angezeigt. Ohne Objekte
    entsteht statt des Formulars nur ein Hinweis.
    """

    return _formular_vertrag(objekte, vorlagen, werte, meldung, vorlagen_hinweise)


def _formular_uebergabe(
    objekte: list[dict],
    vorlagen: dict[str, list[str]],
    werte: dict[str, str] | None,
    meldung: str,
    hinweise: list[str] | None = None,
) -> str:
    basis = _basisformular("protokoll", objekte, vorlagen, werte, meldung, hinweise)
    if basis is None:
        return _ohne_objekte(meldung)

    anfang, daten, format_wert, ziel_wert = basis
    art = _wahl(daten, "art", "Einzug", {wert for wert, _ in _ARTEN})
    return (
        anfang
        + _eingabe("uebergabedatum", "Übergabedatum", daten.get("uebergabedatum", ""))
        + _auswahl("art", "Art", _ARTEN, art)
        + _eingabe("zaehler_strom", "Zählerstand Strom", daten.get("zaehler_strom", ""))
        + _eingabe("zaehler_wasser", "Zählerstand Wasser", daten.get("zaehler_wasser", ""))
        + _eingabe("schluessel_anzahl", "Anzahl Schlüssel", daten.get("schluessel_anzahl", ""))
        + _textbereich("bemerkungen", "Bemerkungen", daten.get("bemerkungen", ""))
        + _format_und_ziel(format_wert, ziel_wert)
        + '</table><p><button type="submit">Erstellen</button></p></form>'
    )


def formular_uebergabe(
    objekte: list[dict],
    vorlagen: dict[str, list[str]],
    werte: dict[str, str] | None = None,
    meldung: str = "",
    vorlagen_hinweise: list[str] | None = None,
) -> str:
    """Erzeugt das maskierte Formular fuer das Uebergabeprotokoll.

    ``werte`` belegt Eingaben und Auswahlen vor. Die Art faellt bei fehlendem
    oder ungueltigem Wert auf ``Einzug`` zurueck. Ohne Objekte entsteht statt
    des Formulars nur ein Hinweis.
    """

    return _formular_uebergabe(objekte, vorlagen, werte, meldung, vorlagen_hinweise)
