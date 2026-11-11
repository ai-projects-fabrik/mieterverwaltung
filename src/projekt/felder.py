"""Pruefung und Normalisierung der veraenderlichen Vertragsfelder."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

FELDER: tuple[str, ...] = (
    "mieter_name",
    "wohnraumnutzer_name",
    "objekt",
    "mietbeginn",
    "miete_netto",
    "nebenkosten",
    "kaution",
)

_TEXT_FELDER = frozenset({"mieter_name", "wohnraumnutzer_name", "objekt"})
_BETRAGS_FELDER = frozenset({"miete_netto", "nebenkosten", "kaution"})
_DATUM_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_DATUM_PUNKT = re.compile(r"([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{4})")
_BETRAG = re.compile(r"(?:CHF )?(?:[0-9]{1,3}(?:'[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?")


def _text_normalisieren(feld: str, wert: object) -> str:
    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss ein Text sein")

    text = wert.strip()
    if not text:
        raise ValueError(f"Feld '{feld}' darf nicht leer sein")
    if len(text) > 120:
        raise ValueError(f"Feld '{feld}' darf hoechstens 120 Zeichen enthalten")
    if "{{" in text or "}}" in text:
        raise ValueError(f"Feld '{feld}' darf keine Platzhalter enthalten")
    return text


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


def _betrag_normalisieren(feld: str, wert: object) -> str:
    if isinstance(wert, bool):
        raise ValueError(f"Feld '{feld}' muss eine Zahl als int oder Text enthalten")

    if isinstance(wert, int):
        if wert < 0:
            raise ValueError(f"Feld '{feld}' darf nicht negativ sein")
        betrag = Decimal(wert)
    elif isinstance(wert, str):
        if _BETRAG.fullmatch(wert) is None:
            raise ValueError(
                f"Feld '{feld}' muss eine nicht negative Zahl mit hoechstens "
                "zwei Nachkommastellen sein"
            )
        zahl = wert.removeprefix("CHF ").replace("'", "")
        betrag = Decimal(zahl)
    else:
        raise ValueError(f"Feld '{feld}' muss eine Zahl als int oder Text enthalten")

    return format(betrag, ",.2f").replace(",", "'")


def normalisiere(daten: dict) -> dict[str, str]:
    """Prueft die uebergebenen Vertragsfelder und liefert ihre Normalform.

    Fehlende Felder sind erlaubt. Unbekannte Feldnamen, ungueltige Werte und
    eine Eingabe, die kein dict ist, loesen einen ValueError mit Feldnamen aus.
    """

    if not isinstance(daten, dict):
        raise ValueError("daten muss ein dict sein")

    for feld in daten:
        if feld not in FELDER:
            raise ValueError(f"Unbekanntes Feld {feld!r}")

    ergebnis: dict[str, str] = {}
    for feld, wert in daten.items():
        if feld in _TEXT_FELDER:
            ergebnis[feld] = _text_normalisieren(feld, wert)
        elif feld == "mietbeginn":
            ergebnis[feld] = _datum_normalisieren(feld, wert)
        elif feld in _BETRAGS_FELDER:
            ergebnis[feld] = _betrag_normalisieren(feld, wert)
    return ergebnis
