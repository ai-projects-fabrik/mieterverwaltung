"""Unterschiede zwischen altem und neuem Feldstand als Aenderungsbericht."""

from __future__ import annotations

from projekt.felder import FELDER

_LEER = "(leer)"
_FEHLT = object()


def _pruefe(daten: object, name: str) -> dict:
    if not isinstance(daten, dict):
        raise ValueError(f"{name} muss ein dict sein")

    for feld, wert in daten.items():
        if feld not in FELDER:
            raise ValueError(f"Unbekanntes Feld {feld!r}")
        if not isinstance(wert, str):
            raise ValueError(f"Feld '{feld}' muss als Text uebergeben werden")
    return daten


def bericht(alt: dict, neu: dict) -> str:
    """Vergleicht zwei Feldstaende und liefert die Aenderungen als Text.

    Geaenderte Felder erscheinen in der Reihenfolge von ``FELDER`` als Zeilen
    ``feld: alt -> neu``. Fehlende Werte werden als ``(leer)`` dargestellt;
    unveraenderte Felder fehlen. Ohne Unterschied lautet das Ergebnis
    ``keine Aenderungen``. Unbekannte Feldnamen, Nicht-dict-Eingaben und
    Nicht-Text-Werte loesen einen ValueError aus.
    """

    alt_geprueft = _pruefe(alt, "alt")
    neu_geprueft = _pruefe(neu, "neu")

    zeilen: list[str] = []
    for feld in FELDER:
        alt_wert = alt_geprueft.get(feld, _FEHLT)
        neu_wert = neu_geprueft.get(feld, _FEHLT)
        if alt_wert == neu_wert:
            continue

        alt_text = _LEER if alt_wert is _FEHLT else alt_wert
        neu_text = _LEER if neu_wert is _FEHLT else neu_wert
        zeilen.append(f"{feld}: {alt_text} -> {neu_text}")

    return "\n".join(zeilen) if zeilen else "keine Aenderungen"
