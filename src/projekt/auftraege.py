"""Geschaeftslogik der Oberflaeche: Formulare zu fertigen Vertragsdateien verarbeiten."""

from __future__ import annotations

import re
from pathlib import Path

from projekt.ablage import lese_vorlage, schreibe_ausgabe
from projekt.anfrage import aenderungen_aus_text
from projekt.bericht import bericht
from projekt.docx_fuellen import fuelle, platzhalter, unersetzt
from projekt.einstellungen import ordner, pdf_ordner
from projekt.felder import FELDER, normalisiere
from projekt.objekte import lade_objekte, objekt_als_felder
from projekt.protokoll import PROTOKOLL_FELDER, normalisiere_protokoll

FORMATE: tuple[str, ...] = ("docx", "pdf", "docx+pdf")

_HINWEIS = "PDF wird in Google Drive erzeugt und erscheint in wenigen Minuten in MV-pdf."
_SLUG_ERSETZUNG = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_SLUG_TEILE = re.compile(r"[a-z0-9]+")
_ORTE = ("lokal", "drive")


def slug(text: str) -> str:
    """Wandelt einen Namen in einen sicheren, kleingeschriebenen Dateinamensteil um.

    Umlaute und ß werden transliteriert, alle uebrigen Zeichenfolgen zu
    Bindestrichen. Ein leerer oder nur aus Sonderzeichen bestehender Text
    ergibt ``unbenannt``.
    """

    if not isinstance(text, str):
        raise ValueError("Feld 'text' muss als Text uebergeben werden")

    klein = text.casefold().translate(_SLUG_ERSETZUNG)
    teile = _SLUG_TEILE.findall(klein)
    return "-".join(teile) if teile else "unbenannt"


def _pruefe_form(form: object) -> dict[str, str]:
    if not isinstance(form, dict):
        raise ValueError("form muss ein dict sein")
    return form


def _pruefe_kontext(kontext: object) -> dict:
    if not isinstance(kontext, dict):
        raise ValueError("kontext muss ein dict sein")
    einstellungen = kontext.get("einstellungen")
    if not isinstance(einstellungen, dict):
        raise ValueError("Feld 'einstellungen' muss als dict uebergeben werden")
    return einstellungen


def _textwert(form: dict[str, str], feld: str, *, pflicht: bool = False) -> str:
    wert = form.get(feld, "")
    if not isinstance(wert, str):
        raise ValueError(f"Feld '{feld}' muss als Text uebergeben werden")
    text = wert.strip()
    if pflicht and not text:
        raise ValueError(f"Feld '{feld}' ist nicht gesetzt")
    return text


def _objekt_id(form: dict[str, str]) -> str | None:
    objekt_id = _textwert(form, "objekt_id")
    return objekt_id or None


def _vorlage(form: dict[str, str]) -> tuple[str, str]:
    auswahl = _textwert(form, "vorlage", pflicht=True)
    if ":" not in auswahl:
        raise ValueError("Feld 'vorlage' muss die Form 'lokal:NAME' oder 'drive:NAME' haben")

    ort, name = (teil.strip() for teil in auswahl.split(":", 1))
    if ort not in _ORTE or not name:
        raise ValueError("Feld 'vorlage' muss die Form 'lokal:NAME' oder 'drive:NAME' haben")
    return ort, name


def _format(form: dict[str, str]) -> str:
    format_ = _textwert(form, "format") or "docx"
    if format_ not in FORMATE:
        raise ValueError(f"Feld 'format' muss einer von {', '.join(FORMATE)} sein")
    return format_


def _ziel(form: dict[str, str]) -> str:
    ziel = _textwert(form, "ziel") or "lokal"
    if ziel not in _ORTE:
        raise ValueError("Feld 'ziel' muss 'lokal' oder 'drive' sein")
    return ziel


def _formularfelder(form: dict[str, str], felder: tuple[str, ...]) -> dict[str, str]:
    ergebnis: dict[str, str] = {}
    for feld in felder:
        if feld not in form:
            continue
        wert = form[feld]
        if not isinstance(wert, str):
            raise ValueError(f"Feld '{feld}' muss als Text uebergeben werden")
        text = wert.strip()
        if text:
            ergebnis[feld] = text
    return ergebnis


def _objektfelder(einstellungen: dict, objekt_id: str) -> dict[str, str]:
    datei = einstellungen.get("objekte_datei")
    if not isinstance(datei, str) or not datei.strip():
        raise ValueError("Feld 'objekte_datei' ist nicht gesetzt")

    try:
        objekte = lade_objekte(datei.strip())
    except ValueError as fehler:
        raise ValueError(f"Feld 'objekte_datei': {fehler}") from fehler

    for objekt in objekte:
        if objekt["id"] == objekt_id:
            return objekt_als_felder(objekt)
    raise ValueError(f"Feld 'objekt_id': Objekt '{objekt_id}' wurde nicht gefunden")


def _ordner_pruefen(pfad: Path, schluessel: str) -> Path:
    try:
        vorhanden = pfad.is_dir()
    except (OSError, ValueError) as fehler:
        raise ValueError(
            f"Feld '{schluessel}': Ordner '{pfad}' ist ungueltig: {fehler}"
        ) from fehler
    if not vorhanden:
        raise ValueError(f"Feld '{schluessel}': Ordner '{pfad}' fehlt")
    return pfad


def _vorlagenordner(einstellungen: dict, ort: str) -> Path:
    return _ordner_pruefen(ordner(einstellungen, "vorlagen", ort), f"vorlagen_{ort}")


def _pdf_eingang(einstellungen: dict) -> Path:
    pfad = pdf_ordner(einstellungen, "eingang")
    try:
        vorhanden = pfad.is_dir()
    except (OSError, ValueError) as fehler:
        raise ValueError(f"PDF-Ordner '{pfad}' (MV-zu-pdf) ist ungueltig: {fehler}") from fehler
    if not vorhanden:
        raise ValueError(f"PDF-Ordner '{pfad}' (MV-zu-pdf) fehlt")
    return pfad


def _google_vorlage(form: dict[str, str], kontext: dict) -> bytes | None:
    """Bytes einer Google-Vorlage (``google:<id>``), vom Aufrufer im Kontext bereitgestellt."""

    if not _textwert(form, "vorlage").startswith("google:"):
        return None
    daten = kontext.get("vorlage_bytes")
    if not isinstance(daten, bytes) or not daten:
        raise ValueError("Feld 'vorlage': Die Google-Vorlage wurde nicht geladen")
    return daten


def _lese_vorlage(einstellungen: dict, ort: str, name: str) -> bytes:
    return lese_vorlage(_vorlagenordner(einstellungen, ort), name)


def _fuelle_vorlage(vorlage: bytes, werte: dict[str, str]) -> bytes:
    try:
        namen = platzhalter(vorlage)
    except ValueError as fehler:
        raise ValueError(f"Feld 'vorlage': {fehler}") from fehler

    fehlend = [name for name in namen if name not in werte]
    if fehlend:
        raise ValueError("Platzhalter ohne Wert: " + ", ".join(fehlend))

    try:
        inhalt = fuelle(vorlage, werte)
    except ValueError as fehler:
        raise ValueError(f"Feld 'vorlage': {fehler}") from fehler

    try:
        reste = unersetzt(inhalt)
    except ValueError as fehler:
        raise ValueError(f"Feld 'vorlage': {fehler}") from fehler
    if reste:
        raise ValueError("Feld 'vorlage': Nicht ersetzte Platzhalter: " + "; ".join(reste))
    return inhalt


def _schreibe_auftrag(
    inhalt: bytes,
    dateiname: str,
    format_: str,
    ziel: str,
    einstellungen: dict,
) -> dict:
    auftraege: list[tuple[str, Path, str, bytes]] = []
    if format_ in ("docx", "docx+pdf"):
        ausgabe = _ordner_pruefen(ordner(einstellungen, "ausgabe", ziel), f"ausgabe_{ziel}")
        auftraege.append(("docx", ausgabe, dateiname, inhalt))
    if format_ in ("pdf", "docx+pdf"):
        auftraege.append(("pdf", _pdf_eingang(einstellungen), dateiname, inhalt))

    geschrieben: list[tuple[str, Path, str]] = []
    try:
        for art, ordner_pfad, name, daten in auftraege:
            geschrieben.append((art, ordner_pfad, schreibe_ausgabe(ordner_pfad, name, daten)))
    except Exception:
        for _, ordner_pfad, name in reversed(geschrieben):
            try:
                (ordner_pfad / name).unlink()
            except OSError:
                pass
        raise

    dateien = [name for art, _, name in geschrieben if art == "docx"]
    pdf_auftrag = next((name for art, _, name in geschrieben if art == "pdf"), None)
    return {
        "dateien": dateien,
        "pdf_auftrag": pdf_auftrag,
        "hinweis": _HINWEIS if pdf_auftrag is not None else "",
    }


def erstelle_vertrag(form: dict[str, str], kontext: dict) -> dict:
    """Erzeugt die Vertragsdatei aus Objekt, Formular und Anfrage.

    Das gewaehlte Objekt liefert den Bestand, nicht leere Formularwerte
    ueberschreiben ihn, danach die Aenderungen aus ``anfrage``. Die Vorlage
    wird vollstaendig gefuellt und erst nach erfolgreicher Pruefung aller
    Ziele geschrieben. Das Ergebnis enthaelt den Aenderungsbericht, die
    erzeugten Ausgabedateien, den PDF-Auftrag und einen Hinweis.
    """

    form = _pruefe_form(form)
    einstellungen = _pruefe_kontext(kontext)
    objekt_id = _objekt_id(form)
    google = _google_vorlage(form, kontext)
    ort, vorlagenname = ("", "") if google is not None else _vorlage(form)
    format_ = _format(form)
    ziel = _ziel(form)

    bestand = _objektfelder(einstellungen, objekt_id) if objekt_id is not None else {}
    bestand.update(_formularfelder(form, FELDER))
    alt = normalisiere(bestand)

    neu = dict(alt)
    anfrage = form.get("anfrage", "")
    if not isinstance(anfrage, str):
        raise ValueError("Feld 'anfrage' muss als Text uebergeben werden")
    if anfrage.strip():
        neu.update(aenderungen_aus_text(anfrage))
    aenderungsbericht = bericht(alt, neu)

    vorlage = google if google is not None else _lese_vorlage(einstellungen, ort, vorlagenname)
    inhalt = _fuelle_vorlage(vorlage, neu)
    dateiname = f"vertrag-{slug(neu.get('mieter_name', ''))}.docx"
    return {
        "bericht": aenderungsbericht,
        **_schreibe_auftrag(inhalt, dateiname, format_, ziel, einstellungen),
    }


def erstelle_protokoll(form: dict[str, str], kontext: dict) -> dict:
    """Erzeugt die Protokolldatei aus Objekt und Formular.

    Ein gewaehltes Objekt liefert nur sein Feld ``objekt``; alle uebrigen
    Protokollfelder stammen aus dem Formular. Die Vorlage wird vollstaendig
    gefuellt und erst nach erfolgreicher Pruefung aller Ziele geschrieben.
    """

    form = _pruefe_form(form)
    einstellungen = _pruefe_kontext(kontext)
    objekt_id = _objekt_id(form)
    google = _google_vorlage(form, kontext)
    ort, vorlagenname = ("", "") if google is not None else _vorlage(form)
    format_ = _format(form)
    ziel = _ziel(form)

    bestand: dict[str, str] = {}
    if objekt_id is not None:
        objektfelder = _objektfelder(einstellungen, objekt_id)
        if "objekt" in objektfelder:
            bestand["objekt"] = objektfelder["objekt"]
    bestand.update(_formularfelder(form, PROTOKOLL_FELDER))
    werte = normalisiere_protokoll(bestand)

    vorlage = google if google is not None else _lese_vorlage(einstellungen, ort, vorlagenname)
    inhalt = _fuelle_vorlage(vorlage, werte)
    dateiname = f"uebergabeprotokoll-{slug(werte.get('mieter_name', ''))}.docx"
    return _schreibe_auftrag(inhalt, dateiname, format_, ziel, einstellungen)
