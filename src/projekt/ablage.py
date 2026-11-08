"""Lesezugriff auf Vorlagen und exklusives Ablegen von Ausgaben im Dateisystem."""

from __future__ import annotations

from pathlib import Path

_AUSGABE_ENDUNGEN = (".docx", ".pdf")


def _als_ordner(ordner: str | Path) -> Path:
    try:
        pfad = Path(ordner)
    except (TypeError, ValueError) as fehler:
        raise ValueError(f"ordner '{ordner}' ist ungueltig") from fehler
    if not pfad.is_dir():
        raise ValueError(f"ordner '{pfad}' ist kein vorhandener Ordner")
    return pfad


def _gueltiger_ausgabename(name: str) -> bool:
    if not name or "/" in name or "\\" in name or "\x00" in name:
        return False
    return any(name.endswith(endung) and len(name) > len(endung) for endung in _AUSGABE_ENDUNGEN)


def liste_vorlagen(ordner: str | Path) -> list[str]:
    """Liefert die DOCX-Vorlagen direkt im Ordner, nach ``str.casefold`` sortiert.

    Unterordner, Dateien mit anderer Endung und Word-Sperrdateien mit dem
    Praefix ``~$`` werden ignoriert. Ein fehlender oder nicht lesbarer Ordner
    loest einen ValueError aus.
    """

    pfad = _als_ordner(ordner)
    try:
        eintraege = list(pfad.iterdir())
    except OSError as fehler:
        raise ValueError(f"ordner '{pfad}' konnte nicht gelesen werden: {fehler}") from fehler

    try:
        namen = [
            eintrag.name
            for eintrag in eintraege
            if eintrag.is_file()
            and eintrag.name.casefold().endswith(".docx")
            and not eintrag.name.startswith("~$")
        ]
    except OSError as fehler:
        raise ValueError(f"ordner '{pfad}' konnte nicht gelesen werden: {fehler}") from fehler
    return sorted(namen, key=str.casefold)


def lese_vorlage(ordner: str | Path, name: str) -> bytes:
    """Liest eine vorhandene DOCX-Vorlage direkt aus dem Ordner.

    Erlaubt sind nur Namen, die auch von :func:`liste_vorlagen` geliefert
    werden. Pfadtrenner, leere Namen und nicht vorhandene Vorlagen loesen einen
    ValueError mit dem Begriff ``vorlage`` aus.
    """

    if (
        not isinstance(name, str)
        or not name
        or "/" in name
        or "\\" in name
        or name in {".", ".."}
        or "\x00" in name
    ):
        raise ValueError(f"vorlage '{name}' ist kein einfacher Dateiname")

    try:
        vorhanden = liste_vorlagen(ordner)
    except ValueError as fehler:
        raise ValueError(f"vorlage '{name}' konnte nicht gelesen werden: {fehler}") from fehler
    if name not in vorhanden:
        raise ValueError(f"vorlage '{name}' ist nicht vorhanden")

    pfad = _als_ordner(ordner) / name
    try:
        return pfad.read_bytes()
    except OSError as fehler:
        raise ValueError(f"vorlage '{name}' konnte nicht gelesen werden: {fehler}") from fehler


def schreibe_ausgabe(ordner: str | Path, name: str, daten: bytes) -> str:
    """Schreibt eine DOCX- oder PDF-Ausgabe, ohne eine Datei zu ueberschreiben.

    Ist ``name`` bereits belegt, wird ``<stamm>-2.<endung>``, danach ``-3``
    usw. verwendet. Zurueckgegeben wird der tatsaechlich angelegte Dateiname.
    Ungueltige Namen, ein fehlender Ordner oder Daten, die keine ``bytes``
    sind, loesen einen ValueError aus; bei einem Schreibfehler bleibt keine
    neue Datei zurueck.
    """

    if not isinstance(name, str) or not _gueltiger_ausgabename(name):
        raise ValueError(f"name '{name}' muss auf .docx oder .pdf enden")
    pfad = _als_ordner(ordner)
    if not isinstance(daten, bytes):
        raise ValueError(f"daten fuer '{name}' muessen als bytes uebergeben werden")

    endung = ".docx" if name.endswith(".docx") else ".pdf"
    stamm = name[: -len(endung)]
    kandidat = name
    nummer = 2
    while True:
        ziel = pfad / kandidat
        try:
            datei = ziel.open("xb")
        except FileExistsError:
            kandidat = f"{stamm}-{nummer}{endung}"
            nummer += 1
            continue
        except OSError as fehler:
            raise ValueError(
                f"name '{kandidat}' konnte im ordner '{pfad}' nicht angelegt werden: {fehler}"
            ) from fehler

        try:
            with datei:
                datei.write(daten)
        except Exception as fehler:
            try:
                ziel.unlink()
            except OSError:
                pass
            raise ValueError(
                f"name '{kandidat}' konnte im ordner '{pfad}' nicht geschrieben werden: {fehler}"
            ) from fehler
        return kandidat
