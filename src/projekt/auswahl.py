"""Letzte Auswahl der Oberflaeche in einer lokalen JSON-Datei merken."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from projekt.pfade import lokaler_ordner

AUSWAHL_FELDER: tuple[str, ...] = (
    "objekt_id",
    "vertrag_vorlage",
    "protokoll_vorlage",
    "format",
    "ziel",
)

_MAX_LAENGE = 200


def auswahl_pfad(einstellungen: dict, home: str | Path | None = None) -> Path:
    """Liefert den Pfad der letzten Auswahl im lokalen Ordner.

    Der lokale Ordner wird mit :func:`projekt.pfade.lokaler_ordner` aus den
    Einstellungen abgeleitet. Es wird nichts gelesen oder angelegt.
    """

    return Path(lokaler_ordner(einstellungen, home)) / "letzte_auswahl.json"


def _als_text(wert: object, feld: str) -> str:
    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss als Text uebergeben werden")
    text = wert.strip()
    if not text:
        raise ValueError(f"Feld '{feld}' darf nicht leer sein")
    if len(text) > _MAX_LAENGE:
        raise ValueError(f"Feld '{feld}' darf hoechstens {_MAX_LAENGE} Zeichen enthalten")
    if "\x00" in text:
        raise ValueError(f"Feld '{feld}' darf kein NUL-Zeichen enthalten")
    return text


def _pruefe_daten(daten: object) -> dict[str, str]:
    if not isinstance(daten, dict):
        raise ValueError("Auswahl muss als dict uebergeben werden")

    ergebnis: dict[str, str] = {}
    for feld, wert in daten.items():
        if feld not in AUSWAHL_FELDER:
            raise ValueError(f"Unbekanntes Feld {feld!r}")
        ergebnis[feld] = _als_text(wert, feld)
    return ergebnis


def _gelesene_daten(pfad: Path) -> object:
    try:
        roh = pfad.read_bytes()
        text = roh.decode("utf-8")
        return json.loads(text)
    except (OSError, UnicodeError, ValueError):
        return None


def lade_auswahl(pfad: Path | str) -> dict[str, str]:
    """Liest die letzte Auswahl; fehlende oder ungueltige Dateien ergeben ``{}``.

    Nur bekannte Felder mit nicht leerem Text ohne NUL-Zeichen und mit
    hoechstens 200 Zeichen werden uebernommen. Andere Werte und unbekannte
    Felder werden still ignoriert. Die Funktion loest nie eine Ausnahme aus.
    """

    try:
        ziel = Path(pfad)
    except (OSError, TypeError, ValueError):
        return {}

    daten = _gelesene_daten(ziel)
    if not isinstance(daten, dict):
        return {}

    ergebnis: dict[str, str] = {}
    for feld in AUSWAHL_FELDER:
        if feld not in daten:
            continue
        wert = daten[feld]
        if not isinstance(wert, str):
            continue
        text = wert.strip()
        if not text or len(text) > _MAX_LAENGE or "\x00" in text:
            continue
        ergebnis[feld] = text
    return ergebnis


def speichere_auswahl(pfad: Path | str, daten: dict) -> None:
    """Prueft, fuehrt mit der letzten Auswahl zusammen und schreibt atomar.

    Die Eingabe muss ein dict mit ausschliesslich bekannten Feldern und nicht
    leeren Texten sein. Werte werden getrimmt. Bei einem ungueltigen Wert
    bleibt eine vorhandene Datei unveraendert. Sonst wird die Datei als
    UTF-8-JSON in einer Temp-Datei im selben Ordner geschrieben und ersetzt.
    """

    try:
        ziel = Path(pfad)
    except (OSError, TypeError, ValueError) as fehler:
        raise ValueError("Feld 'pfad' ist kein gueltiger Pfad") from fehler

    geprueft = _pruefe_daten(daten)
    zusammen = lade_auswahl(ziel)
    zusammen.update(geprueft)
    inhalt = json.dumps(zusammen, ensure_ascii=False, indent=2) + "\n"

    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as fehler:
        raise ValueError(f"Feld 'pfad': Ordner '{ziel.parent}' ist nicht nutzbar") from fehler

    temp_pfad: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=ziel.parent,
            prefix=f".{ziel.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp_pfad = Path(temp.name)
            temp.write(inhalt)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_pfad, ziel)
        temp_pfad = None
    except (OSError, UnicodeError, ValueError) as fehler:
        raise ValueError(
            f"Feld 'pfad': Auswahl '{ziel}' konnte nicht geschrieben werden"
        ) from fehler
    finally:
        if temp_pfad is not None:
            try:
                temp_pfad.unlink(missing_ok=True)
            except OSError:
                pass
