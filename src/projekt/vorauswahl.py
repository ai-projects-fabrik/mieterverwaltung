"""Vorbelegte Werte fuer die Formulare Mietvertrag und Uebergabeprotokoll."""

from __future__ import annotations

from projekt.auftraege import FORMATE

_ARTEN = ("vertrag", "protokoll")
_ORTE = ("lokal", "drive")
_STANDARD_FORMAT = "docx+pdf"
_STANDARD_ZIEL = "drive"


def _pruefe_art(art: object) -> str:
    if not isinstance(art, str) or art not in _ARTEN:
        raise ValueError("Feld 'art' muss 'vertrag' oder 'protokoll' sein")
    return art


def _pruefe_objekte(objekte: object) -> list[dict]:
    if not isinstance(objekte, list):
        raise ValueError("Feld 'objekte' muss eine Liste sein")
    for objekt in objekte:
        if not isinstance(objekt, dict):
            raise ValueError("Feld 'objekte' muss Objekte als dict enthalten")
    return objekte


def _pruefe_vorlagen(vorlagen: object) -> dict[str, list[str]]:
    if not isinstance(vorlagen, dict):
        raise ValueError("Feld 'vorlagen' muss ein dict sein")

    geprueft: dict[str, list[str]] = {}
    for ort in _ORTE:
        namen = vorlagen.get(ort, [])
        if not isinstance(namen, list):
            raise ValueError(f"Feld 'vorlagen_{ort}' muss eine Liste sein")
        if any(not isinstance(name, str) for name in namen):
            raise ValueError(f"Feld 'vorlagen_{ort}' muss Namen als Text enthalten")
        geprueft[ort] = namen
    return geprueft


def _pruefe_letzte(letzte: object) -> dict:
    if not isinstance(letzte, dict):
        raise ValueError("Feld 'letzte' muss ein dict sein")
    return letzte


def _vorlagenliste(vorlagen: dict[str, list[str]]) -> list[str]:
    return [f"{ort}:{name}" for ort in _ORTE for name in vorlagen[ort]]


def _objekt_id(objekte: list[dict], letzte: dict) -> str:
    gewaehlt = letzte.get("objekt_id")
    if isinstance(gewaehlt, str) and any(objekt.get("id") == gewaehlt for objekt in objekte):
        return gewaehlt
    if not objekte:
        return ""
    erste_id = objekte[0].get("id")
    return erste_id if isinstance(erste_id, str) else ""


def _vorlage(art: str, vorlagen: dict[str, list[str]], letzte: dict) -> str:
    verfuegbar = _vorlagenliste(vorlagen)
    gewaehlt = letzte.get(f"{art}_vorlage")
    if isinstance(gewaehlt, str) and gewaehlt in verfuegbar:
        return gewaehlt

    for eintrag in verfuegbar:
        if art in eintrag.split(":", 1)[1].casefold():
            return eintrag
    return verfuegbar[0] if verfuegbar else ""


def _format(letzte: dict) -> str:
    gewaehlt = letzte.get("format")
    return gewaehlt if isinstance(gewaehlt, str) and gewaehlt in FORMATE else _STANDARD_FORMAT


def _ziel(letzte: dict) -> str:
    gewaehlt = letzte.get("ziel")
    return gewaehlt if gewaehlt in _ORTE else _STANDARD_ZIEL


def vorauswahl(
    art: str,
    objekte: list[dict],
    vorlagen: dict[str, list[str]],
    letzte: dict[str, str],
) -> dict[str, str]:
    """Bestimmt die vorbelegten Werte eines Formulars.

    Die letzte Auswahl gewinnt nur, solange ihre Werte noch gueltig sind:
    ein vorhandenes Objekt, eine verfuegbare Vorlage, ein Wert aus
    :data:`projekt.auftraege.FORMATE` und das Ziel ``lokal`` oder ``drive``.
    Sonst gelten Standardwerte; die erste Vorlage mit ``art`` im Namen wird
    bevorzugt. Ohne Objekte beziehungsweise Vorlagen sind die Werte leer.
    """

    art = _pruefe_art(art)
    objekte = _pruefe_objekte(objekte)
    vorlagen = _pruefe_vorlagen(vorlagen)
    letzte = _pruefe_letzte(letzte)

    return {
        "objekt_id": _objekt_id(objekte, letzte),
        "vorlage": _vorlage(art, vorlagen, letzte),
        "format": _format(letzte),
        "ziel": _ziel(letzte),
    }


def merke(art: str, form: dict[str, str]) -> dict[str, str]:
    """Waehlt die aus einem Formular zu merkenden Werte aus.

    Gemerkt werden nur nicht leere Texte fuer ``objekt_id``, ``format``,
    ``ziel`` und ``vorlage``; letztere unter dem Namen ``<art>_vorlage``.
    Alle uebrigen Formularfelder, insbesondere Mieterdaten, werden ignoriert.
    """

    art = _pruefe_art(art)
    if not isinstance(form, dict):
        raise ValueError("Feld 'form' muss ein dict sein")

    auswahl: dict[str, str] = {}
    for quelle, ziel in (
        ("objekt_id", "objekt_id"),
        ("vorlage", f"{art}_vorlage"),
        ("format", "format"),
        ("ziel", "ziel"),
    ):
        if quelle not in form:
            continue
        wert = form[quelle]
        if not isinstance(wert, str):
            raise ValueError(f"Feld '{quelle}' muss als Text uebergeben werden")
        text = wert.strip()
        if text:
            auswahl[ziel] = text
    return auswahl
