"""Felder und Pruefung fuer das Uebergabeprotokoll."""

from __future__ import annotations

import re
from datetime import date

from projekt.felder import normalisiere

PROTOKOLL_FELDER: tuple[str, ...] = (
    "mieter_name",
    "objekt",
    "uebergabedatum",
    "art",
    "zaehler_strom",
    "zaehler_wasser",
    "schluessel_anzahl",
    "bemerkungen",
)

_TEXT_FELDER = frozenset({"mieter_name", "objekt"})
_ZAEHLER_FELDER = frozenset({"zaehler_strom", "zaehler_wasser"})
_DATUM_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_DATUM_PUNKT = re.compile(r"([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{4})")
_ZAHL = re.compile(r"([0-9]+)(?:\.([0-9]{1,3}))?")
_ZIFFERN = re.compile(r"[0-9]+")
_ZEILENUMBRUCH = re.compile(r"\s*(?:\r\n|\r|\n)\s*")


def _datum_normalisieren(feld: str, wert: object) -> str:
    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss ein Datum als Text enthalten")

    treffer = _DATUM_ISO.fullmatch(wert)
    if treffer is not None:
        jahr, monat, tag = (int(teil) for teil in treffer.groups())
    else:
        treffer = _DATUM_PUNKT.fullmatch(wert)
        if treffer is None:
            raise ValueError(f"Feld '{feld}' muss das Format YYYY-MM-DD oder D.M.YYYY haben")
        tag, monat, jahr = (int(teil) for teil in treffer.groups())

    try:
        datum = date(jahr, monat, tag)
    except ValueError as fehler:
        raise ValueError(f"Feld '{feld}' ist kein gueltiges Kalenderdatum") from fehler
    return f"{datum.day:02d}.{datum.month:02d}.{datum.year:04d}"


def _art_normalisieren(feld: str, wert: object) -> str:
    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss 'Einzug' oder 'Auszug' enthalten")

    normalform = {"einzug": "Einzug", "auszug": "Auszug"}
    if wert.casefold() not in normalform:
        raise ValueError(f"Feld '{feld}' muss 'Einzug' oder 'Auszug' enthalten")
    return normalform[wert.casefold()]


def _zaehler_normalisieren(feld: str, wert: object) -> str:
    if isinstance(wert, bool):
        raise ValueError(f"Feld '{feld}' muss eine nicht negative Zahl enthalten")

    if isinstance(wert, int):
        if wert < 0:
            raise ValueError(f"Feld '{feld}' darf nicht negativ sein")
        return str(wert)

    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss eine nicht negative Zahl enthalten")

    treffer = _ZAHL.fullmatch(wert)
    if treffer is None:
        raise ValueError(
            f"Feld '{feld}' muss eine nicht negative Zahl mit hoechstens "
            "drei Nachkommastellen und Punkt als Dezimaltrenner enthalten"
        )

    ganzzahl, nachkomma = treffer.groups()
    ganzzahl = ganzzahl.lstrip("0") or "0"
    nachkomma = (nachkomma or "").rstrip("0")
    if not nachkomma:
        return ganzzahl
    return f"{ganzzahl}.{nachkomma}"


def _schluessel_normalisieren(feld: str, wert: object) -> str:
    if isinstance(wert, bool):
        raise ValueError(f"Feld '{feld}' muss eine Zahl von 0 bis 99 enthalten")

    if isinstance(wert, int):
        if not 0 <= wert <= 99:
            raise ValueError(f"Feld '{feld}' muss eine Zahl von 0 bis 99 enthalten")
        return str(wert)

    if not isinstance(wert, str) or _ZIFFERN.fullmatch(wert) is None:
        raise ValueError(f"Feld '{feld}' muss eine Zahl von 0 bis 99 enthalten")

    normalisiert = wert.lstrip("0") or "0"
    if len(normalisiert) > 2 or (len(normalisiert) == 2 and normalisiert > "99"):
        raise ValueError(f"Feld '{feld}' muss eine Zahl von 0 bis 99 enthalten")
    return normalisiert


def _bemerkungen_normalisieren(feld: str, wert: object) -> str:
    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss ein Text sein")

    text = _ZEILENUMBRUCH.sub(" ", wert).strip()
    if len(text) > 500:
        raise ValueError(f"Feld '{feld}' darf hoechstens 500 Zeichen enthalten")
    if "{{" in text or "}}" in text:
        raise ValueError(f"Feld '{feld}' darf keine Platzhalter enthalten")
    return text


def normalisiere_protokoll(daten: dict) -> dict[str, str]:
    """Prueft die uebergebenen Protokollfelder und liefert ihre Normalform.

    Fehlende Felder sind erlaubt. Unbekannte Feldnamen, ungueltige Werte und
    eine Eingabe, die kein dict ist, loesen einen ValueError mit Feldnamen aus.
    """

    if not isinstance(daten, dict):
        raise ValueError("daten muss ein dict sein")

    for feld in daten:
        if feld not in PROTOKOLL_FELDER:
            raise ValueError(f"Unbekanntes Feld {feld!r}")

    ergebnis: dict[str, str] = {}
    for feld, wert in daten.items():
        if feld in _TEXT_FELDER:
            ergebnis[feld] = normalisiere({feld: wert})[feld]
        elif feld == "uebergabedatum":
            ergebnis[feld] = _datum_normalisieren(feld, wert)
        elif feld == "art":
            ergebnis[feld] = _art_normalisieren(feld, wert)
        elif feld in _ZAEHLER_FELDER:
            ergebnis[feld] = _zaehler_normalisieren(feld, wert)
        elif feld == "schluessel_anzahl":
            ergebnis[feld] = _schluessel_normalisieren(feld, wert)
        elif feld == "bemerkungen":
            ergebnis[feld] = _bemerkungen_normalisieren(feld, wert)
    return ergebnis
