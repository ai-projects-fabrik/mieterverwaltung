"""Objekt-Tabelle der Oberflaeche in Mietobjekte umwandeln."""

from __future__ import annotations

import re
from collections.abc import Iterable

from projekt.felder import normalisiere
from projekt.objekte import normalisiere_objekt

SPALTEN: tuple[tuple[str, str], ...] = (
    ("bezeichnung", "Bezeichnung"),
    ("miete_netto", "Miete netto (CHF)"),
    ("nebenkosten", "Nebenkosten (CHF)"),
    ("kaution", "Kaution (CHF)"),
)

_SPALTENFELDER = frozenset(feld for feld, _ in SPALTEN)
_FORMULARZEILE = re.compile(r"zeile_([0-9]{1,3})_(id|bezeichnung|miete_netto|nebenkosten|kaution)")
_TRANSLITERATION = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_BASISLAENGE = 36
_MAX_ID_LAENGE = 40


def _basis_id(bezeichnung: str) -> str:
    klein = bezeichnung.lower().translate(_TRANSLITERATION)
    basis = re.sub(r"[^a-z0-9]+", "-", klein).strip("-")[:_BASISLAENGE].strip("-")
    return basis or "objekt"


def neue_id(bezeichnung: str, vorhandene: Iterable[str]) -> str:
    """Erzeugt aus einer Bezeichnung eine noch freie technische Objekt-id.

    Umlaute und ss werden transliteriert, alle anderen Zeichen trennen
    Wortteile. Kollidiert die id mit einer vorhandenen, werden die Suffixe
    ``-2``, ``-3`` usw. angehaengt. Die Eingabe muss Text sein.
    """

    if not isinstance(bezeichnung, str):
        raise ValueError("Bezeichnung muss ein Text sein")

    belegt = set(vorhandene)
    basis = _basis_id(bezeichnung)
    if basis not in belegt:
        return basis

    nummer = 2
    while True:
        suffix = f"-{nummer}"
        stamm = basis[: max(1, _MAX_ID_LAENGE - len(suffix))].rstrip("-") or "objekt"
        kandidat = (stamm + suffix)[:_MAX_ID_LAENGE].rstrip("-")
        if kandidat not in belegt:
            return kandidat
        nummer += 1


def zeilen_aus_formular(form: dict[str, str]) -> list[dict[str, str]]:
    """Liest die Tabellenzeilen ``zeile_<n>_<feld>`` aus einem Formular.

    Die Zeilen werden nach ``n`` aufsteigend sortiert. Unbekannte Schluessel
    und Nummern ausserhalb von 0 bis 999 werden ignoriert. Werte werden
    getrimmt; die Eingabe wird nicht veraendert.
    """

    if not isinstance(form, dict):
        raise ValueError("form muss ein dict sein")

    zeilen: dict[int, dict[str, str]] = {}
    for schluessel, wert in form.items():
        if not isinstance(schluessel, str):
            continue
        treffer = _FORMULARZEILE.fullmatch(schluessel)
        if treffer is None:
            continue
        if not isinstance(wert, str):
            raise ValueError(f"Feld '{schluessel}' muss ein Text sein")
        nummer, feld = int(treffer.group(1)), treffer.group(2)
        zeilen.setdefault(nummer, {})[feld] = wert.strip()

    return [zeilen[nummer] for nummer in sorted(zeilen)]


def _hat_spaltenwert(zeile: dict, feld: str) -> bool:
    wert = zeile.get(feld)
    return wert is not None and (not isinstance(wert, str) or wert.strip() != "")


def _zeile_mit_spaltenwerten(zeile: dict) -> bool:
    return any(_hat_spaltenwert(zeile, feld) for feld in _SPALTENFELDER)


def _bezeichnung(zeile: dict, nummer: int) -> str:
    wert = zeile.get("bezeichnung")
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        raise ValueError(f"Zeile {nummer}: Bezeichnung fehlt")
    try:
        return normalisiere({"objekt": wert})["objekt"]
    except ValueError as fehler:
        raise ValueError(f"Zeile {nummer}: Bezeichnung: {fehler}") from fehler


def _betraege(zeile: dict, nummer: int) -> dict[str, str]:
    ergebnis: dict[str, str] = {}
    for feld, beschriftung in SPALTEN[1:]:
        if not _hat_spaltenwert(zeile, feld):
            continue
        try:
            ergebnis[feld] = normalisiere({feld: zeile[feld]})[feld]
        except ValueError as fehler:
            raise ValueError(f"Zeile {nummer}: {beschriftung}: {fehler}") from fehler
    return ergebnis


def _bestehende_ids(bestehend: list[dict]) -> set[str]:
    if not isinstance(bestehend, list):
        raise ValueError("bestehend muss eine Liste sein")
    ids: set[str] = set()
    for objekt in bestehend:
        if not isinstance(objekt, dict):
            raise ValueError("bestehend muss Objekte als dict enthalten")
        objekt_id = objekt.get("id")
        if isinstance(objekt_id, str):
            ids.add(objekt_id)
    return ids


def objekte_aus_zeilen(zeilen: list[dict], bestehend: list[dict]) -> list[dict[str, str]]:
    """Wandelt Tabellenzeilen in normalisierte Mietobjekte um.

    Die Zeilen sind die ganze Wahrheit: Zeilen ohne sichtbaren Spaltenwert
    entfallen, womit Objekte entfernt werden. Eine bestehende id wird
    uebernommen, sofern sie vorhanden und noch nicht verwendet ist; sonst
    entsteht automatisch eine neue id aus der Bezeichnung. Das Ergebnis ist
    nach id sortiert; Eingaben bleiben unveraendert.
    """

    if not isinstance(zeilen, list):
        raise ValueError("zeilen muss eine Liste sein")

    vorhanden = _bestehende_ids(bestehend)
    belegt = set(vorhanden)
    vergeben: set[str] = set()
    ergebnis: list[dict[str, str]] = []

    for nummer, zeile in enumerate(zeilen, start=1):
        if not isinstance(zeile, dict):
            raise ValueError(f"Zeile {nummer} muss ein dict sein")
        if not _zeile_mit_spaltenwerten(zeile):
            continue

        bezeichnung = _bezeichnung(zeile, nummer)
        objekt_id = zeile.get("id")
        if isinstance(objekt_id, str):
            objekt_id = objekt_id.strip()
        if not isinstance(objekt_id, str) or objekt_id not in vorhanden or objekt_id in vergeben:
            objekt_id = neue_id(bezeichnung, belegt)
        vergeben.add(objekt_id)
        belegt.add(objekt_id)

        objekt = {"id": objekt_id, "bezeichnung": bezeichnung}
        objekt.update(_betraege(zeile, nummer))
        ergebnis.append(normalisiere_objekt(objekt))

    return sorted(ergebnis, key=lambda objekt: objekt["id"])
