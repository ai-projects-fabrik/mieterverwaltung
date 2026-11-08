"""Stammdaten der Mietobjekte in einer lokalen JSON-Datei."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from projekt.felder import normalisiere

_BETRAGSFELDER = ("miete_netto", "nebenkosten", "kaution")
_FELDER = ("id", "bezeichnung", *_BETRAGSFELDER)
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")


def _als_pfad(pfad: object) -> Path:
    try:
        return Path(pfad)
    except TypeError as fehler:
        raise ValueError("pfad muss ein Dateipfad sein") from fehler


def _normalisiere_id(wert: object) -> str:
    if not isinstance(wert, str):
        raise ValueError("Feld 'id' muss Text sein")

    objekt_id = wert.strip()
    if _ID.fullmatch(objekt_id) is None:
        raise ValueError(
            "Feld 'id' muss mit einem Kleinbuchstaben oder einer Ziffer beginnen und "
            "danach hoechstens 39 Kleinbuchstaben, Ziffern, Unterstriche oder Bindestriche "
            "enthalten"
        )
    return objekt_id


def normalisiere_objekt(daten: dict) -> dict[str, str]:
    """Prueft ein Mietobjekt und liefert seine Normalform.

    Pflichtfelder sind ``id`` und ``bezeichnung``. Die Betragsfelder
    ``miete_netto``, ``nebenkosten`` und ``kaution`` sind optional. Unbekannte
    Schluessel, fehlende Pflichtfelder, falsche Typen und ungueltige Werte
    loesen einen ValueError mit dem betroffenen Feldnamen aus. Die Eingabe
    wird nicht veraendert.
    """

    if not isinstance(daten, dict):
        raise ValueError("objekt muss ein dict sein")

    for feld in daten:
        if feld not in _FELDER:
            raise ValueError(f"Unbekanntes Feld {feld!r}")

    if "id" not in daten:
        raise ValueError("Feld 'id' fehlt")
    if "bezeichnung" not in daten:
        raise ValueError("Feld 'bezeichnung' fehlt")

    ergebnis = {"id": _normalisiere_id(daten["id"])}
    try:
        ergebnis["bezeichnung"] = normalisiere({"objekt": daten["bezeichnung"]})["objekt"]
    except ValueError as fehler:
        raise ValueError(f"Feld 'bezeichnung' ist ungueltig: {fehler}") from fehler

    for feld in _BETRAGSFELDER:
        if feld in daten:
            ergebnis[feld] = normalisiere({feld: daten[feld]})[feld]
    return ergebnis


def _normalisiere_liste(objekte: object) -> list[dict[str, str]]:
    if not isinstance(objekte, list):
        raise ValueError("objekte muss eine Liste sein")

    ergebnis: list[dict[str, str]] = []
    gesehen: set[str] = set()
    for objekt in objekte:
        normalisiert = normalisiere_objekt(objekt)
        objekt_id = normalisiert["id"]
        if objekt_id in gesehen:
            raise ValueError(f"Feld 'id': doppelte id {objekt_id!r}")
        gesehen.add(objekt_id)
        ergebnis.append(normalisiert)
    return sorted(ergebnis, key=lambda objekt: objekt["id"])


def objekt_als_felder(objekt: dict) -> dict[str, str]:
    """Liefert die aus einem Mietobjekt ableitbaren Vertragsfelder.

    ``bezeichnung`` wird zu ``objekt``; vorhandene Betragsfelder werden
    uebernommen. Die technische ``id`` ist nicht enthalten. Das uebergebene
    Objekt wird zuvor normalisiert und geprueft.
    """

    normalisiert = normalisiere_objekt(objekt)
    ergebnis = {"objekt": normalisiert["bezeichnung"]}
    for feld in _BETRAGSFELDER:
        if feld in normalisiert:
            ergebnis[feld] = normalisiert[feld]
    return ergebnis


def setze_objekt(objekte: list[dict], objekt: dict) -> list[dict[str, str]]:
    """Ersetzt ein Objekt mit gleicher id oder fuegt es hinzu und sortiert nach id.

    Die uebergebene Liste und ihre Eintraege werden nicht veraendert. Alle
    Objekte werden normalisiert; ungueltige oder doppelte ids loesen einen
    ValueError aus.
    """

    vorhanden = _normalisiere_liste(objekte)
    neu = normalisiere_objekt(objekt)
    ergebnis = [eintrag for eintrag in vorhanden if eintrag["id"] != neu["id"]]
    ergebnis.append(neu)
    return sorted(ergebnis, key=lambda eintrag: eintrag["id"])


def entferne_objekt(objekte: list[dict], objekt_id: str) -> list[dict[str, str]]:
    """Entfernt das Objekt mit der angegebenen id und liefert eine neue Liste.

    Die Eingabeliste bleibt unveraendert. Eine ungueltige oder unbekannte id
    loest einen ValueError aus.
    """

    vorhanden = _normalisiere_liste(objekte)
    ziel_id = _normalisiere_id(objekt_id)
    ergebnis = [eintrag for eintrag in vorhanden if eintrag["id"] != ziel_id]
    if len(ergebnis) == len(vorhanden):
        raise ValueError(f"Feld 'id': Objekt {ziel_id!r} wurde nicht gefunden")
    return ergebnis


def lade_objekte(pfad: str | os.PathLike[str]) -> list[dict[str, str]]:
    """Liest und normalisiert die Mietobjekte aus einer JSON-Datei.

    Eine fehlende Datei ergibt eine leere Liste. Ungueltiges JSON, eine andere
    Struktur als eine Liste, ungueltige Objekte oder doppelte ids loesen einen
    ValueError aus. Das Ergebnis ist nach id sortiert.
    """

    datei = _als_pfad(pfad)
    try:
        text = datei.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except IsADirectoryError as fehler:
        raise ValueError(f"pfad '{datei}' ist keine Datei") from fehler
    except (OSError, UnicodeError) as fehler:
        raise ValueError(
            f"objekte aus '{datei}' konnten nicht gelesen werden: {fehler}"
        ) from fehler

    try:
        daten = json.loads(text)
    except (json.JSONDecodeError, ValueError) as fehler:
        raise ValueError(f"objekte in '{datei}' sind kein gueltiges JSON: {fehler}") from fehler
    if not isinstance(daten, list):
        raise ValueError(f"objekte in '{datei}' muessen als Liste gespeichert sein")
    return _normalisiere_liste(daten)


def speichere_objekte(pfad: str | os.PathLike[str], objekte: list[dict]) -> None:
    """Prueft und speichert Mietobjekte atomar als UTF-8-JSON.

    Alle Objekte werden vor dem Schreiben normalisiert und auf doppelte ids
    geprueft. Ein fehlender Zielordner wird nicht angelegt. Geschrieben wird
    ueber eine Temp-Datei im selben Ordner und ``os.replace``; bei einem Fehler
    bleibt eine vorhandene Zieldatei unveraendert.
    """

    normalisiert = _normalisiere_liste(objekte)
    datei = _als_pfad(pfad)
    ordner = datei.parent
    if not ordner.exists():
        raise ValueError(f"Ordner '{ordner}' fehlt")
    if not ordner.is_dir():
        raise ValueError(f"pfad '{ordner}' ist kein Ordner")
    if datei.exists() and datei.is_dir():
        raise ValueError(f"pfad '{datei}' ist ein Ordner")

    inhalt = json.dumps(normalisiert, ensure_ascii=False, indent=2) + "\n"
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=ordner,
            prefix=f".{datei.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp_name = temp.name
            temp.write(inhalt)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, datei)
        temp_name = None
    except (OSError, UnicodeError) as fehler:
        raise ValueError(
            f"objekte konnten nicht nach '{datei}' geschrieben werden: {fehler}"
        ) from fehler
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            except OSError:
                pass
