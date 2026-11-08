"""Zwei Ordner-Einstellungen und daraus abgeleitete Pfade (GUI v3)."""

from __future__ import annotations

from pathlib import Path

from projekt.einstellungen import DRIVE_STANDARD, normalisiere_einstellungen, pdf_ordner

_DRIVE_KANDIDATEN: tuple[str, ...] = (DRIVE_STANDARD, "G:\\Meine Ablage")
_MAX_ORDNER_LAENGE = 300
_ORDNER_FELDER = ("vorlagen_lokal", "ausgabe_lokal", "vorlagen_drive", "ausgabe_drive")


def _als_text(wert: object, bezeichnung: str) -> str:
    if not isinstance(wert, str):
        raise ValueError(f"{bezeichnung} muss als Text uebergeben werden")
    text = wert.strip()
    if not text:
        raise ValueError(f"{bezeichnung} darf nicht leer sein")
    if len(text) > _MAX_ORDNER_LAENGE:
        raise ValueError(f"{bezeichnung} darf hoechstens {_MAX_ORDNER_LAENGE} Zeichen enthalten")
    if "\x00" in text:
        raise ValueError(f"{bezeichnung} darf kein NUL-Zeichen enthalten")
    return text


def _als_pfad(text: str, bezeichnung: str) -> Path:
    try:
        return Path(text)
    except (OSError, TypeError, ValueError) as fehler:
        raise ValueError(f"{bezeichnung} ist kein gueltiger Pfad") from fehler


def standard_lokal(home: str | Path | None = None) -> str:
    """Liefert ``<home>/Documents/Mietverwaltung`` als Text.

    Ohne ``home`` wird ``Path.home()`` verwendet. Es wird nichts angelegt.
    Ein ungueltiges ``home`` loest einen ValueError aus.
    """

    try:
        basis = Path.home() if home is None else Path(home)
    except (OSError, TypeError, ValueError) as fehler:
        raise ValueError("Feld 'home' ist kein gueltiger Ordner") from fehler
    return str(basis / "Documents" / "Mietverwaltung")


def erkenne_drive(kandidaten: tuple[str, ...] | None = None) -> str:
    """Liefert den ersten vorhandenen Drive-Ordner aus ``kandidaten``.

    Ohne Kandidaten werden ``DRIVE_STANDARD`` und ``G:\\Meine Ablage`` in
    dieser Reihenfolge geprueft. Ist keiner vorhanden, gilt ``DRIVE_STANDARD``.
    Es wird nichts angelegt.
    """

    geprueft = _DRIVE_KANDIDATEN if kandidaten is None else kandidaten
    for kandidat in geprueft:
        if not isinstance(kandidat, str):
            raise ValueError("Google-Drive-Ordner muss als Text uebergeben werden")
        if not kandidat:
            continue
        try:
            if Path(kandidat).is_dir():
                return kandidat
        except (OSError, ValueError):
            continue
    return DRIVE_STANDARD


def drive_ordner(einstellungen: dict, kandidaten: tuple[str, ...] | None = None) -> str:
    """Liefert die Drive-Wurzel aus den Einstellungen oder erkennt sie.

    Ein nicht leerer, getrimmter Wert von ``drive_wurzel`` gewinnt. Sonst wird
    :func:`erkenne_drive` mit ``kandidaten`` verwendet. Eine Eingabe, die kein
    dict ist, oder ein ungueltiges ``drive_wurzel`` loest einen ValueError aus.
    """

    if not isinstance(einstellungen, dict):
        raise ValueError("Einstellungen muessen als dict uebergeben werden")

    if "drive_wurzel" in einstellungen:
        wert = einstellungen["drive_wurzel"]
        if not isinstance(wert, str):
            raise ValueError("Feld 'drive_wurzel' muss als Text uebergeben werden")
        text = wert.strip()
        if "\x00" in text:
            raise ValueError("Feld 'drive_wurzel' darf kein NUL-Zeichen enthalten")
        if text:
            return text
    return erkenne_drive(kandidaten)


def lokaler_ordner(einstellungen: dict, home: str | Path | None = None) -> str:
    """Liefert den Elternordner von ``objekte_datei`` oder den lokalen Standard.

    So bleibt das Altformat lesbar. Fehlt ``objekte_datei`` oder ist der Wert
    leer, gilt :func:`standard_lokal` mit ``home``. Eine Eingabe, die kein dict
    ist, oder ein ungueltiger Wert loest einen ValueError aus.
    """

    if not isinstance(einstellungen, dict):
        raise ValueError("Einstellungen muessen als dict uebergeben werden")

    if "objekte_datei" not in einstellungen:
        return standard_lokal(home)
    wert = einstellungen["objekte_datei"]
    if not isinstance(wert, str):
        raise ValueError("Feld 'objekte_datei' muss als Text uebergeben werden")
    text = wert.strip()
    if "\x00" in text:
        raise ValueError("Feld 'objekte_datei' darf kein NUL-Zeichen enthalten")
    if not text:
        return standard_lokal(home)
    return str(_als_pfad(text, "Feld 'objekte_datei'").parent)


def einstellungen_aus_ordnern(drive: str, lokal: str) -> dict[str, str]:
    """Leitet alle Einstellungen aus Drive- und lokalem Ordner ab.

    Beide Ordner muessen nicht leere Texte mit hoechstens 300 Zeichen ohne
    NUL-Zeichen sein; sie werden getrimmt. Das Ergebnis ist gueltig fuer
    :func:`projekt.einstellungen.normalisiere_einstellungen` und legt nichts an.
    """

    drive_text = _als_text(drive, "Google-Drive-Ordner")
    lokal_text = _als_text(lokal, "Lokaler Ordner")
    drive_pfad = _als_pfad(drive_text, "Google-Drive-Ordner")
    lokal_pfad = _als_pfad(lokal_text, "Lokaler Ordner")

    ergebnis = {
        "drive_wurzel": drive_text,
        "objekte_datei": str(lokal_pfad / "objekte.json"),
        "vorlagen_lokal": str(lokal_pfad / "Vorlagen"),
        "ausgabe_lokal": str(lokal_pfad / "Ausgabe"),
        "vorlagen_drive": str(drive_pfad / "Mietverwaltung" / "Vorlagen"),
        "ausgabe_drive": str(drive_pfad / "Mietverwaltung" / "Ausgabe"),
    }
    return normalisiere_einstellungen(ergebnis)


def lege_ordner_an(einstellungen: dict) -> list[str]:
    """Legt die noetigen Ordner an und liefert nur die neu erzeugten Ziele.

    Benoetigt ``vorlagen_lokal``, ``ausgabe_lokal``, ``vorlagen_drive`` und
    ``ausgabe_drive``. Fehlt ein Feld, wird ein ValueError mit dessen Namen
    ausgeloest. Existiert der Drive-Ordner nicht, wird ein ValueError mit
    ``Google-Drive-Ordner`` ausgeloest und nichts angelegt. Elternordner werden
    mit angelegt, aber nicht in der Rueckgabe aufgefuehrt. Ein zweiter Aufruf
    liefert eine leere Liste.
    """

    if not isinstance(einstellungen, dict):
        raise ValueError("Einstellungen muessen als dict uebergeben werden")

    ziele: list[tuple[str, Path]] = []
    for feld in _ORDNER_FELDER:
        wert = einstellungen.get(feld)
        if not isinstance(wert, str) or not wert.strip():
            raise ValueError(f"Feld '{feld}' ist nicht gesetzt")
        text = wert.strip()
        if "\x00" in text:
            raise ValueError(f"Feld '{feld}' darf kein NUL-Zeichen enthalten")
        ziele.append((feld, _als_pfad(text, f"Feld '{feld}'")))

    drive_text = drive_ordner(einstellungen)
    drive_pfad = _als_pfad(drive_text, "Google-Drive-Ordner")
    if not drive_pfad.is_dir():
        raise ValueError(f"Google-Drive-Ordner '{drive_text}' ist nicht vorhanden")

    pdf_pfad = pdf_ordner(einstellungen, "eingang")
    ziele.append(("PDF-Ordner", pdf_pfad))

    eindeutig: list[tuple[str, Path]] = []
    gesehen: set[str] = set()
    for feld, pfad in ziele:
        schluessel = str(pfad)
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        if pfad.exists() and not pfad.is_dir():
            raise ValueError(f"Feld '{feld}' verweist auf eine Datei statt auf einen Ordner")
        eindeutig.append((feld, pfad))

    neu = [(feld, pfad) for feld, pfad in eindeutig if not pfad.exists()]
    for feld, pfad in neu:
        try:
            pfad.mkdir(parents=True, exist_ok=True)
        except OSError as fehler:
            raise ValueError(
                f"Ordner fuer Feld '{feld}' konnte nicht angelegt werden: {fehler}"
            ) from fehler
    return [str(pfad) for _feld, pfad in neu]
