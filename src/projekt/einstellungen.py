"""Pfade fuer Objektdaten, Vorlagen und Ausgaben in einer lokalen JSON-Datei."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

EINSTELLUNGEN_FELDER: tuple[str, ...] = (
    "objekte_datei",
    "vorlagen_lokal",
    "vorlagen_drive",
    "ausgabe_lokal",
    "ausgabe_drive",
    "drive_wurzel",
)

DRIVE_STANDARD = "G:\\My Drive"

_PRAEFIX_EINSTELLUNGEN = "MIETER_EINSTELLUNGEN"
_ORDNER_ARTEN = frozenset({"vorlagen", "ausgabe"})
_ORDNER_ORTE = frozenset({"lokal", "drive"})
_PDF_ORDNER = {
    "eingang": "MV-zu-pdf",
    "ausgabe": "MV-pdf",
    "erledigt": "MV-erledigt",
}


def normalisiere_einstellungen(daten: dict) -> dict[str, str]:
    """Prueft Einstellungen und liefert sie ohne leere Werte und Leerraum.

    Erlaubt sind nur die Schluessel aus ``EINSTELLUNGEN_FELDER``. Werte muessen
    Text sein, werden getrimmt und duerfen hoechstens 400 Zeichen sowie kein
    NUL-Zeichen enthalten. Leere Werte entfallen. Unbekannte Schluessel,
    ungueltige Werte und eine Eingabe, die kein dict ist, loesen einen
    ValueError mit Feldnamen aus.
    """

    if not isinstance(daten, dict):
        raise ValueError("Einstellungen muessen als dict uebergeben werden")

    for feld in daten:
        if feld not in EINSTELLUNGEN_FELDER:
            raise ValueError(f"Unbekanntes Feld {feld!r}")

    ergebnis: dict[str, str] = {}
    for feld, wert in daten.items():
        if not isinstance(wert, str):
            raise ValueError(f"Feld '{feld}' muss als Text uebergeben werden")

        text = wert.strip()
        if not text:
            continue
        if len(text) > 400:
            raise ValueError(f"Feld '{feld}' darf hoechstens 400 Zeichen enthalten")
        if "\x00" in text:
            raise ValueError(f"Feld '{feld}' darf kein NUL-Zeichen enthalten")
        ergebnis[feld] = text

    return ergebnis


def lade_einstellungen(pfad: Path | str) -> dict[str, str]:
    """Liest und prueft Einstellungen; eine fehlende Datei ergibt ``{}``.

    Eine nicht lesbare Datei, ungueltiges JSON oder ungueltige Einstellungen
    loesen einen ValueError aus.
    """

    datei = Path(pfad)
    try:
        roh = datei.read_bytes()
    except FileNotFoundError:
        return {}
    except OSError as fehler:
        raise ValueError(
            f"Einstellungsdatei '{datei}' konnte nicht gelesen werden: {fehler}"
        ) from fehler

    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError as fehler:
        raise ValueError(f"Einstellungsdatei '{datei}' ist nicht UTF-8-kodiert") from fehler

    try:
        daten = json.loads(text)
    except json.JSONDecodeError as fehler:
        raise ValueError(f"Einstellungsdatei '{datei}' enthaelt kein gueltiges JSON") from fehler

    try:
        return normalisiere_einstellungen(daten)
    except ValueError as fehler:
        raise ValueError(f"Einstellungsdatei '{datei}': {fehler}") from fehler


def speichere_einstellungen(pfad: Path | str, daten: dict) -> None:
    """Prueft Einstellungen und schreibt sie atomar als UTF-8-JSON.

    Fehlende Ordner werden angelegt. Die Datei wird zuerst in eine Temp-Datei
    im selben Ordner geschrieben und danach ersetzt; bei einem Fehler bleibt
    eine vorhandene Datei unveraendert und es bleiben keine Temp-Reste zurueck.
    """

    ziel = Path(pfad)
    geprueft = normalisiere_einstellungen(daten)
    inhalt = json.dumps(geprueft, ensure_ascii=False, indent=2) + "\n"

    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
    except OSError as fehler:
        raise ValueError(f"Ordner fuer Einstellungen '{ziel.parent}' ist nicht nutzbar") from fehler

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
    except (OSError, UnicodeError) as fehler:
        raise ValueError(f"Einstellungsdatei '{ziel}' konnte nicht geschrieben werden") from fehler
    finally:
        if temp_pfad is not None:
            try:
                temp_pfad.unlink(missing_ok=True)
            except OSError:
                pass


def einstellungen_pfad(
    umgebung: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Liefert den Einstellungspfad aus der Umgebung oder aus dem Benutzerordner.

    Ein nicht leerer Wert von ``MIETER_EINSTELLUNGEN`` gewinnt. Sonst ist das
    Ergebnis ``<home>/.mieterverwaltung/einstellungen.json``. Es wird nichts
    angelegt oder gelesen.
    """

    quelle = os.environ if umgebung is None else umgebung
    eigener_pfad = quelle.get(_PRAEFIX_EINSTELLUNGEN)
    if eigener_pfad:
        return Path(eigener_pfad)

    basis = Path.home() if home is None else Path(home)
    return basis / ".mieterverwaltung" / "einstellungen.json"


def ordner(einstellungen: dict, art: str, ort: str) -> Path:
    """Liefert den lokalen oder Drive-Ordner fuer Vorlagen beziehungsweise Ausgabe.

    ``art`` ist ``vorlagen`` oder ``ausgabe``, ``ort`` ist ``lokal`` oder
    ``drive``. Eine ungueltige Art, ein ungueltiger Ort oder eine fehlende
    Einstellung loesen einen ValueError aus.
    """

    if art not in _ORDNER_ARTEN:
        raise ValueError("Feld 'art' muss 'vorlagen' oder 'ausgabe' sein")
    if ort not in _ORDNER_ORTE:
        raise ValueError("Feld 'ort' muss 'lokal' oder 'drive' sein")
    if not isinstance(einstellungen, dict):
        raise ValueError("Einstellungen muessen als dict uebergeben werden")

    schluessel = f"{art}_{ort}"
    wert = einstellungen.get(schluessel)
    if not isinstance(wert, str) or not wert.strip():
        raise ValueError(f"Feld '{schluessel}' ist nicht gesetzt")
    return Path(wert.strip())


def pdf_ordner(einstellungen: dict, art: str) -> Path:
    """Liefert einen PDF-Ordner unter der Drive-Wurzel.

    ``art`` ist ``eingang``, ``ausgabe`` oder ``erledigt``. Ohne
    ``drive_wurzel`` gilt ``DRIVE_STANDARD``. Es wird nichts angelegt oder
    geprueft; eine ungueltige Art loest einen ValueError aus.
    """

    if art not in _PDF_ORDNER:
        raise ValueError("Feld 'art' muss 'eingang', 'ausgabe' oder 'erledigt' sein")
    if not isinstance(einstellungen, dict):
        raise ValueError("Einstellungen muessen als dict uebergeben werden")

    wurzel = einstellungen.get("drive_wurzel", DRIVE_STANDARD)
    if not isinstance(wurzel, str):
        raise ValueError("Feld 'drive_wurzel' muss als Text uebergeben werden")
    if not wurzel.strip():
        wurzel = DRIVE_STANDARD
    return Path(wurzel.strip()) / _PDF_ORDNER[art]
